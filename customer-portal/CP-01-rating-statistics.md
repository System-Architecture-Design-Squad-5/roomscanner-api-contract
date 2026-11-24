# CP-01: Rating Statistics (provided by CP)

**Owner:** Customer Portal · **Consumer:** Provider Portal · **Scope:** `rating:read`
**SRS:** PP-RATING-S01, M01, U01, U02 · CP-RATING-M03, U01, U02 · CP SRS §3 "Reviews and rating statistics" · **Decisions:** D-11, D-17

Customer Portal is the authoritative owner of customer reviews and rating statistics (provider-level, per `CP-RATING` §2.6). Within CP's **Modular Monolith**, `PartnerIntegrationModule` delegates to `RatingModule` via `IRatingExternalService` (`RatingStatisticsExternalDto`).

---

## CP-OP-01 GetRatingStatistics

| Binding | Value |
|---|---|
| REST | `GET {CP}/api/v1/partner/providers/{providerId}/rating-statistics` |
| Kafka (Ultimo) | PP → `rs.rating-stats.request.v1` (`type=GET_RATING_STATISTICS`, key `providerId`) · CP → `rs.rating-stats.response.v1` (`type=GET_RATING_STATISTICS_RESULT`, same `correlationId`) |

Statistics are **on demand only**: no rating-change push and no real-time refresh (`PP-RATING-U02`, `CP-RATING-U01`).

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| `providerId` | string (uuid) | yes | Accommodation **provider** (reviews are per provider) |
| `include` | string[] | no | Any of `OVERALL` (default), `SUBCATEGORIES` (Medium), `PRESET_OPTIONS` (Medium), `COMMENTS` |
| `commentsLimit` | integer | no | `1–50`, default `10` |
| `commentsCursor` | string | no | Opaque cursor for comment pagination |

`overall` and `totalReviews` are always returned. `PRESET_OPTIONS` implies `SUBCATEGORIES`; requesting subcategories returns all three named subcategories. Without `PRESET_OPTIONS`, their `presetOptions` arrays are empty. `COMMENTS` includes the requested comment page; omit `comments` otherwise. Averages are omitted when the corresponding count is zero. The response example below shows only the Service entry to keep it readable; real requests for subcategories return Service, Friendliness and Room.

**Request (REST)**

`GET {CP}/api/v1/partner/providers/5b1c2d3e-0000-4000-8000-000000000150/rating-statistics?include=OVERALL&include=SUBCATEGORIES&include=PRESET_OPTIONS&include=COMMENTS&commentsLimit=10`

**Request (Kafka envelope, Ultimo)**

```json
{
  "messageId": "0c4a7d22-0000-4000-8000-00000000c001",
  "correlationId": "0c4a7d22-0000-4000-8000-00000000c0aa",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "type": "GET_RATING_STATISTICS",
  "schemaVersion": "1.0",
  "source": "PP",
  "replyTo": "rs.rating-stats.response.v1",
  "attempt": 1,
  "deadline": "2026-12-01T04:00:20Z",
  "timestamp": "2026-12-01T04:00:00Z",
  "payload": {
    "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
    "include": ["OVERALL", "SUBCATEGORIES", "PRESET_OPTIONS", "COMMENTS"],
    "commentsLimit": 10
  }
}
```

### Response `200`
| Field | Type | Notes |
|---|---|---|
| `providerId` | string | |
| `asOf` | string | UTC computation time |
| `totalReviews` | integer | Active (non-archived) reviews (`CP-RATING-S04`) |
| `overall` | object | `{ average: number, count: integer, distribution: { "1": int, ..., "5": int } }`. No preset options for Overall. |
| `subcategories` | object[] | Medium: one per `RatingSubcategory` (`SERVICE`, `FRIENDLINESS`, `ROOM`) |
| `subcategories[].subcategory` | RatingSubcategory | |
| `subcategories[].average` | number | |
| `subcategories[].count` | integer | |
| `subcategories[].distribution` | object | Counts for star values `1–5` |
| `subcategories[].presetOptions` | object[] | 2 per star group × 3 groups = 6 per subcategory |
| `presetOptions[].optionId` | string | |
| `presetOptions[].starGroup` | StarGroup | `ONE_TO_TWO`, `THREE`, `FOUR_TO_FIVE` |
| `presetOptions[].label` | string | |
| `presetOptions[].selectedCount` | integer | |
| `presetOptions[].denominator` | integer | Reviews whose subcategory score falls in `starGroup` (D-11) |
| `presetOptions[].percentage` | number | `selectedCount / denominator × 100`, 1 decimal. `0.0` when denominator is 0. |
| `comments` | object | `{ items: [{ reviewId, overallScore, text, createdAt, updatedAt }], nextCursor }` |

