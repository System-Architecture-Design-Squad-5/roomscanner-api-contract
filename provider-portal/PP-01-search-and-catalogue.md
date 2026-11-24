# PP-01: Search and Catalogue (provided by PP)

**Owner:** Provider Portal · **Consumer:** Customer Portal · **Scope:** `search:read`
**SRS:** PP-SEARCH-S01, S02, S03, M01, M02, U01, U02 · PP-ROOM-S05, S06, U02 · CP-SEARCH-S01, S02, S03, M01, M02, M03
**Business rules:** Decisions D-02, D-03, D-04, D-05, D-16

PP performs **authoritative** retrieval. CP only renders the results. All four operations are read-only and safe to retry.

> **CP Modular Monolith Integration (`SearchModule` & `RatingModule`):**
> - CP's `SearchModule` maps `PP-OP-01` (`/api/v1/customer/search/providers`), `PP-OP-02` (`/api/v1/customer/branches/{branchId}`), `PP-OP-03` (`/api/v1/customer/branches/{branchId}/rooms`), and `PP-OP-04` (`/api/v1/customer/rooms/{roomId}`). When a customer is logged in with an active Premium JWE, `SearchModule` passes `membershipTier=PREMIUM` on `PP-OP-03` and `PP-OP-04` so PP populates display-only `premiumPricePerNight`.
> - **Default City & Sub-Region Cities:** Because `PP-OP-01` requires `city` and returns `400 CITY_OUTSIDE_SUBREGION` for cities outside the squad's two assigned countries (`VN` and `SG`), CP's frontend search bar provides a curated city selector for the squad's sub-region and defaults initial homepage browsing to the primary sub-region city (e.g. `city=Ho Chi Minh City`).
> - While `PP-OP-02` returns up to 3 `latestComments` for the branch overview, full provider review pages (`GET /api/v1/customer/providers/{providerId}/reviews`) are served **directly in-process** inside CP's Modular Monolith by `SearchModule` calling `RatingModule` via `IRatingExternalService` (`ProviderPublicReviewsDto`) using `branch.providerId`.

---

## PP-OP-01 SearchProviders

Returns the branches (properties) in a city that match the keyword and filters, with lazy-load pagination.

| Binding | Value |
|---|---|
| REST | `GET /api/v1/partner/search/providers` |
| Kafka (Ultimo) | `rs.search.request.v1` (`type=SEARCH_PROVIDERS`) → `rs.search.response.v1` (`type=SEARCH_PROVIDERS_RESULT`) |

### Request (query parameters, or `payload` fields on Kafka)

| Field | Type | Required | Level | Notes |
|---|---|---|---|---|
| city | string | yes | S | Case-insensitive exact city match within the squad's sub-region |
| country | string | no | S | ISO alpha-2. Narrows the shard (U01). |
| q | string | no | S/M | Simplex: substring on provider/branch name. Medium: multi-field FTS (D-03). Max 200 characters. |
| category | ProviderCategory[] | no | S | Repeatable: `?category=HOTEL&category=HOMESTAY` |
| roomType | RoomType[] | no | S | |
| amenities | Amenity[] | no | S | |
| matchMode | string | no | M | `ANY` (default, OR semantics) or `ALL` |
| checkInDate | string (date) | no | S | Must come with `checkOutDate` |
| checkOutDate | string (date) | no | S | > checkInDate, at most 30 nights |
| rooms | integer | no | S | Rooms needed, default 1. Branches with fewer available rooms are excluded. |
| sort | string | no | M | `RELEVANCE` (default), `RATING_DESC`, `PRICE_ASC` |
| limit | integer | no | M | 1-50, default 10 |
| cursor | string | no | M | From the previous `pageInfo.nextCursor` |

### Response `200`

| Field | Type | Notes |
|---|---|---|
| items | ProviderSearchResult[] | `02-shared-types.md` |
| pageInfo.limit | integer | |
| pageInfo.nextCursor | string | Omitted when `hasMore=false` |
| pageInfo.hasMore | boolean | |
| appliedFilters | object | Echo of the interpreted filters, including FTS-recognised phrases (helps CP show chips) |

### Example: Simplex substring (CP-SEARCH-S01 example)

`GET /api/v1/partner/search/providers?city=Ho%20Chi%20Minh%20City&q=he&roomType=SINGLE_TWIN_BED`

