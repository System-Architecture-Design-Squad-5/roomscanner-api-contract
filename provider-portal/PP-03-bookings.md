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
3. Look up the durable idempotency record by authenticated partner, `CREATE_BOOKING` and the HTTP or Kafka idempotency key. Do this **before** checking quote expiry. Same key and normalized body: replay the committed result. Different body: `409 IDEMPOTENCY_CONFLICT`. In flight or uncertain: retryable `503 SERVICE_UNAVAILABLE` with `refundRequiredByPayer=false`.
4. Check `(partner, payment.orderId)`, `quoteId` and `(gateway, paymentReference)`. Each can bind to only one booking, even after workflow archiving. The same business request with another key or transport returns the existing booking. If the input changed, return `409 ORDER_ALREADY_BOUND`, `QUOTE_ALREADY_CONSUMED` or `PAYMENT_ALREADY_BOUND`; reconcile the original order instead of refunding an already-bound payment.
5. Validate `quantity ≤ adults + children`, occupancy, and the quote's customer, room, dates, quantity, adult/child counts and payment mode. The quote must be active, unconsumed and owned by `customer.customerId`. Failure → `422 BOOKING_QUANTITY_EXCEEDS_GUESTS`, `422 OCCUPANCY_EXCEEDED`, `409 QUOTE_EXPIRED` or `409 QUOTE_MISMATCH`.
6. If the quote applied a Premium discount, call CP-OP-02 again and require active Premium at booking creation (D-06). Membership expiry/change → `409 MEMBERSHIP_ELIGIBILITY_CHANGED`; an unavailable membership service → retryable `503 MEMBERSHIP_VERIFICATION_UNAVAILABLE`. Never silently remove the discount or charge a supplement after capture. Terminal loss of eligibility requires a new quote, and compensation (by CP or, at Medium, by PP) only after rejection is durable (D-14).
7. Require `payment.amount` (amount **and currency**) to equal the quote total. At Medium/Ultimo, verify the payment directly with the configured gateway. Bind gateway metadata to `quoteId`, `customerId` and CP `orderId`; verify captured amount/currency and that the payment has not been refunded or bound elsewhere. For DIRECT, verify the provider merchant as payee. For ESCROW, verify the shared squad platform owns the PaymentIntent, `chargeReference` is that intent's captured charge, and the intended connected provider matches the quote (PP-05). Failure → `422 PAYMENT_AMOUNT_MISMATCH`, `PAYMENT_REFERENCE_MISMATCH` or `PAYMENT_NOT_CAPTURED`. Never trust the submitted state alone.
8. In the booking service's database, lock the quote and inventory rows. Recheck expiry, capacity and uniqueness before converting the hold to a reservation. In that same transaction, consume the quote and save the `PENDING_APPROVAL` booking, discount snapshot, CP order and payment bindings, and idempotency outcome. Unique constraints protect against concurrent requests with different keys. Do not write to another service's tables in this transaction. If the hold or capacity is gone, return `409 INSUFFICIENT_AVAILABILITY`.
9. Return the committed booking; creation is acknowledged by the response. Subsequent lifecycle transitions use the transactional outbox. Booking-service replicas use the same authoritative booking data and uniqueness constraints.