```json
{
  "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
  "asOf": "2026-12-01T04:00:00Z",
  "totalReviews": 5,
  "overall": { "average": 4.4, "count": 5, "distribution": { "1": 0, "2": 0, "3": 1, "4": 1, "5": 3 } },
  "subcategories": [
    {
      "subcategory": "SERVICE",
      "average": 4.2,
      "count": 5,
      "distribution": { "1": 0, "2": 0, "3": 1, "4": 2, "5": 2 },
      "presetOptions": [
        { "optionId": "SRV-45-A", "starGroup": "FOUR_TO_FIVE", "label": "The food is delicious", "selectedCount": 3, "denominator": 4, "percentage": 75.0 },
        { "optionId": "SRV-45-B", "starGroup": "FOUR_TO_FIVE", "label": "The services are highly convenient and efficient", "selectedCount": 2, "denominator": 4, "percentage": 50.0 },
        { "optionId": "SRV-3-A", "starGroup": "THREE", "label": "Service was acceptable", "selectedCount": 0, "denominator": 1, "percentage": 0.0 },
        { "optionId": "SRV-3-B", "starGroup": "THREE", "label": "Staff were slow at peak times", "selectedCount": 1, "denominator": 1, "percentage": 100.0 },
        { "optionId": "SRV-12-A", "starGroup": "ONE_TO_TWO", "label": "Requests were ignored", "selectedCount": 0, "denominator": 0, "percentage": 0.0 },
        { "optionId": "SRV-12-B", "starGroup": "ONE_TO_TWO", "label": "Food quality was poor", "selectedCount": 0, "denominator": 0, "percentage": 0.0 }
      ]
    }
  ],
  "comments": {
    "items": [
      { "reviewId": "a1b2c3d4-0000-4000-8000-000000000601", "overallScore": 5, "text": "Lovely hosts and a great breakfast.", "createdAt": "2026-10-02T08:00:00Z", "updatedAt": "2026-10-02T08:00:00Z" }
    ]
  }
}
```
*(`FRIENDLINESS` and `ROOM` entries have the same shape and use the authoritative 18-option `PresetFeedbackOptionCatalogue` in `common/02-shared-types.md`: `FRD-45-A/B`, `FRD-3-A/B`, `FRD-12-A/B` and `RM-45-A/B`, `RM-3-A/B`, `RM-12-A/B`.)*

### Shard Routing & Redundancy (`BE-M07`, `CP-RATING-U02`, CP SRS §3)
- **Targeted Sharding:** CP shards reviews by **`providerId`** (hash). A request for one provider touches exactly one shard; deleted reviews reside in a separate archive shard/table (`CP-RATING-S04`).
- **Redundant Rating Service:** At Ultimo integration, CP runs a second instance of the CP modular monolith (same single deployable, all modules); both instances' rating consumers join group `cp-rating-service` on `rs.rating-stats.request.v1`, so requests continue to be served if one instance fails (`common/04-kafka.md` §5). There is no separate rating microservice.

### Errors
- `404 RESOURCE_NOT_FOUND` is **not** used for providers with no reviews (`200` with `totalReviews: 0`).
- `400 VALIDATION_ERROR`: invalid `include` enum or `commentsLimit` outside `1–50`.
- `503 SERVICE_UNAVAILABLE`: target review shard unavailable → PP retries (`04-kafka.md` §4), then shows its cached value marked stale.
- `401 PARTNER_UNAUTHENTICATED` / `403 PARTNER_FORBIDDEN` / `429 RATE_LIMITED`: standard partner errors, see `common/01-conventions.md` (read limit: 120 requests per 60 s).

```json
{
  "error": {
    "code": "SERVICE_UNAVAILABLE",
    "message": "Rating statistics shard is temporarily unavailable.",
    "requestId": "0c4a7d22-0000-4000-8000-00000000c001",
    "timestamp": "2026-12-01T04:00:05Z"
  }
}
```
