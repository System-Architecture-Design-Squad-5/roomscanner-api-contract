# CP Services Required by Provider Portal

> **Status:** Proposed. Drafted by the PP team as **requirements**. The CP team must review, adjust and approve these in the PR (CP is the owner of these operations).

**Owner:** Customer Portal · **Consumer:** Provider Portal

---

## CP-OP-01 GetRatingStatistics

**SRS:** PP-RATING-S01, M01, U01, U02 · CP-RATING-M03, U01, U02 · Decision D-11
**Scope:** `rating:read`

| Binding | Value |
|---|---|
| REST | `GET {CP}/api/v1/partner/providers/{providerId}/rating-statistics` |
| Kafka (Ultimo) | PP → `rs.rating-stats.request.v1` (`type=GET_RATING_STATISTICS`, key `providerId`) · CP → `rs.rating-stats.response.v1` (`type=GET_RATING_STATISTICS_RESULT`, same `correlationId`) |

Statistics are **on demand only**: no rating-change push and no real-time refresh (PP-RATING-U02, CP-RATING-U01).

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| providerId | string | yes | Accommodation **provider** (reviews are per provider) |
| include | string[] | no | Any of `OVERALL` (default), `SUBCATEGORIES` (Medium), `PRESET_OPTIONS` (Medium), `COMMENTS` |
| commentsLimit | integer | no | 1-50, default 10 |
| commentsCursor | string | no | Pagination of comments |

**Request (REST)**

`GET {CP}/api/v1/partner/providers/5b1c2d3e-0000-4000-8000-000000000150/rating-statistics?include=OVERALL&include=SUBCATEGORIES&include=PRESET_OPTIONS&include=COMMENTS&commentsLimit=10`

**Request (Kafka envelope, Ultimo)**

