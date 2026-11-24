# CP-04: Regional Event Favorites (provided by CP)

**Owner:** Customer Portal · **Consumer:** Provider Portal · **Transport:** Kafka (Ultimo)
**SRS:** CP-EVENT-U01, U02, U03 · PP-EVENT-U02 · **Decision:** D-12

Customer Portal (`EventModule` + `PartnerIntegrationModule`) is the authoritative owner of regional tourist events and customer favorites. CP creates **both** `rs.event.favorite.v1` and `rs.event.notification.v1` (`CP-EVENT-U01`).

---

## CP-OP-05 EventFavoriteChanged (Ultimo, Kafka)

- **Topic:** `rs.event.favorite.v1` (**created by CP**), partition key `eventId`
- **Envelope:** `common/04-kafka.md` §1 (one-way event: `traceId` required; no `replyTo`, `attempt`, `deadline` or `status`). `correlationId` = `favoriteId` for `FAVORITE_*`, `eventId` for `EVENT_*`.
- **Paired Notification Topic:** `rs.event.notification.v1` (**created by CP**, consumed by CP's dedicated consumer group `cp-event-notification-consumer` per `CP-EVENT-U02`)

### Payload Fields
| Field | Type | Required | Notes |
|---|---|---|---|
| `changeType` | string | yes | `FAVORITE_ADDED`, `FAVORITE_REMOVED`, `EVENT_DATES_CHANGED`, or `EVENT_DELETED` |
| `favoriteId` | string (uuid) | for `FAVORITE_*` | Must be absent for `EVENT_*` |
| `customerId` | string (uuid) | for `FAVORITE_*` | Must be absent for `EVENT_*` |
| `favoritedAt` | string | for `FAVORITE_ADDED` | UTC. PP uses this for immediate vs. 2-month scheduled delivery (`D-12`). |
| `event` | EventInfo | yes | Current event data including `searchRoute` |

### Rules
- CP admins create events only in cities PP serves (`VN`, `SG`), using PP's city naming (`EventInfo.city`, case-insensitive). CP therefore never sends PP an out-of-region event in `CP-OP-05` or `PP-OP-12`; PP needs no extra error for this.
- CP sends `FAVORITE_ADDED` **only** for customers who hold an `ACTIVE` `PREMIUM` membership at favorite time (`CP-EVENT-M01`).
- CP sends `FAVORITE_REMOVED` whenever a customer unfavorites an event (`DELETE /api/v1/customer/events/{eventId}/favorite`), **whatever their current membership**, so PP cancels any pending 2-month scheduled notification. An expired member's favorite must still cancel its schedule.
- CP sends `EVENT_DATES_CHANGED` only when an admin edits `startDate` or `endDate` (`PUT /api/v1/customer/admin/events/{eventId}`). Other metadata edits are not sent (`D-12`).
- CP sends `EVENT_DELETED` when an admin deletes an event (`DELETE /api/v1/customer/admin/events/{eventId}`) so PP cancels all pending scheduled notifications for that `eventId`.
- Membership can expire after `FAVORITE_ADDED` was sent. CP's notification consumer therefore re-checks active Premium and the favorite **at display time** (CP-EVENT-U02, PP-06 §Reliability) and drops the notification otherwise.

### Example (`FAVORITE_ADDED`)

```json
{
  "messageId": "3e550000-0000-4000-8000-000000000d01",
  "correlationId": "fa7e0000-0000-4000-8000-000000000b02",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "type": "FAVORITE_ADDED",
  "schemaVersion": "1.0",
  "source": "CP",
  "timestamp": "2026-12-12T03:00:00Z",
  "payload": {
    "changeType": "FAVORITE_ADDED",
    "favoriteId": "fa7e0000-0000-4000-8000-000000000b02",
    "customerId": "7d1e2f30-0000-4000-8000-000000000902",
    "favoritedAt": "2026-12-12T03:00:00Z",
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
}
```

### Example (`FAVORITE_REMOVED`)

```json
{
  "messageId": "3e550000-0000-4000-8000-000000000d02",
  "correlationId": "fa7e0000-0000-4000-8000-000000000b02",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "type": "FAVORITE_REMOVED",
  "schemaVersion": "1.0",
  "source": "CP",
  "timestamp": "2026-12-15T04:00:00Z",
  "payload": {
    "changeType": "FAVORITE_REMOVED",
    "favoriteId": "fa7e0000-0000-4000-8000-000000000b02",
    "customerId": "7d1e2f30-0000-4000-8000-000000000902",
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
}
```

### Example (`EVENT_DATES_CHANGED`)

```json
{
  "messageId": "3e550000-0000-4000-8000-000000000d03",
  "correlationId": "e7e70000-0000-4000-8000-000000000c01",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "type": "EVENT_DATES_CHANGED",
  "schemaVersion": "1.0",
  "source": "CP",
  "timestamp": "2026-12-20T06:00:00Z",
  "payload": {
    "changeType": "EVENT_DATES_CHANGED",
    "event": {
      "eventId": "e7e70000-0000-4000-8000-000000000c01",
      "name": "Hùng Kings' Temple Festival",
      "summary": "National festival honouring the Hùng Kings with processions, folk games and xoan singing.",
      "locationName": "Hùng Kings' Temple, Viet Tri City, Phu Tho",
      "city": "Viet Tri",
      "country": "VN",
      "timeZone": "Asia/Ho_Chi_Minh",
      "startDate": "2027-04-14",
      "endDate": "2027-04-20",
      "searchRoute": "/search?city=Viet%20Tri&country=VN&checkIn=2027-04-14&checkOut=2027-04-15"
    }
  }
}
```

### Example (`EVENT_DELETED`)

```json
{
  "messageId": "3e550000-0000-4000-8000-000000000d04",
  "correlationId": "e7e70000-0000-4000-8000-000000000c01",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "type": "EVENT_DELETED",
  "schemaVersion": "1.0",
  "source": "CP",
  "timestamp": "2027-01-07T03:00:00Z",
  "payload": {
    "changeType": "EVENT_DELETED",
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
}
```
