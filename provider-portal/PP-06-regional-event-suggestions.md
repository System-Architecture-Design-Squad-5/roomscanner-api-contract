# PP-06: Regional Event Suggestions (provided by PP)

**Owner:** Provider Portal (suggestion and publication) · **Consumer:** Customer Portal (owns events, favorites, topics and display)
**SRS:** PP-EVENT-S01, S02, M01, U01, U02 · CP-EVENT-M01, M02, M03, U01, U02, U03 · Decision D-12

PP **does not** administer events or store favorites as authoritative data (PP-EVENT-S01). It only receives the event and city information it needs, and returns the **two most highly rated accommodation providers** in the event's city.

## Shared object: `EventSuggestion`
Fields required by CP-EVENT-M02 / PP-EVENT-S02: price per night, logo URL, type, name, overall rating, and the accommodation provider's name.

| Field | Type | Required | Notes |
|---|---|---|---|
| rank | integer | yes | 1 or 2 |
| providerId | string | yes | |
| providerName | string | yes | "Accommodation provider's name" (company) |
| branchId | string | yes | |
| name | string | yes | Accommodation (branch) name |
| type | ProviderCategory | yes | |
| logoUrl | string | yes | |
| pricePerNight | Money | yes | Lowest available price for the event dates |
| overallRating | number | no | From CP statistics. Omitted when there are no reviews. |
| totalReviews | integer | yes | |

## Shared object: `EventInfo` (supplied by CP)
| Field | Type | Required | Notes |
|---|---|---|---|
| eventId | string | yes | CP ID |
| name | string | yes | e.g. "Hùng Kings' Temple Festival" |
| summary | string | yes | ≤ 300 characters, for the notification |
| locationName | string | yes | e.g. "Hùng Kings' Temple, Viet Tri City" |
| city | string | yes | Must match PP city naming (normalised, case-insensitive) |
| country | string | yes | ISO alpha-2 |
| timeZone | string | yes | IANA |
| startDate / endDate | string (date) | yes | Local to the event |
| searchRoute | string | yes | CP **frontend** route that opens the city search (CP owns the UI), e.g. `/search?city=Viet%20Tri&country=VN` |

---

## PP-OP-12 RequestEventSuggestions (Simplex REST, Medium WebSocket)

### Simplex binding (PP-EVENT-S02): REST
`POST /api/v1/partner/event-suggestions` · scope `event-suggestion:write`

Request:
| Field | Type | Required | Notes |
|---|---|---|---|
| requestId | string (UUID) | yes | |
| favoriteId | string | yes | CP favorite record |
| customerId | string | yes | Echoed back so CP can route the notification. PP does not store it as authoritative. |
| event | EventInfo | yes | |

Response `200`:
| Field | Type | Notes |
|---|---|---|
| requestId / favoriteId / customerId | string | echo |
| event | EventInfo | echo |
| suggestions | EventSuggestion[] | 0-2 items, ranked (D-12) |
| reason | string | When fewer than 2: `NO_AVAILABLE_PROVIDERS_IN_CITY` or `ONLY_ONE_AVAILABLE_PROVIDER` |
| generatedAt | string | UTC |

**Request**

```json
{
  "requestId": "2e9b0c11-0000-4000-8000-000000000a01",
  "favoriteId": "fa7e0000-0000-4000-8000-000000000b01",
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
  "event": {
    "eventId": "e7e70000-0000-4000-8000-000000000c01",
    "name": "Hùng Kings' Temple Festival",
    "summary": "National festival honouring the Hùng Kings with processions, folk games and xoan singing.",
    "locationName": "Hùng Kings' Temple, Viet Tri City, Phu Tho",
    "city": "Viet Tri",
    "country": "VN",
    "timeZone": "Asia/Ho_Chi_Minh",
    "startDate": "2027-04-12",
    "endDate": "2027-04-18",
    "searchRoute": "/search?city=Viet%20Tri&country=VN&checkIn=2027-04-12&checkOut=2027-04-13"
  }
}
```
**Response `200`**

