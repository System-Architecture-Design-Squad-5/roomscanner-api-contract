# PP-05: Payment Flows, Payer (CP) and Beneficiary (PP) Responsibilities

**SRS:** PP-MONEY-S01, M01, M02, M03, U01 · CP-MONEY-S01, M01, M02, M03, U01 to U04 · Decisions D-07, D-08, D-13, D-14

Neither team controls the whole money lifecycle (CP-MONEY-M02(S)): **CP initiates and captures**, and **PP approves, releases and returns**. Gateway keys are per subsystem. Sandbox credentials live in each team's `.env` and are never committed.

For Ultimo, "keys per subsystem" means separate least-privilege service credentials for **one squad-owned Stripe Connect sandbox platform**, configured with the same `STRIPE_PLATFORM_ACCOUNT_ID`. It does not mean two unrelated Stripe accounts. The platform owns CP-created PaymentIntents/charges and PP-created transfers/refunds. Each provider's connected account belongs to that platform; it is the release/payout destination. Validate configured platform identity at startup and verify payment ownership against it. No secret or restricted key is transmitted through the partner payload.

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

CP creates the charge on the configured squad platform without a destination charge or automatic transfer to the connected provider. The quote's `payeeAccountId` identifies the provider for PP's later release; it is not the account into which CP captures the escrow-style payment.

| # | Operation | Owner | Stripe call | When | Contract effect |
|---|---|---|---|---|---|
| 1 | **Authorize** | CP | `PaymentIntent.create(amount=total, capture_method=manual)` + customer confirms | Checkout | N/A |
| 2 | **Capture** | CP | `PaymentIntent.capture` | Immediately after authorization succeeds, **before** PP-OP-06 | `state=CAPTURED_HELD`, `paymentReference=pi_…`, `chargeReference=ch_…` |
| 3 | **Release / transfer** | PP | `Transfer.create(amount=total, destination=acct_provider, source_transaction=ch_…, transfer_group=bookingId)` | Receptionist approval | `escrowStatus=RELEASED`, `releaseReference=tr_…` |
| 4 | **Payout** | PP (provider's connected account) | `Payout.create` on the connected account (or its automatic schedule) | After release, per the provider's payout schedule | Shown on the PP provider dashboard only. Not sent to CP. |
| 5 | **Refund** | PP | `Refund.create(charge=ch_…)` | Cancellation while the funds are held | `escrowStatus=REFUNDED`, `returnPaymentReference=re_…`, `returnPaymentStatus` PENDING → SUCCEEDED/FAILED |

Rules:
- CP records `quoteId`, `customerId` and CP `orderId` as gateway metadata before capture. PP retrieves the actual PaymentIntent/charge with its platform credential and verifies those bindings, captured amount/currency, the charge-to-intent relationship, the intended provider destination and absence of an earlier refund/booking binding. The durable booking uniqueness rules in PP-03 prevent the same money being reused with another idempotency key.
- **Failed or incomplete capture must never look paid** (CP-MONEY-U04). CP sends PP-OP-06 only after `PaymentIntent.status == succeeded`. PP re-checks it (PP-03, validation step 6).
- Cancellation **after** release (customer/receptionist within D-08's permitted window): retain `releaseReference`, set `transferReversalStatus=PENDING` and reverse that transfer (`Transfer.createReversal`). On success, save `transferReversalReference` (`trr_...`), set its status to `SUCCEEDED`, then submit the customer refund. While refund is pending, `escrowStatus=HELD`; set `REFUNDED` only after actual refund success. The original payment, release, reversal and refund references are all retained and reported in PP-OP-11.
- If reversal fails, retain `escrowStatus=RELEASED`, set `transferReversalStatus=FAILED` and `transferReversalFailureCause` to the gateway cause; set `returnPaymentStatus=FAILED` and explain that the customer refund has not been submitted. The booking remains cancelled and inventory remains released. PP retries transient failures under its 3-attempt return policy and exposes a durable failed outcome for operator recovery. If reversal succeeds but refund fails, preserve the successful reversal and retry only the refund, without reversing again. Never report a successful customer return from a successful reversal alone.
- Stripe sends events for the shared platform. Configure authenticated webhook routes: CP handles payment authorization/capture/order events; PP handles release, reversal, refund and connected-account payout outcomes. Verify Stripe signatures on the raw body and deduplicate Stripe `event.id` in the receiving subsystem. A shared event delivery must not grant the receiver ownership of the other team's business action. PP publishes the beneficiary outcomes to CP through PP-OP-11; these include pending and failed reversals/refunds. Webhook URLs and secrets are deployment configuration, not values sent by CP in a booking request.
- Idempotency keys sent to Stripe = `{bookingId}:{operation}`, so a retry after service failover never transfers or refunds twice.
- The return workflow and its reference/status updates are persisted before acknowledgement and survive booking-service failover. Distinct stable operation keys are used for transfer reversal and refund. Stripe's idempotency cache complements the service's durable business ledger; it does not replace it.

This sandbox design uses [Stripe separate charges and transfers](https://docs.stripe.com/connect/separate-charges-and-transfers): platform charges and connected-account transfers are separate objects, and refunding a charge does not itself recover the associated transfer. The contract therefore records both the transfer recovery and the customer refund.

## 4. Who displays what

| Outcome | CP shows the customer | PP shows the receptionist |
|---|---|---|
| Payment failed at checkout | Exact gateway error, no booking | nothing (no booking exists) |
| `PENDING_APPROVAL` | "Paid, awaiting provider confirmation" (clearly distinct from final) | "New request", **newest pending first** (PP-ROOM-M02) |
| `CONFIRMED` | "Confirmed" + email | "Confirmed" (+ escrow released) |
| `CANCELLED` + `returnPaymentStatus` | "Cancelled, refund pending / refunded / refund failed: <cause>" | Same, plus the payout/refund reference |