**If booking creation fails after capture:** PP must verify that the payment and order are unbound and record a durable rejection before either team returns the money. [D-14](../common/03-agreed-decisions.md#d-14-booking-rejected-after-payment-was-captured) defines which team acts and how PP records the quote, order and payment so none can be reused. A schema or auth error, timeout, in-flight result or duplicate binding is not enough to authorize a refund. Retry an uncertain write with the original key or [look up the CP order](#pp-op-08-listcustomerbookings).

Only unused quote holds expire. `PENDING_APPROVAL` bookings do not expire automatically (`PP-BOOK-S02`).

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
| Medium | `{ "mode": "DIRECT", "gateway": "PAYPAL_SANDBOX", "orderId": "o-…", "paymentReference": "<PayPal capture ID>", "state": "CAPTURED", ... }` | Verifies the capture landed in the provider's merchant account, then reserves. Approval makes no second charge. If the booking is terminally rejected, PP refunds the unbound capture itself (D-14). |
| Ultimo | as in the example | Verifies the capture is held in the platform balance. On approval it releases the funds; on cancellation it refunds them (PP-05). |

### Errors
| HTTP | Code | What to do |
|---|---|---|
| 400 | `VALIDATION_ERROR` | A malformed request alone does not authorize compensation. |
| 422 | `BOOKING_QUANTITY_EXCEEDS_GUESTS` / `OCCUPANCY_EXCEEDED` | Follow D-14 if PP verifies a captured, unbound payment and records a terminal rejection. |
| 409 | `QUOTE_EXPIRED` / `QUOTE_MISMATCH` / `MEMBERSHIP_ELIGIBILITY_CHANGED` | Same D-14 rule. Get a new quote before a new purchase. |
| 409 | `ORDER_ALREADY_BOUND` / `QUOTE_ALREADY_CONSUMED` / `PAYMENT_ALREADY_BOUND` | `refundRequiredByPayer=false`. Reconcile the original order. |
| 422 | `PAYMENT_AMOUNT_MISMATCH` / `PAYMENT_REFERENCE_MISMATCH` / `PAYMENT_NOT_CAPTURED` | Same D-14 rule. No successful capture means there is nothing to return. |
| 409 | `INSUFFICIENT_AVAILABILITY` | Same D-14 rule. |
| 409 | `IDEMPOTENCY_CONFLICT` | `refundRequiredByPayer=false`. The original request still stands. |
| 503 | `SERVICE_UNAVAILABLE` / `MEMBERSHIP_VERIFICATION_UNAVAILABLE` | `refundRequiredByPayer=false`. Retry with the same idempotency key; the booking may already exist. |
| 401 / 403 / 429 | `PARTNER_UNAUTHENTICATED` / `PARTNER_FORBIDDEN` / `RATE_LIMITED` | `refundRequiredByPayer=false`. Request not processed. Write limit: 30 requests per 60 s. |

CP refunds only when PP returns `refundRequiredByPayer=true` for escrow. For direct payments, PP handles the return of an unbound capture and reports its outcome using the [D-14 fields](../common/03-agreed-decisions.md#d-14-booking-rejected-after-payment-was-captured).

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
| 429 | `RATE_LIMITED` | Read limit: 120 requests per 60 s |
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
| orderId | string (uuid) | no | Exact CP order ID, scoped to this customer and partner. Used to reconcile a timed-out CreateBooking without knowing its bookingId. |
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
      "priceBreakdown": { "nights": 3, "quantity": 2, "unitPricePerNight": { "amountMinor": 2500, "currency": "USD" }, "subtotal": { "amountMinor": 15000, "currency": "USD" }, "discount": { "discountPackageId": "d15c0a7e-0000-4000-8000-000000000015", "name": "Premium 15% Off", "type": "PERCENTAGE", "value": 15, "amount": { "amountMinor": 2250, "currency": "USD" } }, "total": { "amountMinor": 12750, "currency": "USD" } },
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
| 429 | `RATE_LIMITED` | Read limit: 120 requests per 60 s |
| 503 | `SERVICE_UNAVAILABLE` | Booking service unavailable |

An unknown `customerId` is not an error: the response is `200` with an empty `items` array, so customer existence is not disclosed.

For timeout reconciliation, use `orderId` without status/date filters. It returns the committed booking bound to that CP order, including a booking archived from the provider's workflow. No item during an unresolved in-flight write does not authorize a refund: replay the original idempotent create or wait for PP's durable terminal rejection. The binding/lookup is retained after Redis and quote-hold expiry.

> **Shard routing (PP-SEARCH-U01 style):** Reservations are sharded by **`branch country`**, with a secondary index table `customer_booking_index (customerId → bookingId, shardId)` cached in Redis. A list query touches only the shards that hold that customer's bookings.
>
> **CP Modular Monolith Integration (`BookingModule` → `RatingModule`):** When serving `GET /api/v1/customer/bookings?group=PENDING_AND_ACTIVE|NOT_REVIEWED|PAST|CANCELLED`, CP's `BookingModule` fetches bookings via `PP-OP-08` and joins them **in-process** with `RatingModule` via `IRatingExternalService` (`ReviewedBookingIdsDto`). CP follows upstream cursors until the requested group page is filled or PP reports `hasMore=false`; even `limit=50` cannot guarantee a match on the first upstream page. CP's customer-facing cursor retains the upstream position and any unconsumed matches, so no booking is skipped. If an upstream request fails, return controlled unavailability rather than claim that the group is empty.

---

## PP-OP-09 CancelBookingByCustomer

| Binding | Value |
|---|---|
| REST | `POST /api/v1/partner/bookings/{bookingId}/cancellations` (headers: `Idempotency-Key` **required**) |
| Kafka | `rs.booking.request.v1` (`type=CANCEL_BOOKING`, key `bookingId`) |

On Kafka, `bookingId` moves from the path into the payload. The envelope's **`idempotencyKey`** maps to `Idempotency-Key`; `correlationId` matches this logical request and response, while `traceId` groups the business flow.

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
| 400 | `VALIDATION_ERROR` | `customerId` missing or not a UUID, or `reason` over 500 characters |
| 404 | `RESOURCE_NOT_FOUND` | Unknown booking, or not owned by `customerId` |
| 409 | `STATE_CONFLICT` | Already `CANCELLED` or `COMPLETED`. A repeat with the same `Idempotency-Key` returns the original `200` instead. |
| 409 | `CANCELLATION_WINDOW_CLOSED` | Today ≥ `checkInDate` (D-08) |
| 409 | `IDEMPOTENCY_CONFLICT` | Same `Idempotency-Key` reused with a different body |
| 503 | `SERVICE_UNAVAILABLE` | Booking service unavailable on every instance. Retry with the same `Idempotency-Key`. |
| 401 / 403 / 429 | `PARTNER_UNAUTHENTICATED` / `PARTNER_FORBIDDEN` / `RATE_LIMITED` | Standard partner errors (write limit: 30 requests per 60 s) |

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
| providerName | string | Company name of the accommodation provider (so CP can display and store it with the review without an extra `PP-OP-07` call) |
| branchId | string | |
| branchName | string | Property name of the booked branch |
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
  "providerName": "Thu Bon Family Stays",
  "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
  "branchName": "Riverside Homestay Hoi An",
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
| 429 | `RATE_LIMITED` | Read limit: 120 requests per 60 s |
| 503 | `SERVICE_UNAVAILABLE` | Booking service unavailable |

A booking owned by a different customer returns `200` with `eligible=false` and `reason=NOT_BOOKING_OWNER`, so CP can show a precise message without PP disclosing booking details (only the IDs in the request are echoed).

CP must call this **at review creation**. CP-RATING-S01 evidence requires that pre-stay creation is rejected. Cached eligibility may support display, but review creation re-verifies it because a previously confirmed booking can subsequently be cancelled.
