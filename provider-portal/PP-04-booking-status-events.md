# PP-04: Booking Status Events (PP → CP push)

**Owner:** Provider Portal (producer) · **Consumer:** Customer Portal
**SRS:** PP-MONEY-S01 ("notify the CP when a room is booked or cancelled, and return the outcomes needed for CP's customer confirmation email"), PP-MONEY-M03, PP-MONEY-U01 · CP-MONEY-S01, CP-MONEY-M02(M) (real-time cancellation notification), CP-MONEY-U02

---

## PP-OP-11 BookingStatusEvent

| Binding | Value |
|---|---|
| Simplex / Medium | PP calls CP's webhook **CP-OP-04** `POST {CP}/api/v1/partner/booking-events` (scope `booking-event:write`, `X-RS-Signature`) |
| Ultimo | PP produces to `rs.booking.events.v1` (key `bookingId`, consumer group `cp-booking-events`) |

CP turns these events into (a) the **confirmation email** (CP-MONEY-S01) and (b) a **real-time in-app notification**, pushed over CP's own WebSocket to its frontend (CP-MONEY-M02).

### Event types
| eventType | Emitted when | Triggered by |
|---|---|---|
| `BOOKING_CONFIRMED` | Receptionist approves | PP frontend |
| `BOOKING_CANCELLED` | Customer (PP-OP-09) or receptionist cancels | PP-OP-09 / PP frontend |
| `RETURN_PAYMENT_UPDATED` | The payout (Medium) or refund (Ultimo) changes status: `PENDING → SUCCEEDED/FAILED` | Payment gateway webhook to PP |
| `ESCROW_RELEASE_UPDATED` | Escrow release changes status: `RELEASE_PENDING → RELEASED/RELEASE_FAILED` (Ultimo) | Gateway webhook to PP |
| `BOOKING_COMPLETED` | A confirmed stay's checkout date has passed (nightly job, 02:00 branch local time) | Scheduler |

### Payload
| Field | Type | Required | Notes |
|---|---|---|---|
| eventId | string (UUID) | yes | **CP de-duplicates on this** (delivery is at-least-once) |
| eventType | string | yes | See above |
| occurredAt | string | yes | UTC |
| sequence | integer | yes | Increases per `bookingId`. CP ignores events with a lower sequence than the last one applied. |
| booking | BookingSummary | yes | Full current state, so CP never needs a follow-up call |
| emailData | object | for `BOOKING_CONFIRMED` / `BOOKING_CANCELLED` | Content for CP's email: `{ bookingCode, providerName, branchName, branchAddress, branchPhone, roomName, checkInDate, checkOutDate, checkInTime, quantity, adults, children, total }` |
| message | string | no | Short receptionist note shown to the customer, e.g. a rejection reason |

