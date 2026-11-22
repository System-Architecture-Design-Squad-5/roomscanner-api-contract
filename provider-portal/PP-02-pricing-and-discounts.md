# PP-02: Pricing and Premium Discounts (provided by PP)

**Owner:** Provider Portal · **Consumer:** Customer Portal · **Scope:** `quote:write`
**SRS:** PP-DISCOUNT-S01, S02 · CP exchange "Premium room discounts" · CP-MONEY-M01 evidence ("the selected discount is honored")
**Business rules:** Decisions D-06, D-07, D-14

## Why a quote?
PP owns the discount packages and room policies, so **PP calculates the price** and CP charges exactly that amount. The quote also:
1. puts a **15-minute hold** on the requested quantity to reduce the risk of a paid booking failing for availability (D-14);
2. gives CP the **payee account** for the payment (D-07), without exposing provider payment data in public search.

---

## PP-OP-05 CreatePriceQuote

| Binding | Value |
|---|---|
| REST | `POST /api/v1/partner/quotes` (headers: `Idempotency-Key`, `X-Correlation-Id`) |
| Kafka | `rs.booking.request.v1` (`type=CREATE_QUOTE`) → `rs.booking.response.v1` (`type=CREATE_QUOTE_RESULT`) |

### Request
| Field | Type | Required | Notes |
|---|---|---|---|
| customerId | string | yes | CP user ID |
| membership | MembershipSnapshot | yes | PP re-verifies with CP-OP-02 before applying a discount |
| roomId | string | yes | |
| checkInDate | string (date) | yes | ≥ today (branch local time) |
| checkOutDate | string (date) | yes | > checkInDate, ≤ 30 nights |
| quantity | integer | yes | ≥ 1 |
| adults | integer | yes | ≥ 1 |
| children | integer | yes | ≥ 0. Rule: `quantity ≤ adults + children` (PP-BOOK-S02, CP-BOOK-S02) |
| paymentMode | PaymentMode | yes | Tells PP which payee data to return |

### Response `201`
| Field | Type | Notes |
|---|---|---|
| quoteId | string | Pass this to PP-OP-06 |
| roomId / branchId / providerId | string | |
| checkInDate / checkOutDate | string | |
| quantity / adults / children | integer | |
| priceBreakdown | PriceBreakdown | `total` is the amount CP must charge |
| membershipVerified | boolean | `true` when CP-OP-02 confirmed an active Premium membership |
| payee | object | `{ gateway, payeeAccountId, payeeDisplayName }`. Omitted for `SIMULATED`. For ESCROW this identifies the intended connected provider for a **later PP release**; CP captures into the configured squad platform, not this connected account. |
| holdExpiresAt | string | UTC, `createdAt` + 15 min |
| createdAt | string | |

### Example: Premium customer, 15% policy, 2 rooms × 3 nights
**Request**

```json
{
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
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
  "paymentMode": "ESCROW"
}
```
**Response `201`**

```json
{
  "quoteId": "1a2b3c4d-0000-4000-8000-000000000501",
  "roomId": "3f2e1d0c-0000-4000-8000-000000000301",
  "branchId": "9a8b7c6d-0000-4000-8000-000000000250",
  "providerId": "5b1c2d3e-0000-4000-8000-000000000150",
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
  "membershipVerified": true,
  "payee": {
    "gateway": "STRIPE_SANDBOX",
    "payeeAccountId": "acct_1PxThuBonTEST",
    "payeeDisplayName": "Thu Bon Family Stays"
  },
  "holdExpiresAt": "2026-12-01T03:15:00Z",
  "createdAt": "2026-12-01T03:00:00Z"
}
```

### Example: Standard customer (no discount)
The `priceBreakdown` has no `discount` field, and `total` = `subtotal`. `membershipVerified` is `false`.

### Errors
| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Bad dates or counts |
| 422 | `BOOKING_QUANTITY_EXCEEDS_GUESTS` | `quantity > adults + children` |
| 422 | `OCCUPANCY_EXCEEDED` | `adults + children > quantity × maxOccupancy` |
| 409 | `INSUFFICIENT_AVAILABILITY` | `availableQuantity < quantity` (D-05). The body includes `availableQuantity`. |
| 404 | `RESOURCE_NOT_FOUND` | Room unknown or archived |
| 503 | `MEMBERSHIP_VERIFICATION_UNAVAILABLE` | CP-OP-02 unreachable **and** the customer claims Premium. PP refuses to guess (fail closed). CP may retry or quote as Standard. |

### Rules
- **Idempotent:** The same `Idempotency-Key` and body replay the original quote, including its original `holdExpiresAt`; replay never extends or recreates a hold. CP checks that expiry before capture and requests a new quote/key if it is no longer active.
- Store the quote's customer, room, dates, quantity, tourist counts, payment mode, price/membership snapshot and hold identity. Validate capacity and insert/replace the hold atomically. The authoritative hold lives in the booking service's store; Redis may accelerate expiry detection.
- **Expiry:** After `holdExpiresAt`, the hold is released by a Redis key-expiry listener plus a sweeper job. A booking that references the quote then fails with `QUOTE_EXPIRED`.
- **Policy cancelled while a quote is open:** The quote keeps its price until it expires (D-06).
- One active hold per `customerId` + `roomId`. A genuinely new quote (new key) invalidates the previous unconsumed quote/hold atomically; replaying an old key never recreates or extends it. A consumed quote stays bound to its booking, and cannot be reused with another payment/order/key.
- Before capture, CP binds `quoteId`, `customerId` and its `orderId` into gateway payment metadata. PP validates the gateway's actual metadata and shared-platform ownership at booking creation. Capture must finish before the hold's deadline; rejection/timeout reconciliation follows PP-03.