```json
{
  "requestId": "2e9b0c11-0000-4000-8000-000000000a01",
  "favoriteId": "fa7e0000-0000-4000-8000-000000000b01",
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
  "event": {
    "eventId": "e7e70000-0000-4000-8000-000000000c01",
    "name": "Hùng Kings' Temple Festival",
    "summary": "National festival honouring the Hùng Kings with processions, folk games and xoan singing.",
    "locationName": "Hùng Kings' Temple, Viet Tri City, Phu Tho",
    "city": "Viet Tri",
    "country": "VN",
    "timeZone": "Asia/Ho_Chi_Minh",
    "startDate": "2027-04-12",
    "endDate": "2027-04-18",
    "searchRoute": "/search?city=Viet%20Tri&country=VN&checkIn=2027-04-12&checkOut=2027-04-13"
  },
  "suggestions": [
    {
      "rank": 1,
      "providerId": "5b1c2d3e-0000-4000-8000-000000000170",
      "providerName": "Phu Tho Tourism JSC",
      "branchId": "9a8b7c6d-0000-4000-8000-000000000270",
      "name": "Saigon Phu Tho Hotel",
      "type": "HOTEL",
      "logoUrl": "https://cdn.roomscanner.local/logos/sgpt_256.webp",
      "pricePerNight": {
        "amountMinor": 4200,
        "currency": "USD"
      },
      "overallRating": 4.7,
      "totalReviews": 63
    },
    {
      "rank": 2,
      "providerId": "5b1c2d3e-0000-4000-8000-000000000171",
      "providerName": "Song Lo Homes",
      "branchId": "9a8b7c6d-0000-4000-8000-000000000271",
      "name": "Song Lo Riverside Homestay",
      "type": "HOMESTAY",
      "logoUrl": "https://cdn.roomscanner.local/logos/songlo_256.webp",
      "pricePerNight": {
        "amountMinor": 1800,
        "currency": "USD"
      },
      "overallRating": 4.5,
      "totalReviews": 22
    }
  ],
  "generatedAt": "2027-02-15T04:00:01Z"
}
```

### Medium binding (PP-EVENT-M01): real-time socket
- **Protocol:** STOMP 1.2 over WebSocket. Endpoint `wss://pp-gateway.<squad>.roomscanner.local/ws/partner`. The partner token goes in the STOMP `CONNECT` header `Authorization: Bearer <token>`. Heartbeats are 10 s / 10 s.
- **CP → PP:** `SEND /app/event-suggestions.request` with the same body as the REST request.
- **PP → CP:** CP subscribes to `/user/queue/event-suggestions`. PP pushes the same body as the REST response **as soon as it is ready**.
- **Reconnect:** CP reconnects with exponential backoff (1 s → 30 s). Requests not answered within 10 s are re-sent with the same `requestId`. PP de-duplicates on `requestId`.
- CP then pushes its own in-app notification to the customer's browser (CP-EVENT-M03). That CP-internal socket is not part of this contract.

**Example frames** (`^@` marks the STOMP NULL terminator; bodies are abridged versions of the REST request and response above):

```text
CONNECT
accept-version:1.2
host:pp-gateway.<squad>.roomscanner.local
heart-beat:10000,10000
Authorization:Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6InBwLTIwMjYtMTEifQ...

^@
SUBSCRIBE
id:sub-0
destination:/user/queue/event-suggestions

^@
SEND
destination:/app/event-suggestions.request
content-type:application/json
x-correlation-id:2e9b0c11-0000-4000-8000-000000000a01

{"requestId":"2e9b0c11-0000-4000-8000-000000000a01","favoriteId":"fa7e0000-0000-4000-8000-000000000b01","customerId":"7d1e2f30-0000-4000-8000-000000000901","event":{"eventId":"e7e70000-0000-4000-8000-000000000c01","city":"Viet Tri","country":"VN","...":"..."}}^@
```

