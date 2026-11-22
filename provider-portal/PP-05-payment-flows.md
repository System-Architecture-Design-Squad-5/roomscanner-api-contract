# PP-05: Payment Flows, Payer (CP) and Beneficiary (PP) Responsibilities

**SRS:** PP-MONEY-S01, M01, M02, M03, U01 · CP-MONEY-S01, M01, M02, M03, U01 to U04 · Decisions D-07, D-08, D-13, D-14

Neither team controls the whole money lifecycle (CP-MONEY-M02(S)): **CP initiates and captures**, and **PP approves, releases and returns**. Gateway keys are per subsystem. Sandbox credentials live in each team's `.env` and are never committed.

> **CP Customer-Facing Endpoint Mapping (`BookingModule`):**
> 1. `POST /api/v1/customer/bookings/quotes` → calls `PP-OP-05 CreatePriceQuote` (`quoteId`, `priceBreakdown.total`, `payee`).
> 2. `POST /api/v1/customer/payments/authorize` → Step 1 Authorize (Stripe `PaymentIntent.create(capture_method=manual)` / PayPal order creation).
> 3. `POST /api/v1/customer/payments/capture` → Step 2 Capture into escrow (`CAPTURED_HELD` / `CAPTURED`).
> 4. `POST /api/v1/customer/bookings` → calls `PP-OP-06 CreateBooking` (refunds automatically if `PP-OP-06` fails with `refundRequiredByPayer=true`).
> 5. `POST /api/v1/customer/bookings/{bookingId}/cancel` → calls `PP-OP-09 CancelBookingByCustomer` (triggers PP Step 5 Refund / PayPal Payout).

## 1. Simplex: simulated order (no third-party provider)

```
CP                                   PP                                   CP
│ 1 create simulated order o-…        │                                    │
│ 2 PP-OP-05 quote ─────────────────► │                                    │
│ 3 PP-OP-06 booking (SIMULATED) ───► │ reserve, PENDING_APPROVAL          │
│                                     │ 4 receptionist approves / cancels  │
│                                     │ 5 CP-OP-03 PATCH order COMPLETE/CANCEL ─► mark order
│                                     │ 6 PP-OP-11 BOOKING_CONFIRMED/CANCELLED ─► email + UI
```

## 2. Medium: direct customer-to-provider payment + separate return payout (PayPal Sandbox)

| Step | Actor | Operation | Gateway call | Contract field |
|---|---|---|---|---|
| 1 | CP | PP-OP-05 quote (`paymentMode=DIRECT`) | N/A | `payee.payeeAccountId` = provider's PayPal merchant ID |
| 2 | CP | Create the order with `payee.merchant_id` = the provider, then the customer approves | PayPal Orders v2 `POST /v2/checkout/orders`, then `.../capture` | N/A |
| 3 | CP | On **failure**: show the exact PayPal error to the customer and send **no** booking (CP-MONEY-M01) | N/A | N/A |
| 4 | CP | PP-OP-06 with `state=CAPTURED` | N/A | `paymentReference` = capture ID |
| 5 | PP | Verify the capture (status `COMPLETED`, amount, payee) | `GET /v2/payments/captures/{id}` | N/A |
| 6 | PP | Receptionist approves → `BOOKING_CONFIRMED`. **No second charge.** | none | N/A |
| 7 | PP | On cancellation → release the rooms, then make a **separate payout** from the provider to the customer's email | PayPal Payouts `POST /v1/payments/payouts` | `returnPaymentReference` = payout batch ID, `returnPaymentStatus=PENDING` |
| 8 | PP | Payout webhook `PAYMENT.PAYOUTS-ITEM.SUCCEEDED/FAILED` → `RETURN_PAYMENT_UPDATED` | N/A | `failureCause` when failed (PP-MONEY-M03) |

The original capture is **never** refunded through the refund API at Medium (PP-MONEY-M02, D-13). Both references are preserved.

## 3. Ultimo: escrow (Stripe Sandbox, Connect "separate charges and transfers")

The five escrow operations required by PP-MONEY-U01 / CP-MONEY-U04:

| # | Operation | Owner | Stripe call | When | Contract effect |
|---|---|---|---|---|---|
| 1 | **Authorize** | CP | `PaymentIntent.create(amount=total, capture_method=manual)` + customer confirms | Checkout | N/A |
| 2 | **Capture** | CP | `PaymentIntent.capture` | Immediately after authorization succeeds, **before** PP-OP-06 | `state=CAPTURED_HELD`, `paymentReference=pi_…`, `chargeReference=ch_…` |
| 3 | **Release / transfer** | PP | `Transfer.create(amount=total, destination=acct_provider, source_transaction=ch_…, transfer_group=bookingId)` | Receptionist approval | `escrowStatus=RELEASED`, `releaseReference=tr_…` |
| 4 | **Payout** | PP (provider's connected account) | `Payout.create` on the connected account (or its automatic schedule) | After release, per the provider's payout schedule | Shown on the PP provider dashboard only. Not sent to CP. |
| 5 | **Refund** | PP | `Refund.create(charge=ch_…)` | Cancellation while the funds are held | `escrowStatus=REFUNDED`, `returnPaymentReference=re_…`, `returnPaymentStatus` PENDING → SUCCEEDED/FAILED |

Rules:
- **Failed or incomplete capture must never look paid** (CP-MONEY-U04). CP sends PP-OP-06 only after `PaymentIntent.status == succeeded`. PP re-checks it (PP-03, validation step 6).
- Cancellation **after** release (receptionist cancels a confirmed booking): PP first reverses the transfer (`Transfer.createReversal`), then refunds. Both references are reported.
- Stripe webhooks (`charge.refunded`, `transfer.created`, `transfer.reversed`) are received by the **owning** subsystem only. PP turns them into PP-OP-11 events.
- Idempotency keys sent to Stripe = `{bookingId}:{operation}`, so a retry after service failover never transfers or refunds twice.

## 4. Who displays what

| Outcome | CP shows the customer | PP shows the receptionist |
|---|---|---|
| Payment failed at checkout | Exact gateway error, no booking | nothing (no booking exists) |
| `PENDING_APPROVAL` | "Paid, awaiting provider confirmation" (clearly distinct from final) | "New request", **newest pending first** (PP-ROOM-M02) |
| `CONFIRMED` | "Confirmed" + email | "Confirmed" (+ escrow released) |
| `CANCELLED` + `returnPaymentStatus` | "Cancelled, refund pending / refunded / refund failed: <cause>" | Same, plus the payout/refund reference |