```json
{
  "items": [
    {
      "providerId": "5b1c2d3e-0000-4000-8000-000000000101",
      "providerName": "Sheraton Hotels Vietnam Co.",
      "branchId": "9a8b7c6d-0000-4000-8000-000000000201",
      "branchName": "Sheraton Hotel Saigon",
      "category": "HOTEL",
      "logoUrl": "https://cdn.roomscanner.local/logos/5b1c2d3e_256.webp",
      "location": { "addressLine": "88 Dong Khoi, District 1", "city": "Ho Chi Minh City", "country": "VN", "timeZone": "Asia/Ho_Chi_Minh" },
      "roomTypesOffered": ["SINGLE_TWIN_BED", "DOUBLE_BED"],
      "amenities": ["FREE_WIFI", "PRIVATE_BATHROOM", "AIR_CONDITIONING", "DISABLED_FACILITIES"],
      "availableRoomCount": 14,
      "lowestPricePerNight": { "amountMinor": 12000, "currency": "USD" },
      "ratingSummary": { "overallAverage": 4.6, "totalReviews": 128, "source": "CP", "asOf": "2026-11-20T10:50:00Z" }
    },
    {
      "providerId": "5b1c2d3e-0000-4000-8000-000000000102",
      "providerName": "Henry Hospitality",
      "branchId": "9a8b7c6d-0000-4000-8000-000000000202",
      "branchName": "Henry Suites",
      "category": "HOTEL",
      "logoUrl": "https://cdn.roomscanner.local/logos/henry_256.webp",
      "location": { "addressLine": "12 Ly Tu Trong, District 1", "city": "Ho Chi Minh City", "country": "VN", "timeZone": "Asia/Ho_Chi_Minh" },
      "roomTypesOffered": ["SINGLE_TWIN_BED"],
      "amenities": ["FREE_WIFI", "AIR_CONDITIONING"],
      "availableRoomCount": 3,
      "lowestPricePerNight": { "amountMinor": 4500, "currency": "USD" },
      "ratingSummary": { "totalReviews": 0, "source": "CP", "asOf": "2026-11-20T10:50:00Z" }
    }
  ],
  "pageInfo": { "limit": 10, "hasMore": false },
  "appliedFilters": { "city": "Ho Chi Minh City", "q": "he", "roomType": ["SINGLE_TWIN_BED"], "matchMode": "ANY" }
}
```

### Example: Medium FTS with OR semantics (CP-SEARCH-M01 example)

`GET /api/v1/partner/search/providers?city=Hoi%20An&q=Single%20Bed%20Free%20WiFi%20Homestay&limit=2`

```json
{
  "items": [
    {
      "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
      "providerName": "Thu Bon Family Stays",
      "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
      "branchName": "Riverside Homestay Hoi An",
      "category": "HOMESTAY",
      "logoUrl": "https://cdn.roomscanner.local/logos/thubon_256.webp",
      "location": { "addressLine": "21 Nguyen Phuc Chu", "city": "Hoi An", "country": "VN", "timeZone": "Asia/Ho_Chi_Minh" },
      "roomTypesOffered": ["SINGLE_TWIN_BED", "DOUBLE_BED"],
      "amenities": ["FREE_WIFI", "KITCHEN", "WASHING_MACHINE"],
      "availableRoomCount": 4,
      "lowestPricePerNight": { "amountMinor": 2500, "currency": "USD" },
      "ratingSummary": { "overallAverage": 4.8, "totalReviews": 41, "source": "CP", "asOf": "2026-11-20T10:40:00Z" },
      "matchedFields": ["category", "roomType", "amenities"],
      "relevanceScore": 0.97
    },
    {
      "providerId": "5b1c2d3e-0000-4000-8000-000000000151",
      "providerName": "Ancient Town Hotels",
      "branchId": "9a8b7c6d-0000-4000-8000-000000000251",
      "branchName": "Hoi An Lantern Hotel",
      "category": "HOTEL",
      "logoUrl": "https://cdn.roomscanner.local/logos/lantern_256.webp",
      "location": { "addressLine": "5 Tran Phu", "city": "Hoi An", "country": "VN", "timeZone": "Asia/Ho_Chi_Minh" },
      "roomTypesOffered": ["SINGLE_TWIN_BED"],
      "amenities": ["FREE_WIFI", "AIR_CONDITIONING"],
      "availableRoomCount": 9,
      "lowestPricePerNight": { "amountMinor": 3800, "currency": "USD" },
      "ratingSummary": { "overallAverage": 4.2, "totalReviews": 77, "source": "CP", "asOf": "2026-11-20T10:40:00Z" },
      "matchedFields": ["roomType", "amenities"],
      "relevanceScore": 0.64
    }
  ],
  "pageInfo": { "limit": 2, "nextCursor": "eyJzIjowLjY0LCJpZCI6IjI1MSJ9", "hasMore": true },
  "appliedFilters": {
    "city": "Hoi An",
    "q": "Single Bed Free WiFi Homestay",
    "recognised": { "category": ["HOMESTAY"], "roomType": ["SINGLE_TWIN_BED"], "amenities": ["FREE_WIFI"] },
    "matchMode": "ANY"
  }
}
```