### Example: confirmation (Ultimo escrow, funds released)
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
    "roomId": "3f2e1d0c-0000-4000-8000-000000000301",
    "providerName": "Thu Bon Family Stays",
    "branchName": "Riverside Homestay Hoi An",
    "roomName": "Garden Single Room",
    "checkInDate": "2027-04-10",
    "checkOutDate": "2027-04-13",
    "quantity": 2, "adults": 3, "children": 1,
    "priceBreakdown": { "nights": 3, "quantity": 2, "unitPricePerNight": { "amountMinor": 2500, "currency": "USD" }, "subtotal": { "amountMinor": 15000, "currency": "USD" }, "discount": { "discountPackageId": "d15c0a7e-0000-4000-8000-000000000015", "name": "Premium 15% Off", "type": "PERCENTAGE", "value": 15, "amount": { "amountMinor": 2250, "currency": "USD" } }, "total": { "amountMinor": 12750, "currency": "USD" } },
    "payment": { "mode": "ESCROW", "originalPaymentReference": "pi_3QAbCdTEST0001", "escrowStatus": "RELEASED", "releaseReference": "tr_1QXyzTEST0001", "returnPaymentStatus": "NOT_REQUIRED" },
    "createdAt": "2026-12-01T03:02:12Z",
    "updatedAt": "2026-12-01T09:15:40Z"
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
    "quantity": 2, "adults": 3, "children": 1,
    "total": { "amountMinor": 12750, "currency": "USD" }
  }
}
```

### Example: cancelled by the receptionist, Medium payout pending, then failed
```json
{
  "eventId": "11112222-0000-4000-8000-000000000002",
  "eventType": "BOOKING_CANCELLED",
  "occurredAt": "2026-12-02T02:00:00Z",
  "sequence": 2,
  "booking": {
    "bookingId": "8c9d0e1f-0000-4000-8000-000000000802",
    "bookingCode": "RS-TH-9KD2M",
    "status": "CANCELLED",
    "cancellation": { "cancelledBy": "RECEPTIONIST", "reason": "Room under maintenance", "cancelledAt": "2026-12-02T02:00:00Z" },
    "payment": { "mode": "DIRECT", "originalPaymentReference": "PAYPAL-CAPTURE-7XK12345AB", "returnPaymentStatus": "PENDING", "returnPaymentReference": "PAYOUT-BATCH-5UXD2EXAMPLE" }
  },
  "message": "We are sorry, the room is under maintenance on your dates."
}
```
```json
{
  "eventId": "11112222-0000-4000-8000-000000000003",
  "eventType": "RETURN_PAYMENT_UPDATED",
  "occurredAt": "2026-12-02T02:03:30Z",
  "sequence": 3,
  "booking": {
    "bookingId": "8c9d0e1f-0000-4000-8000-000000000802",
    "status": "CANCELLED",
    "payment": {
      "mode": "DIRECT",
      "originalPaymentReference": "PAYPAL-CAPTURE-7XK12345AB",
      "returnPaymentStatus": "FAILED",
      "returnPaymentReference": "PAYOUT-BATCH-5UXD2EXAMPLE",
      "failureCause": "RECEIVER_UNREGISTERED: the receiver email is not linked to a PayPal sandbox account"
    }
  }
}
```
*(The `booking` objects are abridged above for readability. Real events always carry the full `BookingSummary`.)*

### Kafka envelope (Ultimo)

On `rs.booking.events.v1` the event above is the `payload` of the standard envelope. Events are one-way, so there is no `replyTo`; `correlationId` is the `bookingId`, which groups every event of one booking.

```json
{
  "messageId": "11112222-0000-4000-8000-0000000000e1",
  "correlationId": "8c9d0e1f-0000-4000-8000-000000000801",
  "type": "BOOKING_CONFIRMED",
  "schemaVersion": "1.0",
  "source": "PP",
  "timestamp": "2026-12-01T09:15:40Z",
  "payload": {
    "eventId": "11112222-0000-4000-8000-000000000001",
    "eventType": "BOOKING_CONFIRMED",
    "occurredAt": "2026-12-01T09:15:40Z",
    "sequence": 2,
    "booking": { "bookingId": "8c9d0e1f-0000-4000-8000-000000000801", "status": "CONFIRMED" }
  }
}
```

The `booking` object is abridged here; see the full example above.

### Delivery guarantees
| Concern | Webhook (Simplex/Medium) | Kafka (Ultimo) |
|---|---|---|
| Guarantee | At-least-once | At-least-once (`acks=all`, idempotent producer) |
| Retry by PP | 6 attempts: 1 s, 5 s, 30 s, 2 min, 10 min, 1 h. Each event is written to a PP **outbox** table first (transactional outbox). | Outbox relay publishes. The broker handles redelivery. |
| Success criterion | CP returns `2xx` within 5 s | Offset committed by CP after processing |
| Ordering | `sequence` per booking | Partition key `bookingId` + `sequence` |
| Duplicates | CP ignores a repeated `eventId` (`200` with `"duplicate": true`) | CP ignores a repeated `eventId` |
| Give-up | After the last attempt: marked `UNDELIVERED`, shown on the PP admin screen, re-sendable manually | DLQ `rs.booking.events.v1.dlq` |
