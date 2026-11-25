# PP-05: Payment Flows, Payer (CP) and Beneficiary (PP) Responsibilities

**SRS:** PP-MONEY-S01, M01, M02, M03, U01 · CP-MONEY-S01, M01, M02, M03, U01 to U04 · Decisions D-07, D-08, D-13, D-14

Neither team controls the whole money lifecycle (CP-MONEY-M02(S)): **CP initiates and captures**, and **PP approves, releases and returns**. Gateway keys are per subsystem. Sandbox credentials live in each team's `.env` and are never committed.

> **CP Customer-Facing Endpoint Mapping (`BookingModule`):**
> 1. `POST /api/v1/customer/bookings/quotes` -> calls `PP-OP-05 CreatePriceQuote` (`quoteId`, `priceBreakdown.total`, `payee`).
> 2. `POST /api/v1/customer/payments/authorize` -> Step 1 Authorize (Stripe `PaymentIntent.create(capture_method=manual)` / PayPal order creation).
> 3. `POST /api/v1/customer/payments/capture` -> captures on the squad platform (`CAPTURED_HELD`) or directly for the provider (`CAPTURED`).
> 4. `POST /api/v1/customer/bookings` -> calls `PP-OP-06 CreateBooking`. For rejected captures, follow [D-14](../common/03-agreed-decisions.md#d-14-booking-rejected-after-payment-was-captured). A timeout is not permission to refund.
> 5. `POST /api/v1/customer/bookings/{bookingId}/cancel` → calls `PP-OP-09 CancelBookingByCustomer` (triggers PP Step 5 Refund / PayPal Payout).

For paid checkout, CP reuses the existing order and gateway payment for the quote. Use separate stable gateway request IDs for creation and capture. If a response is lost, reconcile the original operation before retrying. Do not start a new payment for an unresolved checkout. See [D-14](../common/03-agreed-decisions.md#d-14-booking-rejected-after-payment-was-captured) for a separate capture on the same quote.

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
| 5a | PP | After recording a terminal rejection, submit a refund of the unbound capture. This is not a cancellation (D-14). | `POST /v2/payments/captures/{id}/refund` | Once a reference exists: `refundIssuedByBeneficiary=true`, `returnPaymentReference`, `returnPaymentStatus` |
| 6 | PP | Receptionist approves → `BOOKING_CONFIRMED`. **No second charge.** | none | N/A |
| 7 | PP | On cancellation → release the rooms, then make a **separate payout** from the provider to the customer's email | PayPal Payouts `POST /v1/payments/payouts` | `returnPaymentReference` = payout batch ID, `returnPaymentStatus=PENDING` |
| 8 | PP | Payout webhook `PAYMENT.PAYOUTS-ITEM.SUCCEEDED/FAILED` → `RETURN_PAYMENT_UPDATED` | N/A | `failureCause` when failed (PP-MONEY-M03) |

For a **cancelled booking**, the original capture is **never** refunded through the refund API at Medium (PP-MONEY-M02, D-13); the return is the separate payout in step 7. Both references are preserved. Step 5a is the only Medium refund, and it applies only when no booking was ever created.

## 3. Ultimo: escrow (Stripe Sandbox, Connect "separate charges and transfers")

The five escrow operations required by PP-MONEY-U01 / CP-MONEY-U04:

CP creates the charge on the squad platform, without an automatic transfer to the provider. The quote's `payeeAccountId` is the destination for PP's later release. CP and PP both use the **CP `orderId`** as Stripe's `transfer_group`, since it exists before PP creates a `bookingId`.

| # | Operation | Owner | Stripe call | When | Contract effect |
|---|---|---|---|---|---|
| 1 | **Authorize** | CP | `PaymentIntent.create(amount=total, capture_method=manual)` + customer confirms | Checkout | N/A |
| 2 | **Capture** | CP | `PaymentIntent.capture` | Immediately after authorization succeeds, **before** PP-OP-06 | `state=CAPTURED_HELD`, `paymentReference=pi_…`, `chargeReference=ch_…` |
| 3 | **Release / transfer** | PP | `Transfer.create(amount=total, destination=acct_provider, source_transaction=chargeId, transfer_group=orderId)` | After receptionist approval | `RELEASE_PENDING` until the transfer result is known. On success: `RELEASED` and `releaseReference` contains the transfer ID. On definitive failure: `RELEASE_FAILED`. |
| 4 | **Payout** | PP (provider's connected account) | `Payout.create` on the connected account (or its automatic schedule) | After release, per the provider's payout schedule | Shown on the PP provider dashboard only. Not sent to CP. |
| 5 | **Refund** | PP | `Refund.create(charge=chargeId)` | Cancellation once funds are held or a released transfer has been reversed | `returnPaymentStatus` goes from `PENDING` to `SUCCEEDED` or `FAILED`. Set `escrowStatus=REFUNDED` only on success. |

Rules:
- CP records `quoteId`, `customerId` and CP `orderId` as gateway metadata before capture. PP retrieves the actual PaymentIntent/charge with its platform credential and verifies those bindings, captured amount/currency, the charge-to-intent relationship, the intended provider destination and absence of an earlier refund/booking binding. The durable booking uniqueness rules in PP-03 prevent the same money being reused with another idempotency key.
- **Failed or incomplete capture must never look paid** (`CP-MONEY-U04`). CP sends PP-OP-06 only after `PaymentIntent.status == succeeded`. PP verifies the capture again ([PP-03](PP-03-bookings.md#pp-validation-order)).
- **Approval and release are separate.** Record `CONFIRMED` and `RELEASE_PENDING`, then attempt the transfer with the stable `bookingId:release` key. After the attempt, lock and re-read the booking. If it is still confirmed and no confirmation was queued, record the observed release state and queue `BOOKING_CONFIRMED` in one transaction. Queue `ESCROW_RELEASE_UPDATED` after confirmation when the transfer result is known. A timeout leaves the release pending. A failed release does not undo the approval, charge the customer again or start a refund.
- **Cancellation while release is pending:** Use the same booking lock for cancellation and for recording a transfer result. If cancellation wins before confirmation is queued, do not queue a confirmation from a late Stripe reply. Record the verified result against the cancelled booking and report through cancellation and return-payment events. Do not start a new transfer for a cancelled booking. Release inventory and report `returnPaymentStatus=PENDING` until the original transfer is resolved. Reverse a successful transfer first. Refund directly only after confirming no transfer occurred. A missing transfer in a lookup is not enough to make that decision.
- Cancellation **after** release (customer/receptionist within D-08's permitted window): retain `releaseReference`, set `transferReversalStatus=PENDING` and reverse that transfer (`Transfer.createReversal`). On success, save `transferReversalReference` (`trr_...`), set its status to `SUCCEEDED`, then submit the customer refund. While refund is pending, `escrowStatus=HELD`; set `REFUNDED` only after actual refund success. The original payment, release, reversal and refund references are all retained and reported in PP-OP-11.
- If reversal fails, retain `escrowStatus=RELEASED`, set `transferReversalStatus=FAILED` and `transferReversalFailureCause` to the gateway cause; set `returnPaymentStatus=FAILED` and explain that the customer refund has not been submitted. The booking remains cancelled and inventory remains released. PP retries transient failures under its 3-attempt return policy and exposes a durable failed outcome for operator recovery. If reversal succeeds but refund fails, preserve the successful reversal and retry only the refund, without reversing again. Never report a successful customer return from a successful reversal alone.
- Stripe sends events for the shared platform. Configure authenticated webhook routes: CP handles payment authorization/capture/order events; PP handles release, reversal, refund and connected-account payout outcomes. Verify Stripe signatures on the raw body and deduplicate Stripe `event.id` in the receiving subsystem. A shared event delivery must not grant the receiver ownership of the other team's business action. PP publishes the beneficiary outcomes to CP through PP-OP-11; these include pending and failed reversals/refunds. Webhook URLs and secrets are deployment configuration, not values sent by CP in a booking request.

### Recovering pending gateway actions

Use the status and references in `Payment` and the recorded request outcome to reconcile after a timeout or restart. Use a stable gateway request ID for each operation: `bookingId:release` for the Stripe transfer and distinct IDs based on the original target and operation for reversals and refunds. Retry the identical call only while the gateway still guarantees that it will not repeat the operation. Record the verified result and queue booking events in `OutboxEvent` in the same transaction when a booking exists.

If the existing records and gateway cannot establish the outcome and a safe retry is no longer possible, leave it pending for manual reconciliation. Never send a fresh gateway request just because the reply was lost.

<!-- shortcut: the fixed model does not track a second capture per quote. Add durable per-capture tracking only if automatic reconciliation becomes a requirement. -->

This sandbox design uses [Stripe separate charges and transfers](https://docs.stripe.com/connect/separate-charges-and-transfers): platform charges and connected-account transfers are separate objects, and refunding a charge does not itself recover the associated transfer. The contract therefore records both the transfer recovery and the customer refund.

## 4. Who displays what

| Outcome | CP shows the customer | PP shows the receptionist |
|---|---|---|
| Payment failed at checkout | Exact gateway error, no booking | nothing (no booking exists) |
| `PENDING_APPROVAL` | "Paid, awaiting provider confirmation" (clearly distinct from final) | "New request", **newest pending first** (PP-ROOM-M02) |
| `CONFIRMED` | "Confirmed" + one confirmation email. Release updates do not resend the email. | "Confirmed". For escrow, show release pending, released, or release failed separately. |
| `CONFIRMED` + `RELEASE_PENDING` or `RELEASE_FAILED` | Booking stays confirmed. Do not show a completed transfer or a refund. No action is required from the customer. | Show the actual transfer status and the gateway failure cause when available. |
| `CANCELLED` + `returnPaymentStatus` | "Cancelled, refund pending / refunded / refund failed: <cause>" | Same, plus the payout/refund reference |