### Kafka example (Ultimo)

```json
{
  "messageId": "e1a2b3c4-0000-4000-8000-00000000a001",
  "correlationId": "c0ffee00-0000-4000-8000-00000000b001",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "type": "SEARCH_PROVIDERS",
  "schemaVersion": "1.0",
  "source": "CP",
  "replyTo": "rs.search.response.v1",
  "attempt": 1,
  "deadline": "2026-12-01T03:00:12Z",
  "timestamp": "2026-12-01T03:00:00Z",
  "payload": {
    "city": "Hoi An",
    "country": "VN",
    "q": "Single Bed Free WiFi Homestay",
    "limit": 10
  }
}
```
The response has `type=SEARCH_PROVIDERS_RESULT`, the same `correlationId` and `traceId`, `causationId` = the `messageId` of the request it answers, `status` = `OK` or `ERROR`, and a `payload` identical to the REST `200` body (or to the standard error body when `status=ERROR`). Search requests are resent per INT-U03: 3 s per attempt, 3 attempts, 12 s overall budget (`common/04-kafka.md`).

**Kafka response example (`status=OK`)**

```json
{
  "messageId": "e1a2b3c4-0000-4000-8000-00000000a002",
  "correlationId": "c0ffee00-0000-4000-8000-00000000b001",
  "causationId": "e1a2b3c4-0000-4000-8000-00000000a001",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "type": "SEARCH_PROVIDERS_RESULT",
  "schemaVersion": "1.0",
  "source": "PP",
  "status": "OK",
  "timestamp": "2026-12-01T03:00:01Z",
  "payload": {
    "items": [
      {
        "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
        "providerName": "Thu Bon Family Stays",
        "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
        "branchName": "Riverside Homestay Hoi An",
        "category": "HOMESTAY",
        "logoUrl": "https://cdn.roomscanner.local/logos/thubon_256.webp",
        "location": { "addressLine": "21 Nguyen Phuc Chu", "city": "Hoi An", "country": "VN", "timeZone": "Asia/Ho_Chi_Minh" },
        "roomTypesOffered": ["SINGLE_TWIN_BED", "DOUBLE_BED"],
        "amenities": ["FREE_WIFI", "KITCHEN", "WASHING_MACHINE"],
        "availableRoomCount": 4,
        "lowestPricePerNight": { "amountMinor": 2500, "currency": "USD" },
        "ratingSummary": { "overallAverage": 4.8, "totalReviews": 41, "source": "CP", "asOf": "2026-12-01T02:50:00Z" },
        "matchedFields": ["category", "roomType", "amenities"],
        "relevanceScore": 0.97
      }
    ],
    "pageInfo": { "limit": 10, "hasMore": false },
    "appliedFilters": { "city": "Hoi An", "q": "Single Bed Free WiFi Homestay", "matchMode": "ANY" }
  }
}
```

**Kafka error response example (`status=ERROR`)**

```json
{
  "messageId": "e1a2b3c4-0000-4000-8000-00000000a003",
  "correlationId": "c0ffee00-0000-4000-8000-00000000b002",
  "causationId": "e1a2b3c4-0000-4000-8000-00000000a010",
  "traceId": "7ace0000-0000-4000-8000-000000000002",
  "type": "SEARCH_PROVIDERS_RESULT",
  "schemaVersion": "1.0",
  "source": "PP",
  "status": "ERROR",
  "timestamp": "2026-12-01T03:00:01Z",
  "payload": {
    "error": {
      "code": "CITY_OUTSIDE_SUBREGION",
      "message": "This city is not served by this squad.",
      "httpStatus": 400,
      "requestId": "e1a2b3c4-0000-4000-8000-00000000a010",
      "timestamp": "2026-12-01T03:00:01Z"
    }
  }
}
```

