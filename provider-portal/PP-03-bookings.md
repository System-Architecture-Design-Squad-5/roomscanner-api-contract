# PP-03: Reservations / Bookings (provided by PP)

**Owner:** Provider Portal (authoritative, primary resource) · **Consumer:** Customer Portal
**Scopes:** `booking:write`, `booking:read`
**SRS:** PP-BOOK-S01, S02, U01 · PP-MONEY-S01, M01, M02, M03, U01 · PP-ROOM-M02 · CP-BOOK-S01, S02 · CP-MONEY-S01, M01, M03, U01, U02, U03, U04 · CP-RATING-S01
**Business rules:** D-05, D-06, D-08, D-09, D-10, D-14

## Booking lifecycle

```
           CreateBooking (PP-OP-06)
                    │  rooms reserved (no automatic expiry)
                    ▼
            PENDING_APPROVAL ──── receptionist approves (PP frontend only) ───► CONFIRMED ── checkOut passed ─► COMPLETED
                    │                                                            │
                    └── customer (PP-OP-09) or receptionist cancels ────────────┴──► CANCELLED  (rooms released, money returned)
```
- **Only the receptionist** (the provider's single account, through the PP frontend) can approve. There is **no** partner API for approval (CP-MONEY-M02(S), PP-MONEY-S01).
- Approval **never** charges the customer again (PP-MONEY-M01, U01).
- Every transition emits a **BookingStatusEvent** (PP-OP-11).

---

## PP-OP-06 CreateBooking

| Binding | Value |
|---|---|
| REST | `POST /api/v1/partner/bookings` (headers: `Idempotency-Key` **required**, `X-Correlation-Id`) |
| Kafka | `rs.booking.request.v1` (`type=CREATE_BOOKING`, key `customerId`) → `rs.booking.response.v1` (`type=CREATE_BOOKING_RESULT`) |
| Redundancy (PP-BOOK-U01) | Served by the primary or the redundant booking instance. With REST, the gateway + service discovery + circuit breaker reroute. With Kafka, the consumer group fails over. Requests are idempotent, so a retry after failover is safe. |

### Request
| Field | Type | Required | Level | Notes |
|---|---|---|---|---|
| quoteId | string | yes | S | From PP-OP-05. PP validates room, dates, quantity and total against it. |
| customer | CustomerSnapshot | yes | S | |
| membership | MembershipSnapshot | yes | S | CP-BOOK-S01 "relevant customer and membership details" |
| roomId | string | yes | S | Must equal the quote's room |
| checkInDate / checkOutDate | string (date) | yes | S | Must equal the quote's dates |
| quantity | integer | yes | S | ≥ 1, equals the quote |
| adults | integer | yes | S | ≥ 1 |
| children | integer | yes | S | ≥ 0. `quantity ≤ adults + children` |
| payment | PaymentInfo | yes | S | Simplex `SIMULATED` · Medium `DIRECT` + `CAPTURED` · Ultimo `ESCROW` + `CAPTURED_HELD` |
| specialRequest | string | no | S | ≤ 500 characters, shown to the receptionist |

### PP validation order
1. Partner auth + scope → 401/403
2. Schema → `400 VALIDATION_ERROR`
3. `quantity ≤ adults + children` → `422 BOOKING_QUANTITY_EXCEEDS_GUESTS`
4. Quote exists, is not expired, and matches → `409 QUOTE_EXPIRED` / `409 QUOTE_MISMATCH`
5. `payment.amount == quote.priceBreakdown.total` → `422 PAYMENT_AMOUNT_MISMATCH`
6. **Medium/Ultimo:** PP verifies the payment **directly with the gateway** (PayPal capture `COMPLETED` / Stripe PaymentIntent `succeeded` and captured, with amount and payee matching). Never trust CP's state alone. → `422 PAYMENT_NOT_CAPTURED`
7. Convert the hold into a reservation inside one DB transaction (row lock on the room inventory) → `409 INSUFFICIENT_AVAILABILITY` (only if the hold was lost)
8. Persist the booking as `PENDING_APPROVAL`, store the `AppliedDiscount` and payment references, and emit no event (creation is acknowledged synchronously).

> Errors at steps 4-7 after a captured payment mean **no booking exists**. CP refunds its own payment (D-14). The error body includes `"refundRequiredByPayer": true`.

### Response `201`
`BookingSummary` (see `02-shared-types.md`), plus:

| Field | Type | Notes |
|---|---|---|
| reviewableFrom | string (date) | = `checkInDate` (D-10) |
| receptionistContact | object | `{ branchName, branchPhone }`, the branch's **public** desk phone |

### Example: Ultimo escrow
**Request**

```json
{
  "quoteId": "1a2b3c4d-0000-4000-8000-000000000501",
  "customer": {
    "customerId": "7d1e2f30-0000-4000-8000-000000000901",
    "email": "tim.nguyen@example.com",
    "phone": "+84901234567",
    "countryOfResidence": "VN"
  },
  "membership": {
    "tier": "PREMIUM",
    "status": "ACTIVE",
    "validUntil": "2027-08-01T00:00:00Z"
  },
  "roomId": "3f2e1d0c-0000-4000-8000-000000000301",
  "checkInDate": "2027-04-10",
  "checkOutDate": "2027-04-13",
  "quantity": 2,
  "adults": 3,
  "children": 1,
  "payment": {
    "mode": "ESCROW",
    "gateway": "STRIPE_SANDBOX",
    "orderId": "55aa66bb-0000-4000-8000-000000000701",
    "paymentReference": "pi_3QAbCdTEST0001",
    "chargeReference": "ch_3QAbCdTEST0001",
    "state": "CAPTURED_HELD",
    "amount": {
      "amountMinor": 12750,
      "currency": "USD"
    },
    "paidAt": "2026-12-01T03:02:10Z"
  },
  "specialRequest": "Late arrival around 22:00"
}
```
**Response `201`**

```json
{
  "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
  "bookingCode": "RS-VN-24F7Q",
  "status": "PENDING_APPROVAL",
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
  "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
  "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
  "roomId": "3f2e1d0c-0000-4000-8000-000000000301",
  "providerName": "Thu Bon Family Stays",
  "branchName": "Riverside Homestay Hoi An",
  "roomName": "Garden Single Room",
  "checkInDate": "2027-04-10",
  "checkOutDate": "2027-04-13",
  "quantity": 2,
  "adults": 3,
  "children": 1,
  "priceBreakdown": {
    "nights": 3,
    "quantity": 2,
    "unitPricePerNight": {
      "amountMinor": 2500,
      "currency": "USD"
    },
    "subtotal": {
      "amountMinor": 15000,
      "currency": "USD"
    },
    "discount": {
      "discountPackageId": "d15c0a7e-0000-4000-8000-000000000015",
      "name": "Premium 15% Off",
      "type": "PERCENTAGE",
      "value": 15,
      "amount": {
        "amountMinor": 2250,
        "currency": "USD"
      }
    },
    "total": {
      "amountMinor": 12750,
      "currency": "USD"
    }
  },
  "payment": {
    "mode": "ESCROW",
    "originalPaymentReference": "pi_3QAbCdTEST0001",
    "escrowStatus": "HELD",
    "returnPaymentStatus": "NOT_REQUIRED"
  },
  "reviewableFrom": "2027-04-10",
  "receptionistContact": {
    "branchName": "Riverside Homestay Hoi An",
    "branchPhone": "+842353861234"
  },
  "createdAt": "2026-12-01T03:02:12Z",
  "updatedAt": "2026-12-01T03:02:12Z"
}
```

### Variants by level
| Level | `payment` sent by CP | What PP does |
|---|---|---|
| Simplex | `{ "mode": "SIMULATED", "gateway": "NONE", "orderId": "o-…", "state": "SIMULATED_ISSUED", "amount": {…} }` | Stores the booking. On receptionist approval or cancellation, PP **completes or cancels the simulated order** via CP-OP-03 (PP-MONEY-S01). |
| Medium | `{ "mode": "DIRECT", "gateway": "PAYPAL_SANDBOX", "orderId": "o-…", "paymentReference": "<PayPal capture ID>", "state": "CAPTURED", ... }` | Verifies the capture landed in the provider's merchant account, then reserves. Approval makes no second charge. |
| Ultimo | as in the example | Verifies the capture is held in the platform balance. On approval it releases the funds; on cancellation it refunds them (PP-05). |

### Errors
| HTTP | Code | `refundRequiredByPayer` |
|---|---|---|
| 400 | `VALIDATION_ERROR` | true if already paid |
| 422 | `BOOKING_QUANTITY_EXCEEDS_GUESTS` | true if already paid |
| 409 | `QUOTE_EXPIRED` / `QUOTE_MISMATCH` | true if already paid |
| 422 | `PAYMENT_AMOUNT_MISMATCH` / `PAYMENT_NOT_CAPTURED` | true if any amount was captured |
| 409 | `INSUFFICIENT_AVAILABILITY` | true if already paid |
| 409 | `IDEMPOTENCY_CONFLICT` | false (the original request still stands) |
| 503 | `SERVICE_UNAVAILABLE` | false. **Retry with the same Idempotency-Key**; the booking may already exist. |

---

## PP-OP-07 GetBooking

| Binding | Value |
|---|---|
| REST | `GET /api/v1/partner/bookings/{bookingId}?customerId={customerId}` |
| Kafka | `rs.booking.request.v1` (`type=GET_BOOKING`) |

The `customerId` is required, and must own the booking (otherwise `404`, so the booking's existence is not revealed). The response is a `BookingSummary`, so CP can always reconcile with PP's actual state (CP-MONEY-U02).

### Request

| Field | In | Type | Required | Notes |
|---|---|---|---|---|
| bookingId | path | string (uuid) | yes | PP booking reference |
| customerId | query | string (uuid) | yes | Must own the booking |

**Request (Kafka payload, `type=GET_BOOKING`)**

```json
{
  "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
  "customerId": "7d1e2f30-0000-4000-8000-000000000901"
}
```

### Response `200`: `BookingSummary`

```json
{
  "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
  "bookingCode": "RS-VN-24F7Q",
  "status": "PENDING_APPROVAL",
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
  "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
  "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
  "roomId": "3f2e1d0c-0000-4000-8000-000000000301",
  "providerName": "Thu Bon Family Stays",
  "branchName": "Riverside Homestay Hoi An",
  "roomName": "Garden Single Room",
  "checkInDate": "2027-04-10",
  "checkOutDate": "2027-04-13",
  "quantity": 2,
  "adults": 3,
  "children": 1,
  "priceBreakdown": {
    "nights": 3,
    "quantity": 2,
    "unitPricePerNight": { "amountMinor": 2500, "currency": "USD" },
    "subtotal": { "amountMinor": 15000, "currency": "USD" },
    "discount": { "discountPackageId": "d15c0a7e-0000-4000-8000-000000000015", "name": "Premium 15% Off", "type": "PERCENTAGE", "value": 15, "amount": { "amountMinor": 2250, "currency": "USD" } },
    "total": { "amountMinor": 12750, "currency": "USD" }
  },
  "payment": {
    "mode": "ESCROW",
    "originalPaymentReference": "pi_3QAbCdTEST0001",
    "escrowStatus": "HELD",
    "returnPaymentStatus": "NOT_REQUIRED"
  },
  "createdAt": "2026-12-01T03:02:12Z",
  "updatedAt": "2026-12-01T03:02:12Z"
}
```

### Errors

| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | `customerId` missing or not a UUID |
| 401 / 403 | `PARTNER_UNAUTHENTICATED` / `PARTNER_FORBIDDEN` | Token missing, invalid, or without `booking:read` |
| 404 | `RESOURCE_NOT_FOUND` | Unknown booking, or not owned by `customerId` |
| 503 | `SERVICE_UNAVAILABLE` | Booking service unavailable on every instance |

---

## PP-OP-08 ListCustomerBookings

Provides the data CP needs to show its three booking groups (CP-BOOK-S02(b), D-09).

| Binding | Value |
|---|---|
| REST | `GET /api/v1/partner/customers/{customerId}/bookings` |
| Kafka | `rs.booking.request.v1` (`type=LIST_BOOKINGS`) |

**Request (Kafka payload, `type=LIST_BOOKINGS`)**

```json
{
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
  "status": ["PENDING_APPROVAL", "CONFIRMED", "COMPLETED"],
  "sort": "CHECK_IN_DESC",
  "limit": 10
}
```

| Query field | Type | Required | Notes |
|---|---|---|---|
| status | BookingStatus[] | no | Default: all |
| stayFrom / stayTo | string (date) | no | Filter on `checkInDate` |
| sort | string | no | `CHECK_IN_DESC` (default), `CREATED_DESC` |
| limit / cursor | | no | |

Response: `{ "items": BookingSummary[], "pageInfo": {...} }`

```json
{
  "items": [
    {
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
      "priceBreakdown": { "nights": 3, "quantity": 2, "unitPricePerNight": { "amountMinor": 2500, "currency": "USD" }, "subtotal": { "amountMinor": 15000, "currency": "USD" }, "total": { "amountMinor": 12750, "currency": "USD" } },
      "payment": { "mode": "ESCROW", "originalPaymentReference": "pi_3QAbCdTEST0001", "escrowStatus": "RELEASED", "releaseReference": "tr_1QXyzTEST0001", "returnPaymentStatus": "NOT_REQUIRED" },
      "createdAt": "2026-12-01T03:02:12Z",
      "updatedAt": "2026-12-01T09:15:40Z"
    }
  ],
  "pageInfo": { "limit": 10, "hasMore": false }
}
```
### Errors

| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Unknown `status` value, `stayTo` before `stayFrom`, or `limit` outside 1-50 |
| 400 | `INVALID_CURSOR` | Cursor tampered with or expired |
| 401 / 403 | `PARTNER_UNAUTHENTICATED` / `PARTNER_FORBIDDEN` | Token missing, invalid, or without `booking:read` |
| 503 | `SERVICE_UNAVAILABLE` | Booking service unavailable |

An unknown `customerId` is not an error: the response is `200` with an empty `items` array, so customer existence is not disclosed.

> **Shard routing (PP-SEARCH-U01 style):** Reservations are sharded by **`branch country`**, with a secondary index table `customer_booking_index (customerId → bookingId, shardId)` cached in Redis. A list query touches only the shards that hold that customer's bookings.

---

## PP-OP-09 CancelBookingByCustomer

| Binding | Value |
|---|---|
| REST | `POST /api/v1/partner/bookings/{bookingId}/cancellations` (headers: `Idempotency-Key` **required**) |
| Kafka | `rs.booking.request.v1` (`type=CANCEL_BOOKING`, key `bookingId`) |

On Kafka, `bookingId` moves from the path into the payload, and the envelope's `correlationId` plays the role of the `Idempotency-Key`.

**Request (Kafka payload, `type=CANCEL_BOOKING`)**

```json
{
  "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
  "reason": "Change of travel plans"
}
```

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| customerId | string | yes | Must own the booking |
| reason | string | no | ≤ 500 characters |

### Response `200`
A `BookingSummary` with `status=CANCELLED`, the `cancellation` filled, and `payment.returnPaymentStatus` usually `PENDING`. The **final** return outcome arrives later as a `RETURN_PAYMENT_UPDATED` event (PP-OP-11).

**Request**

```json
{
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
  "reason": "Change of travel plans"
}
```
**Response `200` (abridged; all BookingSummary fields are present)**

```json
{
  "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
  "status": "CANCELLED",
  "cancellation": {
    "cancelledBy": "CUSTOMER",
    "reason": "Change of travel plans",
    "cancelledAt": "2026-12-03T05:00:00Z"
  },
  "payment": {
    "mode": "ESCROW",
    "originalPaymentReference": "pi_3QAbCdTEST0001",
    "escrowStatus": "HELD",
    "returnPaymentStatus": "PENDING"
  },
  "updatedAt": "2026-12-03T05:00:00Z"
}
```

### Errors
| HTTP | Code | When |
|---|---|---|
| 404 | `RESOURCE_NOT_FOUND` | Unknown booking, or not owned by `customerId` |
| 409 | `STATE_CONFLICT` | Already `CANCELLED` or `COMPLETED`. A repeat with the same `Idempotency-Key` returns the original `200` instead. |
| 409 | `CANCELLATION_WINDOW_CLOSED` | Today ≥ `checkInDate` (D-08) |

---

## PP-OP-10 GetReviewEligibility

| Binding | Value |
|---|---|
| REST | `GET /api/v1/partner/bookings/{bookingId}/review-eligibility?customerId={customerId}` |
| Kafka | `rs.booking.request.v1` (`type=GET_ELIGIBILITY`) |

**Request (Kafka payload, `type=GET_ELIGIBILITY`)**

```json
{
  "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
  "customerId": "7d1e2f30-0000-4000-8000-000000000901"
}
```

### Response `200`
| Field | Type | Notes |
|---|---|---|
| bookingId | string | |
| customerId | string | |
| providerId | string | The review target. Reviews are per **provider**, not per room. |
| branchId | string | |
| stayStartDate / stayEndDate | string (date) | |
| reviewableFrom | string (date) | = stayStartDate |
| bookingStatus | BookingStatus | |
| eligible | boolean | D-10 |
| reason | string | When `eligible=false`: `BEFORE_STAY_START`, `BOOKING_CANCELLED`, `NOT_CONFIRMED`, or `NOT_BOOKING_OWNER` |
| evaluatedAt | string | UTC |

```json
{
  "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
  "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
  "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
  "stayStartDate": "2027-04-10",
  "stayEndDate": "2027-04-13",
  "reviewableFrom": "2027-04-10",
  "bookingStatus": "CONFIRMED",
  "eligible": false,
  "reason": "BEFORE_STAY_START",
  "evaluatedAt": "2027-04-09T10:00:00Z"
}
```
### Errors

| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | `customerId` missing or not a UUID |
| 401 / 403 | `PARTNER_UNAUTHENTICATED` / `PARTNER_FORBIDDEN` | Token missing, invalid, or without `booking:read` |
| 404 | `RESOURCE_NOT_FOUND` | Unknown booking |

A booking owned by a different customer returns `200` with `eligible=false` and `reason=NOT_BOOKING_OWNER`, so CP can show a precise message without PP disclosing booking details (only the IDs in the request are echoed).

CP must call this **at review creation**. CP-RATING-S01 evidence requires that pre-stay creation is rejected. CP may cache an `eligible=true` result for the booking.
