# CP-03: Orders and Booking Events (provided by CP)

**Owner:** Customer Portal · **Consumer:** Provider Portal · **Scopes:** `order:write`, `booking-event:write`
**SRS:** PP-MONEY-S01, M03 · CP-MONEY-S01, M02(M) · **Decisions:** D-07, D-08, D-13

Within CP's **Modular Monolith**, `PartnerIntegrationModule` delegates these partner calls to `BookingModule` via `IBookingExternalService` (`OrderUpdateExternalDto`, `BookingEventExternalDto`).

---

## CP-OP-03 UpdateSimulatedOrder (Simplex only)

`PATCH {CP}/api/v1/partner/orders/{orderId}` · `Idempotency-Key` required · **Scope:** `order:write`

| Field | Type | Required | Notes |
|---|---|---|---|
| `action` | string | yes | `COMPLETE` (on receptionist approval) or `CANCEL` (on cancellation) |
| `bookingId` | string (uuid) | yes | |
| `reason` | string | no | |

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

**Errors:** `400 VALIDATION_ERROR` (bad `action` or `bookingId`) · `404 RESOURCE_NOT_FOUND` (unknown order) · `409 STATE_CONFLICT` (already completed or cancelled with a different action) · `503 SERVICE_UNAVAILABLE` (PP retries with the same `Idempotency-Key`) · `401` / `403` / `429` standard partner errors (`common/01-conventions.md`; write limit 30 requests per 60 s).

---

## CP-OP-04 ReceiveBookingEvent (Webhook, Simplex / Medium)

`POST {CP}/api/v1/partner/booking-events` · headers `Authorization`, `X-RS-Signature` · **Scope:** `booking-event:write`

*(Replaced by Kafka topic `rs.booking.events.v1` at Ultimo.)*

- Body: the `BookingStatusEvent` payload from `PP-OP-11`.
- Response `200` within 5 s. Heavy work (emails, real-time WebSocket push) executes asynchronously after acknowledging.
- `401 PARTNER_UNAUTHENTICATED` if the HMAC-SHA256 `X-RS-Signature` or replay window (`|now - t| > 300 s`) is invalid. Any `5xx` or timeout → PP retries (`PP-04` delivery table).
- `400 VALIDATION_ERROR` if the body does not match `BookingStatusEvent` (PP does not retry 4xx except `429`). `429 RATE_LIMITED` (60 requests per 60 s) and `503 SERVICE_UNAVAILABLE` are retried by PP per the `PP-04` delivery table.

**Request (abridged `booking`; full `BookingSummary` and `emailData` match `PP-04`)**

```json
{
  "eventId": "11112222-0000-4000-8000-000000000001",
  "eventType": "BOOKING_CONFIRMED",
  "occurredAt": "2026-12-01T09:15:40Z",
  "sequence": 2,
  "booking": {
    "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
    "bookingCode": "RS-VN-24F7Q",
    "status": "CONFIRMED",
    "customerId": "7d1e2f30-0000-4000-8000-000000000901",
    "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
    "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
    "roomId": "3f2e1d0c-0000-4000-8000-000000000301"
  },
  "emailData": {
    "bookingCode": "RS-VN-24F7Q",
    "providerName": "Thu Bon Family Stays",
    "branchName": "Riverside Homestay Hoi An",
    "branchAddress": "21 Nguyen Phuc Chu, Hoi An, VN",
    "branchPhone": "+842353861234",
    "roomName": "Garden Single Room",
    "checkInDate": "2027-04-10",
    "checkOutDate": "2027-04-13",
    "checkInTime": "14:00",
    "quantity": 2,
    "adults": 3,
    "children": 1,
    "total": { "amountMinor": 12750, "currency": "USD" }
  }
}
```

**Response `200`**

```json
{
  "eventId": "11112222-0000-4000-8000-000000000001",
  "accepted": true,
  "duplicate": false
}
```

**Error `401`**

```json
{
  "error": {
    "code": "PARTNER_UNAUTHENTICATED",
    "message": "Invalid or expired X-RS-Signature webhook header.",
    "requestId": "0c4a7d22-0000-4000-8000-00000000c004",
    "timestamp": "2026-12-01T09:15:42Z"
  }
}
```