### Shard routing (PP-SEARCH-U01)
- Room/branch data is sharded by **`country`** (shard key), since the squad serves two countries, `shard_vn`, `shard_sg`. A city→country lookup is cached in Redis (`geo:city:{normalisedCity}` → `country`).
- A request is routed to **one** shard: the one for `country`, or for the country resolved from `city`. PP never broadcasts to unrelated shards.
- `ratingSummary` is never gathered from other shards: it comes from CP rating statistics cached in Redis (D-11, PP-SEARCH-U01).

### Errors
| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Missing `city`, bad enum, or `checkOutDate ≤ checkInDate` |
| 400 | `CITY_OUTSIDE_SUBREGION` | City not served by this squad |
| 400 | `INVALID_CURSOR` | Cursor tampered with or expired (cursors last 30 min) |
| 503 | `SERVICE_UNAVAILABLE` | Search service or shard unavailable |
| 401 / 403 / 429 | `PARTNER_UNAUTHENTICATED` / `PARTNER_FORBIDDEN` / `RATE_LIMITED` | Standard partner errors, see `common/01-conventions.md` (read limit: 120 requests per 60 s) |

**Error example (`400 INVALID_CURSOR`)**

```json
{
  "error": {
    "code": "INVALID_CURSOR",
    "message": "The cursor is invalid or has expired. Restart the search.",
    "requestId": "3f2a9c1e-7b4d-4e0a-8c5f-9d1b2a6e7f30",
    "timestamp": "2026-12-01T03:00:05Z"
  }
}
```

### Caching
PP caches the first result page per normalised query in Redis (`search:{hash(query)}`, TTL **60 s**). The cache is invalidated for a branch's city when a room in it is created, edited, archived or booked.

---

## PP-OP-02 GetBranchDetails

Public profile of one branch, with its rating summary and latest comments (PP-SEARCH-S02 "rating, comments"). Comments are sourced from CP-OP-01.

| Binding | Value |
|---|---|
| REST | `GET /api/v1/partner/branches/{branchId}` |
| Kafka | `rs.search.request.v1` (`type=GET_BRANCH`, payload `{ "branchId": "..." }`) |

Kafka messages use the same envelope as PP-OP-01 (`common/04-kafka.md`), with a different `type` and `payload`.

### Request

| Field | In | Type | Required | Notes |
|---|---|---|---|---|
| branchId | path | string (uuid) | yes | From `ProviderSearchResult.branchId` |
| checkInDate / checkOutDate | query | string (date) | no | Used for `availableRoomCount`. Default: tonight (D-05). |

**Request (Kafka payload, `type=GET_BRANCH`)**

```json
{ "branchId": "9a8b7c6d-0000-4000-8000-000000000250", "checkInDate": "2027-04-10", "checkOutDate": "2027-04-13" }
```

### Response `200`
| Field | Type | Notes |
|---|---|---|
| branch | ProviderSearchResult | Search fields without `matchedFields` / `relevanceScore` |
| description | string | ≤ 2,000 characters |
| imageUrls | string[] | Branch photos |
| checkInTime / checkOutTime | string | `HH:mm` |
| latestComments | object[] | ≤ 3 items `{ reviewId, overallScore, text, createdAt }` from CP. Empty if none, or if CP is unavailable. |

```json
{
  "branch": {
    "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
    "providerName": "Thu Bon Family Stays",
    "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
    "branchName": "Riverside Homestay Hoi An",
    "category": "HOMESTAY",
    "logoUrl": "https://cdn.roomscanner.local/logos/thubon_256.webp",
    "location": { "addressLine": "21 Nguyen Phuc Chu", "city": "Hoi An", "country": "VN", "timeZone": "Asia/Ho_Chi_Minh" },
    "roomTypesOffered": ["SINGLE_TWIN_BED", "DOUBLE_BED"],
    "amenities": ["FREE_WIFI", "KITCHEN", "WASHING_MACHINE"],
    "availableRoomCount": 4,
    "lowestPricePerNight": { "amountMinor": 2500, "currency": "USD" },
    "ratingSummary": { "overallAverage": 4.8, "totalReviews": 41, "source": "CP", "asOf": "2026-11-20T10:40:00Z" }
  },
  "description": "Family-run homestay on the Thu Bon river, 5 minutes' walk to the Ancient Town.",
  "imageUrls": ["https://cdn.roomscanner.local/branches/250/1.webp", "https://cdn.roomscanner.local/branches/250/2.webp"],
  "checkInTime": "14:00",
  "checkOutTime": "12:00",
  "latestComments": [
    { "reviewId": "a1b2c3d4-0000-4000-8000-000000000601", "overallScore": 5, "text": "Lovely hosts and a great breakfast.", "createdAt": "2026-10-02T08:00:00Z" }
  ]
}
```
### Errors

| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Malformed `branchId` or dates |
| 404 | `RESOURCE_NOT_FOUND` | Unknown or archived branch |
| 503 | `SERVICE_UNAVAILABLE` | Search service unavailable |
| 401 / 403 / 429 | `PARTNER_UNAUTHENTICATED` / `PARTNER_FORBIDDEN` / `RATE_LIMITED` | Standard partner errors, see `common/01-conventions.md` (read limit: 120 requests per 60 s) |


**Error example (`404 RESOURCE_NOT_FOUND`)**

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The branch does not exist or has been archived.",
    "requestId": "5d7e1a90-2c3b-4f6a-9b1e-0a4c8d2f6b11",
    "timestamp": "2026-12-01T03:00:05Z"
  }
}
```

If CP-OP-01 is unavailable, PP still answers `200`: `latestComments` is empty and `ratingSummary` carries the last cached value (D-11). If no cached statistics exist, omit `ratingSummary` and display "Rating temporarily unavailable". A missing summary must not be interpreted as zero reviews.

---

## PP-OP-03 ListBranchRooms

The available room listings of a selected provider branch (PP-SEARCH-S03: room name, available quantity, price per night, images).

| Binding | Value |
|---|---|
| REST | `GET /api/v1/partner/branches/{branchId}/rooms` |
| Kafka | `rs.search.request.v1` (`type=LIST_ROOMS`) |

Kafka messages use the same envelope as PP-OP-01 (`common/04-kafka.md`), with a different `type` and `payload`.

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| branchId | string (path) | yes | |
| checkInDate / checkOutDate | string (date) | no | Default: tonight (D-05) |
| rooms | integer | no | Default 1. Listings with less availability are returned with `availableQuantity` but flagged by CP as unavailable. |
| roomType | RoomType[] | no | |
| amenities | Amenity[] | no | |
| membershipTier | MembershipTier | no | When `PREMIUM`, `premiumPricePerNight` is filled where a policy is assigned |
| limit | integer | no | 1-50, default 10 |
| cursor | string | no | From the previous `pageInfo.nextCursor`. Expires after 30 minutes. |

**Request (Kafka payload, `type=LIST_ROOMS`)**

```json
{
  "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
  "checkInDate": "2027-04-10",
  "checkOutDate": "2027-04-13",
  "rooms": 2,
  "roomType": ["SINGLE_TWIN_BED"],
  "membershipTier": "PREMIUM",
  "limit": 10
}
```

### Response `200`
`{ "items": RoomSummary[], "pageInfo": {...} }`. `items` fields: `RoomSummary` in `common/02-shared-types.md`. `pageInfo` (`limit`, `nextCursor`, `hasMore`): `common/01-conventions.md` Pagination.

```json
{
  "items": [
    {
      "roomId": "3f2e1d0c-0000-4000-8000-000000000301",
      "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
      "name": "Garden Single Room",
      "roomType": "SINGLE_TWIN_BED",
      "maxOccupancy": 2,
      "totalQuantity": 3,
      "availableQuantity": 2,
      "pricePerNight": { "amountMinor": 2500, "currency": "USD" },
      "premiumPricePerNight": { "amountMinor": 2125, "currency": "USD" },
      "amenities": ["FREE_WIFI", "KITCHEN"],
      "thumbnailUrl": "https://cdn.roomscanner.local/rooms/301/1_thumb.webp",
      "imageUrls": ["https://cdn.roomscanner.local/rooms/301/1.webp", "https://cdn.roomscanner.local/rooms/301/2.webp"]
    }
  ],
  "pageInfo": { "limit": 10, "hasMore": false }
}
```
### Errors

| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Bad dates, enum values or `rooms < 1` |
| 400 | `INVALID_CURSOR` | Cursor tampered with or expired (cursors last 30 min) |
| 404 | `RESOURCE_NOT_FOUND` | Unknown or archived branch |
| 503 | `SERVICE_UNAVAILABLE` | Search service unavailable |
| 401 / 403 / 429 | `PARTNER_UNAUTHENTICATED` / `PARTNER_FORBIDDEN` / `RATE_LIMITED` | Standard partner errors, see `common/01-conventions.md` (read limit: 120 requests per 60 s) |

**Error example (`400 VALIDATION_ERROR`)**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid fields.",
    "details": [{ "field": "rooms", "issue": "must be at least 1" }],
    "requestId": "8b2c4d6e-1a3f-4b5c-8d7e-9f0a1b2c3d4e",
    "timestamp": "2026-12-01T03:00:05Z"
  }
}
```