```text
MESSAGE
subscription:sub-0
message-id:pp-msg-000182
destination:/user/queue/event-suggestions
content-type:application/json
x-correlation-id:2e9b0c11-0000-4000-8000-000000000a01

{"requestId":"2e9b0c11-0000-4000-8000-000000000a01","favoriteId":"fa7e0000-0000-4000-8000-000000000b01","suggestions":[{"rank":1,"name":"Saigon Phu Tho Hotel","...":"..."},{"rank":2,"name":"Song Lo Riverside Homestay","...":"..."}],"generatedAt":"2027-02-15T04:00:01Z"}^@
```

Errors are pushed to `/user/queue/errors` with the standard error body (`01-conventions.md` Section 5) and the same `x-correlation-id` header.

---

## PP-OP-13 PublishEventNotification (Ultimo, Kafka)

**Flow (CP-EVENT-U01 to U03, PP-EVENT-U01, U02):**
```
CP admin/customer           Kafka (Machine 4)                    PP event-service
favorites event ──► rs.event.favorite.v1 (CP-created) ──► consume CP-OP-05
                                                         compute notificationWindowStart (D-12)
                                                         ├─ within window → publish now
                                                         └─ earlier → persist schedule (event_notification_schedule), publish at window start
                     rs.event.notification.v1 (CP-created) ◄── publish REGIONAL_EVENT_NOTIFICATION (fresh top-2 at publish time)
CP dedicated consumer ◄─ filters: still favorited AND customer is active Premium → in-app real-time notification
```

- **Topic:** `rs.event.notification.v1` (**created by CP**, PP is the only producer), key `customerId`, type `REGIONAL_EVENT_NOTIFICATION`.
- **Envelope:** `04-kafka.md` §1 (no `replyTo`; this is a one-way publication).

### Payload
| Field | Type | Required | Notes |
|---|---|---|---|
| notificationId | string (UUID) | yes | CP de-duplicates on this |
| favoriteId | string | yes | |
| customerId | string | yes | |
| trigger | string | yes | `IMMEDIATE_WITHIN_WINDOW`, `IMMEDIATE_ONGOING`, or `SCHEDULED_TWO_MONTH` |
| notificationWindowStart | string (date) | yes | e.g. `2027-02-11` |
| event | EventInfo | yes | |
| suggestions | EventSuggestion[] | yes | 0-2 |
| searchLink | string | yes | = `event.searchRoute`. Opens CP's search UI for **all** providers in the event city (CP-EVENT-M03). |
| publishedAt | string | yes | UTC |

```json
{
  "messageId": "3e550000-0000-4000-8000-000000000e01",
  "correlationId": "fa7e0000-0000-4000-8000-000000000b02",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "type": "REGIONAL_EVENT_NOTIFICATION",
  "schemaVersion": "1.0",
  "source": "PP",
  "timestamp": "2027-02-10T17:00:00Z",
  "payload": {
    "notificationId": "40710000-0000-4000-8000-000000000f01",
    "favoriteId": "fa7e0000-0000-4000-8000-000000000b02",
    "customerId": "7d1e2f30-0000-4000-8000-000000000902",
    "trigger": "SCHEDULED_TWO_MONTH",
    "notificationWindowStart": "2027-02-11",
    "event": {
      "eventId": "e7e70000-0000-4000-8000-000000000c01",
      "name": "Hùng Kings' Temple Festival",
      "summary": "National festival honouring the Hùng Kings with processions, folk games and xoan singing.",
      "locationName": "Hùng Kings' Temple, Viet Tri City, Phu Tho",
      "city": "Viet Tri",
      "country": "VN",
      "timeZone": "Asia/Ho_Chi_Minh",
      "startDate": "2027-04-12",
      "endDate": "2027-04-18",
      "searchRoute": "/search?city=Viet%20Tri&country=VN&checkIn=2027-04-12&checkOut=2027-04-13"
    },
    "suggestions": [
      {
        "rank": 1,
        "providerId": "5b1c2d3e-0000-4000-8000-000000000170",
        "providerName": "Phu Tho Tourism JSC",
        "branchId": "9a8b7c6d-0000-4000-8000-000000000270",
        "name": "Saigon Phu Tho Hotel",
        "type": "HOTEL",
        "logoUrl": "https://cdn.roomscanner.local/logos/sgpt_256.webp",
        "pricePerNight": {
          "amountMinor": 4200,
          "currency": "USD"
        },
        "overallRating": 4.7,
        "totalReviews": 63
      },
      {
        "rank": 2,
        "providerId": "5b1c2d3e-0000-4000-8000-000000000171",
        "providerName": "Song Lo Homes",
        "branchId": "9a8b7c6d-0000-4000-8000-000000000271",
        "name": "Song Lo Riverside Homestay",
        "type": "HOMESTAY",
        "logoUrl": "https://cdn.roomscanner.local/logos/songlo_256.webp",
        "pricePerNight": {
          "amountMinor": 1800,
          "currency": "USD"
        },
        "overallRating": 4.5,
        "totalReviews": 22
      }
    ],
    "searchLink": "/search?city=Viet%20Tri&country=VN&checkIn=2027-04-12&checkOut=2027-04-13",
    "publishedAt": "2027-02-10T17:00:00Z"
  }
}
```
*`2027-02-10T17:00:00Z` = 00:00 on 11 Feb 2027 in `Asia/Ho_Chi_Minh`.*