```json
{
  "messageId": "0c4a7d22-0000-4000-8000-00000000c001",
  "correlationId": "0c4a7d22-0000-4000-8000-00000000c0aa",
  "type": "GET_RATING_STATISTICS",
  "schemaVersion": "1.0",
  "source": "PP",
  "replyTo": "rs.rating-stats.response.v1",
  "attempt": 1,
  "deadline": "2026-12-01T04:00:05Z",
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
| providerId | string | |
| asOf | string | UTC computation time |
| totalReviews | integer | Active (non-archived) reviews (CP-RATING-S04) |
| overall | object | `{ average: number, count: integer, distribution: { "1": int, ..., "5": int } }`. There are no preset options for Overall. |
| subcategories | object[] | Medium: one per `RatingSubcategory` |
| subcategories[].subcategory | RatingSubcategory | |
| subcategories[].average | number | |
| subcategories[].count | integer | |
| subcategories[].distribution | object | Counts for star values 1-5 |
| subcategories[].presetOptions | object[] | 2 per star group × 3 groups = 6 per subcategory |
| presetOptions[].optionId | string | |
| presetOptions[].starGroup | StarGroup | |
| presetOptions[].label | string | |
| presetOptions[].selectedCount | integer | |
| presetOptions[].denominator | integer | Reviews whose subcategory score falls in `starGroup` (D-11) |
| presetOptions[].percentage | number | `selectedCount / denominator × 100`, 1 decimal. `0.0` when the denominator is 0. |
| comments | object | `{ items: [{ reviewId, overallScore, text, createdAt, updatedAt }], nextCursor }` |

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
*(`FRIENDLINESS` and `ROOM` entries have the same shape and are omitted here for length.)*

Check: The Service distribution has 4 reviews in the 4-5 group and 1 in the 3 group, so the denominators are 4 and 1. Percentages of the two options in a group can add up to more than 100% (a customer may pick both) or less than 100% (a customer may pick none). Reviews that picked no option still count in the denominator.

### Shard routing (CP-RATING-U02)
CP shards reviews by **`providerId`** (hash). A request for one provider touches exactly one shard.

### Errors
`404 RESOURCE_NOT_FOUND` is **not** used for providers with no reviews. That case returns `200` with `totalReviews: 0`. `503 SERVICE_UNAVAILABLE` → PP retries (04-kafka §4), then shows its cached value marked stale.

---

## CP-OP-02 GetCustomerMembership

**SRS:** PP-DISCOUNT-S02 · Decision D-06 · **Scope:** `membership:read`

| Binding | Value |
|---|---|
| REST | `GET {CP}/api/v1/partner/customers/{customerId}/membership` |
| Kafka | `rs.membership.request.v1` → `rs.membership.response.v1` |

Request:

| Field | In | Type | Required | Notes |
|---|---|---|---|---|
| customerId | path | string (uuid) | yes | CP application user ID |

**Request (Kafka payload, `type=GET_MEMBERSHIP`)**

```json
{ "customerId": "7d1e2f30-0000-4000-8000-000000000901" }
```

Response `200`:

| Field | Type | Notes |
|---|---|---|
| customerId | string | |
| tier | MembershipTier | |
| status | MembershipStatus | |
| validFrom / validUntil | string | UTC. Present for Premium (active or expired). |

```json
{ "customerId": "7d1e2f30-0000-4000-8000-000000000901", "tier": "PREMIUM", "status": "ACTIVE", "validFrom": "2026-08-01T00:00:00Z", "validUntil": "2027-08-01T00:00:00Z" }
```
Errors: `404 RESOURCE_NOT_FOUND` (unknown customer) · `503`. PP fails closed: no discount without verification.

---

## CP-OP-03 UpdateSimulatedOrder (Simplex only)

**SRS:** PP-MONEY-S01 ("complete or cancel the simulated transaction order issued by CP") · CP-MONEY-S01 · **Scope:** `order:write`

`PATCH {CP}/api/v1/partner/orders/{orderId}` · `Idempotency-Key` required

| Field | Type | Required | Notes |
|---|---|---|---|
| action | string | yes | `COMPLETE` (on receptionist approval) or `CANCEL` (on cancellation) |
| bookingId | string | yes | |
| reason | string | no | |

**Request**

```json
{
  "action": "COMPLETE",
  "bookingId": "8c9d0e1f-0000-4000-8000-000000000801"
}
```

**Response `200`**

```json
{
  "orderId": "55aa66bb-0000-4000-8000-000000000701",
  "status": "COMPLETED",
  "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
  "updatedAt": "2026-12-01T09:15:41Z"
}
```
Errors: `404` unknown order · `409 STATE_CONFLICT` (already completed or cancelled with a different action).

---

## CP-OP-04 ReceiveBookingEvent (webhook, Simplex/Medium)

**SRS:** PP-MONEY-S01, M03 · CP-MONEY-S01, M02(M) · **Scope:** `booking-event:write`

`POST {CP}/api/v1/partner/booking-events` · headers `Authorization`, `X-RS-Signature`

- Body: the `BookingStatusEvent` payload from PP-OP-11.
- Response `200` `{ "eventId": "...", "accepted": true, "duplicate": false }` within 5 s. Heavy work (emails, socket push) is done asynchronously after acknowledging.
- `401` if the signature is invalid. Any `5xx` or timeout → PP retries (PP-04 delivery table).

---

## CP-OP-05 EventFavoriteChanged (Ultimo, Kafka)

**SRS:** CP-EVENT-U01, U03 · PP-EVENT-U02 · Topic `rs.event.favorite.v1` (**created by CP**), key `eventId`

| Field | Type | Required | Notes |
|---|---|---|---|
| changeType | string | yes | `FAVORITE_ADDED`, `FAVORITE_REMOVED`, or `EVENT_DATES_CHANGED` |
| favoriteId | string | for FAVORITE_* | |
| customerId | string | for FAVORITE_* | |
| favoritedAt | string | for FAVORITE_ADDED | UTC. PP uses it for the immediate vs scheduled decision. |
| event | EventInfo | yes | Current event data |

```json
{
  "messageId": "3e550000-0000-4000-8000-000000000d01",
  "correlationId": "fa7e0000-0000-4000-8000-000000000b02",
  "type": "FAVORITE_ADDED",
  "schemaVersion": "1.0",
  "source": "CP",
  "timestamp": "2026-12-12T03:00:00Z",
  "payload": {
    "changeType": "FAVORITE_ADDED",
    "favoriteId": "fa7e0000-0000-4000-8000-000000000b02",
    "customerId": "7d1e2f30-0000-4000-8000-000000000902",
    "favoritedAt": "2026-12-12T03:00:00Z",
    "event": { "eventId": "e7e70000-0000-4000-8000-000000000c01", "name": "Hùng Kings' Temple Festival", "summary": "National festival honouring the Hùng Kings with processions, folk games and xoan singing.", "locationName": "Hùng Kings' Temple, Viet Tri City, Phu Tho", "city": "Viet Tri", "country": "VN", "timeZone": "Asia/Ho_Chi_Minh", "startDate": "2027-04-12", "endDate": "2027-04-18", "searchRoute": "/search?city=Viet%20Tri&country=VN&checkIn=2027-04-12&checkOut=2027-04-13" }
  }
}
```
- CP sends `FAVORITE_ADDED` **only** for customers who are active Premium at favorite time (CP-EVENT-M01).
- CP sends `EVENT_DATES_CHANGED` only when `startDate` or `endDate` changes. Other edits are not sent (D-12).