---

## PP-OP-04 GetRoomDetails

| Binding | Value |
|---|---|
| REST | `GET /api/v1/partner/rooms/{roomId}?checkInDate=&checkOutDate=&membershipTier=` |
| Kafka | `rs.search.request.v1` (`type=GET_ROOM`) |

Kafka messages use the same envelope as PP-OP-01 (`common/04-kafka.md`), with a different `type` and `payload`.

### Request

| Field | In | Type | Required | Notes |
|---|---|---|---|---|
| roomId | path | string (uuid) | yes | |
| checkInDate / checkOutDate | query | string (date) | no | Used for `availableQuantity`. Default: tonight (D-05). |
| membershipTier | query | MembershipTier | no | When `PREMIUM`, `premiumPricePerNight` is filled where a policy is assigned. Display only. |

**Request (Kafka payload, `type=GET_ROOM`)**

```json
{ "roomId": "3f2e1d0c-0000-4000-8000-000000000301", "checkInDate": "2027-04-10", "checkOutDate": "2027-04-13", "membershipTier": "PREMIUM" }
```

### Response `200`: `RoomDetail`
Fields and types: `RoomDetail` in `common/02-shared-types.md`.

```json
{
  "roomId": "3f2e1d0c-0000-4000-8000-000000000301",
  "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
  "name": "Garden Single Room",
  "roomType": "SINGLE_TWIN_BED",
  "maxOccupancy": 2,
  "bedCount": 1,
  "sizeSqm": 18,
  "totalQuantity": 3,
  "availableQuantity": 2,
  "pricePerNight": { "amountMinor": 2500, "currency": "USD" },
  "premiumPricePerNight": { "amountMinor": 2125, "currency": "USD" },
  "amenities": ["FREE_WIFI", "KITCHEN"],
  "description": "Quiet single room facing the garden, shared kitchen access.",
  "thumbnailUrl": "https://cdn.roomscanner.local/rooms/301/1_thumb.webp",
  "imageUrls": ["https://cdn.roomscanner.local/rooms/301/1.webp", "https://cdn.roomscanner.local/rooms/301/2.webp", "https://cdn.roomscanner.local/rooms/301/3.webp"],
  "checkInTime": "14:00",
  "checkOutTime": "12:00",
  "discountPolicy": { "discountPackageId": "d15c0a7e-0000-4000-8000-000000000015", "name": "Premium 15% Off", "type": "PERCENTAGE", "value": 15, "eligibleTier": "PREMIUM", "active": true },
  "provider": {
    "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
    "providerName": "Thu Bon Family Stays",
    "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
    "branchName": "Riverside Homestay Hoi An",
    "category": "HOMESTAY",
    "logoUrl": "https://cdn.roomscanner.local/logos/thubon_256.webp",
    "location": { "addressLine": "21 Nguyen Phuc Chu", "city": "Hoi An", "country": "VN", "timeZone": "Asia/Ho_Chi_Minh" },
    "roomTypesOffered": ["SINGLE_TWIN_BED", "DOUBLE_BED"],
    "amenities": ["FREE_WIFI", "KITCHEN", "WASHING_MACHINE"],
    "availableRoomCount": 4,
    "lowestPricePerNight": { "amountMinor": 2500, "currency": "USD" },
    "ratingSummary": { "overallAverage": 4.8, "totalReviews": 41, "source": "CP", "asOf": "2026-11-20T10:40:00Z" }
  }
}
```
### Errors

| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Malformed `roomId`, dates or `membershipTier` |
| 404 | `RESOURCE_NOT_FOUND` | Unknown or **archived** room (PP-ROOM-S04 excludes archive storage from ordinary queries) |
| 503 | `SERVICE_UNAVAILABLE` | Search service unavailable |
| 401 / 403 / 429 | `PARTNER_UNAUTHENTICATED` / `PARTNER_FORBIDDEN` / `RATE_LIMITED` | Standard partner errors, see `common/01-conventions.md` (read limit: 120 requests per 60 s) |

**Error example (`404 RESOURCE_NOT_FOUND`)**

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "The room does not exist or has been archived.",
    "requestId": "a9c8b7d6-5e4f-4a3b-9c2d-1e0f9a8b7c6d",
    "timestamp": "2026-12-01T03:00:05Z"
  }
}
```

