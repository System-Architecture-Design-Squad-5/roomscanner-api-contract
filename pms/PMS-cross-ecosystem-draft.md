# Shared PMS: Cross-Ecosystem Contract (DRAFT)

> **Pending partner-squad agreement.** All choices below are proposals, not part of the binding CP-PP contract. Each squad keeps a copy of the separate PMS agreement once signed (lecturer clarification, 23 Nov 2026).

**Coverage:** PP SRS 2.9 (`PP-PMS-S01`, `PP-PMS-S02`), CP SRS 1 and 3, `BE-U09`, `DEP-U05`, `INT-M03`, `INT-U02`, `INT-U03`.

## 1. Roles and scope

| Party | Responsibility |
|---|---|
| PMS (Machine 5) | Stores a searchable copy of shared room data and routes requests. The projection and its supporting store are proposed for Machine 5. Who runs them is still open. |
| Each squad's PP | Verifies provider subscription payments, publishes its rooms, and authorizes provider reads. Owns availability, quotes and bookings for its rooms. |
| Each squad's CP | Searches and books directly through PMS, authenticates its customers and serves reviews it owns. Only sends the agreed fields for each operation. |

Both squads use the same roles. Browsers do not connect to PMS. CP merges local PP and PMS search results at its own boundary. Local CP-PP endpoints never accept foreign room IDs. The owning PP uses its existing `pp.pms-booking.request.v1` / `.reply.v1` internal adapter for booking calls. No changes to either squad's existing database model are specified here.

## 2. Provider entitlement

- The provider pays **USD 200 per year**. The home PP owns activation and profile display. Verify a successful USD 200 capture directly with the selected gateway and bind it to the authenticated provider and the PMS subscription purchase. A redirect or client claim is not proof. Failed, pending or mismatched payments do not activate access. The squads still need to agree on gateway and merchant/setup ownership.
- Persist `subscriptionId`, `providerId`, unique `paymentReference`, `validFrom` and `validUntil` in `PmsSubscription`. The same payment reference for the same provider replays the original period and never extends it. Reject reuse by another provider. Serialize activation per provider. For a new verified payment, `validFrom` is the later of the UTC date of verification and the latest paid `validUntil` (if any). `validUntil` is one calendar year later, clamped to February 28 if the anniversary has no February 29.
- Use UTC calendar dates. Access is active when any paid period satisfies `validFrom <= todayUTC < validUntil`. The end is exclusive at `00:00:00Z` on `validUntil`. Profile shows derived `ACTIVE`, `EXPIRED` or `NONE` and the current period if active, else the last elapsed period if any. Show prepaid renewal dates separately if present. No stored status field. Example: `2026-12-01` to `2027-12-01` stops granting access at `2027-12-01T00:00:00Z` unless renewed. Stay dates still use the branch time zone.
- PP publishes eligible rooms on activation and refreshes their expiry on renewal. Advertise the end of the contiguous paid periods starting with the active period. When entitlement actually ends, PP publishes `ROOM_UNPUBLISHED` for all the provider's shared rooms. PMS hides rows at their advertised expiry even if the withdrawal is late. Before exposing a room or serving its reviews, PMS also checks the owning PP for current sharing and entitlement. If the owner cannot verify, fail closed with `503 SERVICE_UNAVAILABLE`, not an empty result or an inactive decision. An expired projection can temporarily hide a renewed room until PP refreshes it.
- A provider signs into its home PP. PP must derive `actingProviderId` from the authenticated account, not from frontend input. Provider-mode search requires a live home-PP `CHECK_ENTITLEMENT` and shows only the other squad's currently shared rooms. The booking-scoped guest read rechecks locally at the home PP. No arbitrary customer lookup. CP customer search does not need a requester subscription or customer Premium. The room owner's provider entitlement still applies.
- Owning PP rechecks room sharing and provider entitlement when creating a new quote and before committing a new booking. Replay recorded writes before rechecking, without repeating side effects. Reading or cancelling an existing booking by its originating CP and customer remains allowed after provider expiry, subject to normal booking ownership and cancellation rules. Provider-mode guest reads remain gated.