### Timing test cases (SRS worked example, CP-EVENT-U03)
Event start: **12 Apr 2027** → window start **11 Feb 2027** (D-12).

| Customer | Favorited on | Expected trigger | Published at (local) |
|---|---|---|---|
| Tim | 15 Feb 2027 | `IMMEDIATE_WITHIN_WINDOW` | 15 Feb 2027, within seconds |
| Andy | 12 Dec 2026 | `SCHEDULED_TWO_MONTH` | 11 Feb 2027 00:00 |
| Lan | 14 Apr 2027 (event ongoing) | `IMMEDIATE_ONGOING` | immediately |
| Minh | 19 Apr 2027 (event ended) | none | not published |
| Andy (after an admin edits only the description on 1 Jan 2027) | N/A | unchanged | still 11 Feb 2027, no extra notification |

### Reliability
- Schedules are persisted in PP's DB, so they survive restarts. A scheduler runs every minute with a distributed lock. In one database transaction it inserts a due notification into the outbox and marks the schedule `PUBLISHED`; the outbox relay retries Kafka publication until acknowledged. A crash between publication and acknowledgement may cause redelivery with the same `notificationId`.
- The CP consumer is idempotent on `notificationId`. PP never creates another business notification for a `PUBLISHED` schedule; transport retries retain its identity. Re-favoriting creates a new `favoriteId` and a new schedule.
- Eligibility (active Premium, still favorited) is checked by **CP at display time** (CP-EVENT-U02). PP does not hold membership data.
- **Handling CP-OP-05 change types (D-12):**

| `changeType` | PP action |
|---|---|
| `FAVORITE_ADDED` | Compute `notificationWindowStart`; publish now or persist a `SCHEDULED` row |
| `FAVORITE_REMOVED` | Mark that favorite's `SCHEDULED` row `CANCELLED` (no-op if already `PUBLISHED`) |
| `EVENT_DATES_CHANGED` | Recompute every `SCHEDULED` row for the `eventId`; publish now any that fall inside the new window. `PUBLISHED` rows are not re-sent |
| `EVENT_DELETED` | Mark every `SCHEDULED` row for the `eventId` `CANCELLED`; ignore later `FAVORITE_ADDED` for that event |

  Messages are keyed by `eventId`, so one partition preserves their order per event; PP is idempotent on `messageId`.
- **CP Modular Monolith Integration (`PartnerIntegrationModule` → `EventModule`):** CP's dedicated Kafka consumer (`cp-event-notification-consumer`) receives `PP-OP-13` on `rs.event.notification.v1`, invokes `IEventExternalService` (`EventNotificationExternalDto`) to verify active Premium membership and favorite status, persists the notification, pushes it in real time to the customer's browser, and exposes it via `GET /api/v1/customer/notifications/events` and `PATCH /api/v1/customer/notifications/events/{notificationId}/read`.
