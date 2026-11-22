# CP-04: Regional Event Favorites (provided by CP)

**Owner:** Customer Portal · **Consumer:** Provider Portal · **Transport:** Kafka (Ultimo)
**SRS:** CP-EVENT-U01, U02, U03 · PP-EVENT-U02 · **Decision:** D-12

Customer Portal (`EventModule` + `PartnerIntegrationModule`) is the authoritative owner of regional tourist events and customer favorites. CP creates **both** `rs.event.favorite.v1` and `rs.event.notification.v1` (`CP-EVENT-U01`).

---

## CP-OP-05 EventFavoriteChanged (Ultimo, Kafka)

- **Topic:** `rs.event.favorite.v1` (**created by CP**), partition key `eventId`
- **Paired Notification Topic:** `rs.event.notification.v1` (**created by CP**, consumed by CP's dedicated consumer group `cp-event-notification-consumer` per `CP-EVENT-U02`)

### Payload Fields
| Field | Type | Required | Notes |
|---|---|---|---|
| `changeType` | string | yes | `FAVORITE_ADDED`, `FAVORITE_REMOVED`, or `EVENT_DATES_CHANGED` |
| `favoriteId` | string (uuid) | for `FAVORITE_*` | |
| `customerId` | string (uuid) | for `FAVORITE_*` | |
| `favoritedAt` | string | for `FAVORITE_ADDED` | UTC. PP uses this for immediate vs. 2-month scheduled delivery (`D-12`). |
| `event` | EventInfo | yes | Current event data including `searchRoute` |

### Rules
- CP sends `FAVORITE_ADDED` **only** for customers who hold an `ACTIVE` `PREMIUM` membership at favorite time (`CP-EVENT-M01`).
- CP sends `FAVORITE_REMOVED` when an active Premium customer unfavorites an event (`DELETE /api/v1/customer/events/{eventId}/favorite`) so PP cancels any pending 2-month scheduled notification.
- CP sends `EVENT_DATES_CHANGED` only when an admin edits `startDate` or `endDate` (`PUT /api/v1/customer/admin/events/{eventId}`). Other metadata edits are not sent (`D-12`).

### Example (`FAVORITE_ADDED`)

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