`PP-PMS-S02` is treated as provider PMS entitlement, not customer Premium, following [D-17](../common/03-agreed-decisions.md#d-17-srs-errata-noted-by-the-squad). The wording still needs lecturer confirmation.

## 3. Typed operations and payload examples

All examples in this section show **payloads only**, not Kafka envelopes. The operation name is the envelope `type`. A request's result type is `<type>_RESULT`. Follow [shared formats and errors](../common/01-conventions.md#2-data-formats) and [shared types](../common/02-shared-types.md) where named. `uuid` means a UUID string, `date` an ISO calendar date, `instant` a UTC timestamp, `country` an ISO alpha-2 country code, and `squad` a registered squad ID string. All fields are required unless marked `?`. Reject unknown fields and invalid types. IDs are opaque to clients.

| Type | Fields |
|---|---|
| `RoomId` | string `<squadId>:<roomId>` with UUID local suffix. The prefix is the owning squad. No lookup table. |
| `ProviderRef` | string `<squadId>:<providerId>` with UUID local suffix. Joins shared rooms to provider-level reviews. |
| `SharedRoom` | `pmsRoomId: RoomId`, `providerRef: ProviderRef`, `roomName: string`, `roomType: RoomType`, `branchName: string`, `providerName: string`, `country: country`, `city: string`, `pricePerNight: Money` (indicative only), `totalQuantity: integer >= 1`, `validUntil: date` (exclusive UTC sharing cutoff) |
| `StayDates` | `checkInDate: date`, `checkOutDate: date` (later, up to 30 nights) |
| `BookingRoute` | `ownerSquadId: squad`, `country: country` (booking shard), `bookingId: uuid` |

### 3.1 Share rooms and find availability

| Type and route | Request or event | OK result |
|---|---|---|
| `ROOM_PUBLISHED`, `ROOM_UPDATED` (owner PP -> PMS) | `SharedRoom`, a complete upsert in both cases | One-way |
| `ROOM_UNPUBLISHED` (owner PP -> PMS) | `{ pmsRoomId: RoomId }` | One-way |
| `SEARCH_ROOMS` (CP or PP -> PMS) | `{ country: country, city?: string, stay?: StayDates, actingProviderId?: uuid, cursor?: string }`. Require `actingProviderId` for PP and forbid it for CP. | `{ rooms: SharedRoom[], nextCursor?: string }` |
| `CHECK_ENTITLEMENT` (PMS -> requesting PP) | `{ providerId: uuid }` | `{ validUntil: date }` for the current active period, otherwise `403 PMS_SUBSCRIPTION_INACTIVE` |
| `GET_AVAILABILITY` (CP -> PMS -> owner PP, also used by PMS during search and review reads) | `{ pmsRoomId: RoomId, stay?: StayDates }`. PMS supplies the room's registered `country: country` on the owner leg. | `{ providerRef: ProviderRef, availableQuantity?: integer >= 0 }`. Omit quantity only when no stay was requested. |

The room feed is keyed by `pmsRoomId`. The room and provider prefixes must match the publisher. PP sends changes in current-state order per key, including on retry. PMS applies duplicates idempotently and can rebuild from a fresh owner snapshot. The initial policy is to share all non-archived rooms of eligible providers. An archive or loss of eligibility emits a withdrawal. `totalQuantity` is capacity, not remaining stock. The owner checks sharing and archived status even without dates. With dates, the owner computes live availability across all requested nights using [D-05](../common/03-agreed-decisions.md#d-05-availability-calculation), including holds. Search drops known unshared, inactive or sold-out rooms, but does not treat an owner timeout as sold out. An availability read does not hold stock. Direct availability and review lookups return `404 RESOURCE_NOT_FOUND` if the room cannot be exposed.

Search scans rooms in `pmsRoomId` order, up to 20 candidates per page. A cursor is opaque and bound to the caller and filters, and advances past the last candidate checked even if none were visible. Recheck entitlement on each page. `shortcut:` no PMS inventory cache or bulk availability endpoint. Add batched owner checks if page latency becomes a problem.

`ROOM_PUBLISHED` / `ROOM_UPDATED` payload, also the `SharedRoom` item in search:

```json
{
  "pmsRoomId": "5:3f2e1d0c-0000-4000-8000-000000000301",
  "providerRef": "5:5b1c2d3e-0000-4000-8000-000000000150",
  "roomName": "Garden Twin",
  "roomType": "SINGLE_TWIN_BED",
  "branchName": "River Branch",
  "providerName": "Thu Bon Family Stays",
  "country": "VN",
  "city": "Hoi An",
  "pricePerNight": {"amountMinor":2500,"currency":"USD"},
  "totalQuantity": 4,
  "validUntil": "2027-12-01"
}
```

`ROOM_UNPUBLISHED` payload:

```json
{"pmsRoomId":"5:3f2e1d0c-0000-4000-8000-000000000301"}
```

Provider-mode `SEARCH_ROOMS` request and an empty OK result. CP omits `actingProviderId`. A nonempty `rooms` array contains the `SharedRoom` shape above.

```json
{"country":"SG","city":"Singapore","actingProviderId":"5b1c2d3e-0000-4000-8000-000000000150"}
```

```json
{"rooms":[]}
```

PMS calls `CHECK_ENTITLEMENT` first in provider mode. Request and OK result:

```json
{"providerId":"5b1c2d3e-0000-4000-8000-000000000150"}
```

```json
{"validUntil":"2027-12-01"}
```

`GET_AVAILABILITY` request and OK result:

```json
{"pmsRoomId":"5:3f2e1d0c-0000-4000-8000-000000000301","stay":{"checkInDate":"2027-04-10","checkOutDate":"2027-04-13"}}
```

```json
{"providerRef":"5:5b1c2d3e-0000-4000-8000-000000000150","availableQuantity":2}
```

### 3.2 Quote, book and cancel

> **Checkout is disabled pending agreement.** The shapes below are proposed, not permission to place a hold or capture payment. Enable quoting and new bookings only after both squads agree on payment mode, gateway account and currency, who captures, verifies, releases and refunds, and how booking updates reach the originating CP. Until then return `409 PMS_CHECKOUT_NOT_ENABLED` for new checkout writes. Do not block access to existing bookings or their cancellation when new checkout is disabled.

| Type (CP -> PMS -> owner PP) | Request | OK result |
|---|---|---|
| `CREATE_QUOTE` | `{ pmsRoomId: RoomId, country: country, customerId: uuid, stay: StayDates, quantity: integer >= 1, adults: integer >= 1, children: integer >= 0 }` | `{ quoteId: uuid, country: country, total: Money, holdExpiresAt: instant, payee: Payee }` |
| `CREATE_BOOKING` | `{ pmsRoomId: RoomId, country: country, quoteId: uuid, customer: CustomerSnapshot, payment: PaymentInfo }` | `BookingResult` |
| `GET_BOOKING` | `{ booking: BookingRoute, customerId: uuid }` | `BookingResult` |
| `CANCEL_BOOKING` | `{ booking: BookingRoute, customerId: uuid, reason?: string }` (max 500 chars) | `BookingResult` |

`Payee` is `{ gateway: PaymentGateway, payeeAccountId: string, payeeDisplayName: string }` as in [PP-OP-05](../provider-portal/PP-02-pricing-and-discounts.md#pp-op-05-createpricequote). `BookingResult` is `{ booking: BookingRoute, status: BookingStatus, returnPaymentStatus: ReturnPaymentStatus }`. `CustomerSnapshot`, `PaymentInfo` and status enums use the linked shared types. The escrow examples only illustrate the existing owner's payment shape. They do not select a shared gateway setup.

- PMS routes both writes by room prefix and supplied country, even if the room projection is gone. The owner verifies the shard against the room and quote. It binds each quote to the originating CP and customer using the existing quote and scoped idempotency records, and uses the normal occupancy rules and 15-minute hold. For booking creation, it reloads the dates, guests and quantity from the quote and verifies the capture directly with the agreed gateway after validating room, shard, quote, origin and customer. PMS does not capture money or keep a payment store.
- The owner keeps the existing [PP-OP-06](../provider-portal/PP-03-bookings.md#pp-op-06-createbooking) checks and one payment and at most one booking per quote. Apply [D-14](../common/03-agreed-decisions.md#d-14-booking-rejected-after-payment-was-captured) to an entitlement loss after capture: record a verified terminal rejection for an unbound capture before any authorized refund. A missing reply, unverified capture or routing error is not proof of rejection. Reconcile a lost create reply with the original key and payment. Do not charge again or change the shard to retry.
- Route status and cancellation by `BookingRoute`, independent of publication. Validate the booking's shard, originating CP and customer at owning PP using its existing booking, quote and scoped write records. Return `404 RESOURCE_NOT_FOUND` for a booking outside that scope. Apply [PP-OP-09](../provider-portal/PP-03-bookings.md#pp-op-09-cancelbookingbycustomer) cancellation rules. `PENDING` means money has not yet been returned. `GET_BOOKING` can read the latest owner status.
- `shortcut:` no cross-squad Premium discount and no new lifecycle event feed in this draft. Use Standard pricing and direct status reads. Agree on membership verification before adding discounts and on lifecycle delivery for notifications and refund reconciliation before enabling checkout.

`CREATE_QUOTE` request and OK result:

```json
{"pmsRoomId":"5:3f2e1d0c-0000-4000-8000-000000000301","country":"VN","customerId":"7d1e2f30-0000-4000-8000-000000000901","stay":{"checkInDate":"2027-04-10","checkOutDate":"2027-04-13"},"quantity":1,"adults":2,"children":0}
```

```json
{
  "quoteId": "1a2b3c4d-0000-4000-8000-000000000501",
  "country": "VN",
  "total": {"amountMinor":7500,"currency":"USD"},
  "holdExpiresAt": "2026-12-01T03:15:00Z",
  "payee": {"gateway":"STRIPE_SANDBOX","payeeAccountId":"acct_example","payeeDisplayName":"Thu Bon Family Stays"}
}
```

`CREATE_BOOKING` request and OK result:

```json
{
  "pmsRoomId": "5:3f2e1d0c-0000-4000-8000-000000000301",
  "country": "VN",
  "quoteId": "1a2b3c4d-0000-4000-8000-000000000501",
  "customer": {"customerId":"7d1e2f30-0000-4000-8000-000000000901","email":"guest@example.com","phone":"+6591234567","countryOfResidence":"SG"},
  "payment": {
    "mode":"ESCROW",
    "gateway":"STRIPE_SANDBOX",
    "orderId":"55aa66bb-0000-4000-8000-000000000701",
    "paymentReference":"pi_example",
    "chargeReference":"ch_example",
    "state":"CAPTURED_HELD",
    "amount":{"amountMinor":7500,"currency":"USD"},
    "paidAt":"2026-12-01T03:02:10Z"
  }
}
```

```json
{"booking":{"ownerSquadId":"5","country":"VN","bookingId":"8c9d0e1f-0000-4000-8000-000000000801"},"status":"PENDING_APPROVAL","returnPaymentStatus":"NOT_REQUIRED"}
```

`GET_BOOKING` request, and also `CANCEL_BOOKING` request with the optional `reason` omitted. The OK result below shows a successful cancellation, or a status read shortly after cancellation.

```json
{"booking":{"ownerSquadId":"5","country":"VN","bookingId":"8c9d0e1f-0000-4000-8000-000000000801"},"customerId":"7d1e2f30-0000-4000-8000-000000000901"}
```

```json
{"booking":{"ownerSquadId":"5","country":"VN","bookingId":"8c9d0e1f-0000-4000-8000-000000000801"},"status":"CANCELLED","returnPaymentStatus":"PENDING"}
```

### 3.3 Read permitted partner guest data

`GET_PARTNER_GUEST` (PP -> PMS -> same PP): request `{ actingProviderId: uuid, country: country, bookingId: uuid }`. OK result `{ email: string, phone: string, countryOfResidence: country }`, using the original partner CP booking snapshot only. This is a gated read of data supplied by a partner through PMS, not remote lookup by customer ID.

PMS routes only back to the calling PP's squad. The home PP verifies its provider's current entitlement, the booking's provider through its room, and a committed booking created by a different squad's CP using the existing scoped write record. Return `404 RESOURCE_NOT_FOUND` unless the booking is in scope and is `PENDING_APPROVAL` or `CONFIRMED`. No customer account, membership, guest history or payment details. Do not store a guest projection in PMS. This gate does not change the local booking workflow for existing reservations.

Request and OK result:

```json
{"actingProviderId":"5b1c2d3e-0000-4000-8000-000000000150","country":"VN","bookingId":"8c9d0e1f-0000-4000-8000-000000000801"}
```

```json
{"email":"guest@example.com","phone":"+6591234567","countryOfResidence":"SG"}
```

### 3.4 Read ratings and reviews

`GET_REVIEWS` (CP -> PMS -> review source CP): request `{ pmsRoomId: RoomId, reviewSquadId: squad, cursor?: string, limit?: integer }`. PMS checks the room with its owner, then sends `{ providerRef: ProviderRef, cursor?: string, limit?: integer }` to the specified participating CP. OK result: `{ providerRef: ProviderRef, reviewSquadId: squad, totalReviews: integer >= 0, average?: number, reviews: Review[], nextCursor?: string, asOf: instant }`.

`Review` is `{ reviewId: uuid, overallScore: number, text?: string, createdAt: instant }`. Scores and average are on the 1 to 5 scale. CP provides only public, non-archived reviews and no reviewer identifiers, private text or payment data. Scope the cursor to the caller, review source and provider. Limit 1 to 50, default 10. Sort newest first, with `reviewId` as tie-breaker. Omit `average` when `totalReviews` is zero. Both platforms can request each participating CP as a source. CPs remain authoritative for reviews they own. Callers combining summaries weight each average by its count and must not label a partial result as the combined rating.

`shortcut:` no ratings push or merged review cursor. Read one source at a time. Add a merged cursor only if a single ordered feed is required.

Request and OK result:

```json
{"pmsRoomId":"5:3f2e1d0c-0000-4000-8000-000000000301","reviewSquadId":"5","limit":10}
```

```json
{
  "providerRef": "5:5b1c2d3e-0000-4000-8000-000000000150",
  "reviewSquadId": "5",
  "totalReviews": 1,
  "average": 5,
  "reviews": [{"reviewId":"a1b2c3d4-0000-4000-8000-000000000601","overallScore":5,"text":"Quiet room and a good breakfast.","createdAt":"2026-10-02T08:00:00Z"}],
  "asOf": "2026-12-01T03:04:00Z"
}
```

## 4. Broker permissions and rejection

Proposed `SASL_SSL` and SCRAM-SHA-512 on the PMS broker. Register a distinct principal per squad and portal role (`<squad>-cp`, `<squad>-pp`) and one `pms-svc` principal. No anonymous access, no shared CP/PP credentials, no auto-creation and no wildcard partner grants. Admins provision exact topic and consumer-group ACLs. Credentials are exchanged out of band. There is no public PMS REST endpoint. Existing CP-PP client credentials do not grant PMS access.

For each squad and portal role let `P = pms.<squad>.<role>` (`cp` or `pp`). Every request has one paired response topic. These topic pairs use `correlationId` as key. All request types must match the route in Section 3.

| Topic | Producer -> consumer |
|---|---|
| `P.to-pms.request.v1` | That portal -> PMS |
| `P.to-pms.response.v1` | PMS -> only that portal's reply group |
| `P.from-pms.request.v1` | PMS -> only that portal's request group |
| `P.from-pms.response.v1` | That portal -> PMS |
| `pms.<squad>.pp.room.events.v1` | That squad's PP -> PMS |

- PMS derives caller squad and role from the incoming topic's exclusive write ACL. Kafka records do not expose the authenticated connection principal to consumers. Check `source` against the permitted producer for that topic. The same applies when a portal receives PMS requests or replies. Partners cannot produce on each other's channels, consume each other's replies, or write directly to owner topics.
- PMS derives the destination from validated room, booking or review routing fields, not from an arbitrary topic or URL supplied by a caller. It sets `origin` (string `<squad>-<role>`) on forwarded requests only. Portal peers accept `origin` only on their PMS-only inbound request topics. It is the original authenticated system identity, not an end-user credential. Never accept `origin` from an external caller. PMS calculates both reply topics from the route, and rejects a mismatched `replyTo` without sending to it.
- The broker rejects unknown or invalid credentials during authentication and denies topic or group access without an ACL. Neither case yields a PMS response. For a trusted system with a valid request envelope, a disallowed operation or forged scope returns `403 PARTNER_FORBIDDEN` on its fixed reply channel. A malformed payload returns `400 VALIDATION_ERROR` when safe to correlate. If the envelope cannot be safely correlated, drop it and record an ops-only diagnostic. Do not send credentials or raw card data or log guest data or payment references. Restrict broker retention and ops access before enabling real data.

A valid system request can still fail provider entitlement. Return `403 PMS_SUBSCRIPTION_INACTIVE` for an in-scope provider read or new checkout write denied by this rule. Example `ERROR` payload for `CHECK_ENTITLEMENT`, also used for the outer `SEARCH_ROOMS` rejection with the outer attempt's `requestId`:

```json
{
  "error": {
    "code": "PMS_SUBSCRIPTION_INACTIVE",
    "httpStatus": 403,
    "message": "The provider does not have an active PMS subscription.",
    "requestId": "0b6f8f4c-5a5e-4c55-8a39-31b2f1b9b0a7",
    "timestamp": "2027-12-01T00:01:00Z"
  }
}
```

## 5. Correlation, retries and replay

- Reuse the [Kafka envelope](../common/04-kafka.md#1-message-envelope) and `1.0` schema version. `source` must match the ACL principal's portal name or be `PMS` for `pms-svc`. PMS forwards with the `origin` field described above. Use the shared `X-Correlation-Id` to `correlationId` mapping at portal HTTP boundaries. One-way room events use the local room UUID as envelope `correlationId`, with no reply fields.
- On each hop, copy `correlationId` and `traceId` into the reply and match `causationId` to a sent attempt's `messageId`. PMS gives each distinct downstream call a separate correlation ID (including calls within one search) and carries the same trace and absolute deadline. It maps downstream replies back to the original request and its fixed reply channel. Use dedicated reply consumers. Verify source, type, trace and causation before accepting a reply. Ignore late or duplicate replies for closed requests.
- Apply the common [resend rules](../common/04-kafka.md#4-resend-policy-int-u03): up to three sends with backoff on publish failure, timeout, `503` or `504` only. The initiating portal owns retries. For reads, use 3 s per attempt, backoffs of 0.5 s and 1 s, and a 12 s budget. For quote, create and cancel, use 10 s per attempt, backoffs of 2 s and 4 s, and a 45 s budget. PMS does not independently retry or multiply the budgets. It makes at most one downstream send per needed call per upstream attempt. Bound fan-out by the search page and the caller's deadline. A resend keeps payload, correlation, trace, deadline and any idempotency key, but increments `attempt` and uses a new `messageId`. A responder does not start work past the deadline. Timeout is an unknown write outcome, not a rollback.
- Kafka delivery is at least once. Carry the original `idempotencyKey` through for quote, booking and cancellation. The owner uses durable records scoped to authenticated `origin`, operation and key, and still checks quote, order and payment uniqueness. Same key and body replays the committed outcome, changed input returns `409 IDEMPOTENCY_CONFLICT`, and unresolved work returns a retryable `503` without duplicating the write. Scope pending replies and any deduplication by authenticated origin as well as operation and correlation. Do not reuse cached read results to bypass entitlement or resource checks.

## 6. Before sign-off

Agree on the proposed fields and permissions (especially provider guest data), retention, hosting and operations for Machine 5, gateway and merchant ownership for subscriptions, and checkout money and lifecycle responsibilities. Confirm how each CP resolves provider-scoped reviews, including reviews from cross-squad stays. Confirm `PP-PMS-S02` with the lecturer. Verify broker denial, entitlement expiry with delayed withdrawal, and owner replay before rollout.
