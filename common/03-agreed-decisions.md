# 03: Agreed Decisions and Business Rules

The SRS documents leave several details to the teams ("teams document fields, access scope, criteria, limits, aggregation rules and failure behaviour in their design and agreed API contract", Common Req. §1). Some SRS statements also conflict with each other. This file records each decision, its rationale, and its status.

**Status legend:**

| Status | Meaning |
|---|---|
| Proposed | Drafted by PP, awaiting CP sign-off in the contract pull request |
| Agreed | Signed off by both teams (see the sign-off table in `README.md`, Section 7) |
| Lecturer confirmation | Interpretation of an ambiguous SRS statement; raised with the lecturer and tracked as a blocker in stand-up minutes until answered |

| ID | Topic | Status |
|---|---|---|
| D-01 | Target integration level and transports | Agreed |
| D-02 | Unified amenity / service list | Agreed; Lecturer confirmation |
| D-03 | Search matching and filter semantics | Agreed; Lecturer confirmation |
| D-04 | Search result unit and category vs room type | Agreed |
| D-05 | Availability calculation | Agreed |
| D-06 | Premium discount calculation, eligibility and policy changes | Agreed |
| D-07 | Payment gateways per level | Agreed |
| D-08 | Cancellation rules | Agreed |
| D-09 | Mapping booking status to CP's three booking groups | Agreed |
| D-10 | Review eligibility | Agreed |
| D-11 | Rating statistics: denominators and PP caching | Agreed |
| D-12 | Event suggestions: ranking and the two-month rule | Agreed; Lecturer confirmation |
| D-13 | Medium "refund" wording vs separate payout | Agreed; Lecturer confirmation |
| D-14 | Booking rejected after payment was captured | Agreed |
| D-15 | Time zones | Agreed |
| D-16 | Data minimisation | Agreed |
| D-17 | SRS errata noted by the squad | Agreed; Lecturer confirmation |

---

### D-01 Target integration level and transports
- **Decision:** The contract is written to **Ultimo** detail (typed fields + examples, TW-U04). Each operation lists its REST binding (Simplex/Medium) and its Kafka binding (Ultimo). The squad implements **one** binding per operation at Milestone 2, matching the selected level.
- **Subsystem Architecture Independence (Common Req. §2 & §5):** Backend architecture levels are selected independently per team: **Customer Portal (CP)** uses a **Modular Monolith** (`BE-M01`–`BE-M08`), while **Provider Portal (PP)** uses **Microservices** (`BE-U01`–`BE-U09`). Both subsystems exchange the exact same Ultimo Kafka messages and REST payloads across the partner boundary.
- **Rationale:** One schema across transports and subsystem architectures means upgrading or deploying either side never changes the contract data, and C4 diagrams show the same payloads at every level.

### D-02 Unified amenity / service list
- **Conflict:** CP-SEARCH-S02 lists *Free WiFi, Private Bathroom, Air-conditioning, Facilities for Disabled Guests*. PP-ROOM-S06 lists *Free Wifi, Kitchen, Washing Machine, Pets Allowed*.
- **Decision:** Use the **union of 7 amenities** (`02-shared-types.md`, `Amenity`). Rooms are tagged by PP (PP-ROOM-M01). CP filters on any of the 7.
- **Rationale:** This satisfies both SRSs (CP: ≥ 4 service filters; PP: the 4 named amenities) without inventing a free-form taxonomy (PP-ROOM-M01).

### D-03 Search matching and filter semantics
- **Simplex (PP-SEARCH-S01, CP-SEARCH-S01):** `q` is a **case-insensitive substring** match on `providerName` and `branchName` (e.g. `"he"` matches "Sheraton Hotel" and "Henry Suites"). `city` is required. The `category`, `roomType` and `amenities` filters are optional.
- **Medium (PP-SEARCH-M01, CP-SEARCH-M01), multi-field Full-Text Search:**
  1. `q` is tokenised and searched across `providerName`, `branchName`, `description`, `category` labels, `roomType` labels and `amenity` labels.
  2. Phrases recognised in `q` that name a classification (e.g. "Homestay", "Single Bed", "Free WiFi") are mapped to the matching enum values.
  3. **OR semantics:** a provider matches if it satisfies **any** term or filter. Results are **ranked by the number of matched terms and filters**, then by FTS relevance. So for `"Single Bed Free WiFi Homestay"`, the Homestay providers offering both a Single Bed and Free WiFi rank first.
  4. Optional `matchMode=ALL` lets CP ask for strict AND matching (only providers matching every term).
- **Open point (lecturer confirmation):** The SRS says "OR semantics", but its example describes results that satisfy all three terms. The design above meets both readings: OR retrieval with matches-all ranked first, plus an opt-in strict mode.

### D-04 Search result unit, and category vs room type
- **Decision:** A search result is a **branch** (one property at one address), because providers may own several branches (PP-ROOM-S01) and search is per city.
- `category` (`RESORT`/`HOTEL`/`MOTEL_HOSTEL`/`HOMESTAY`) classifies the **provider**. `roomType` (`BUNK_BED`/`SINGLE_TWIN_BED`/`DOUBLE_BED`) classifies the **room**. Both are filterable. This reconciles PP-SEARCH-S01 ("room category" = provider categories) with CP-SEARCH-S01 (room types).

### D-05 Availability calculation
- `availableQuantity(room, checkIn, checkOut) = totalQuantity − max over each night n in [checkIn, checkOut) of (Σ quantity of PENDING_APPROVAL + CONFIRMED bookings covering n + Σ active quote holds covering n)`.
- When no dates are supplied, availability is computed for **tonight** (checkIn = today, checkOut = tomorrow, branch local time).
- Only rooms with `availableQuantity ≥ requested quantity` (default 1) are returned as "available".
- Archived rooms and branches (PP-ROOM-S04) are never returned.

### D-06 Premium discount calculation, eligibility and policy changes (PP-DISCOUNT-S01, S02)
- **Who calculates:** PP only, through **PP-OP-05 CreatePriceQuote**. CP charges exactly `priceBreakdown.total`.
- **One policy per room:** A room listing has 0 or 1 assigned discount package. One package can be assigned to many rooms.
- **Calculation:**
  - `PERCENTAGE`: discount = round_half_up(subtotal × value / 100).
  - `FIXED_PER_NIGHT`: discount = value × nights × quantity, capped at the subtotal.
- **Eligibility timing:** The customer must be `PREMIUM` with status `ACTIVE` **at quote time and at booking creation time**. PP verifies this with CP-OP-02 and does not rely only on the snapshot CP sends. The membership expiring **after** booking creation does not change the booking.
- If Premium eligibility ends between quote and creation, PP returns `MEMBERSHIP_ELIGIBILITY_CHANGED`; it must not increase an already-captured price. The unbound request is durably rejected before CP returns the captured payment and asks for a new quote. Dependency unavailability remains retryable and does not authorize compensation (PP-03).
- **Policy change or cancellation:** This affects **new quotes only**. Existing bookings keep their `AppliedDiscount` snapshot, and open quotes keep their price until they expire. No per-booking discount program is created.

### D-07 Payment gateways per level
| Level | Gateway | Payer (CP) | Beneficiary (PP) |
|---|---|---|---|
| Simplex | none (`SIMULATED`) | Issues a simulated order | Completes/cancels it via CP-OP-03 |
| Medium | **PayPal Sandbox** | Orders API: capture to the **provider's PayPal sandbox merchant account** (direct customer-to-provider payment) | On cancellation, a **Payouts API** transfer from the provider account to the customer's PayPal email. This is a separate payment with its own reference (PP-MONEY-M02). |
| Ultimo | **Stripe Sandbox with Connect** (separate charges and transfers) | PaymentIntent with `capture_method=manual` → **authorize**, then **capture** into the platform balance (held) | On approval: **release** via a Transfer to the provider's connected account (`source_transaction` = charge). The provider's connected account then makes a **Payout** to bank. On cancellation: **refund** the charge. |
- **Shared-platform ownership:** The squad configures one Stripe Connect sandbox platform, with its platform account ID recorded as `STRIPE_PLATFORM_ACCOUNT_ID` in each subsystem's environment. CP creates/captures the platform charge; PP releases, reverses and refunds that same platform's objects. Use separate least-privilege service credentials for this platform, not unrelated CP/PP Stripe accounts. Provider connected-account IDs are destinations belonging to this platform. PP-05 defines reversal outcomes and webhook ownership.
- **Rationale:** PayPal Payouts supports a true provider-to-customer payment that is separate from the original (needed for Medium). Stripe Connect natively supports all five escrow operations (authorize, capture, release/transfer, payout, refund) required by PP-MONEY-U01 and CP-MONEY-U04.
- Each provider stores its `paymentAccountId` (PayPal merchant ID / Stripe `acct_…`). PP returns it in the quote, so CP never needs provider account data.

### D-08 Cancellation rules
| Actor | Allowed when | Money returned |
|---|---|---|
| Customer (via CP, PP-OP-09) | Status `PENDING_APPROVAL` or `CONFIRMED`, and today (branch local) < `checkInDate` | 100% of `priceBreakdown.total` |
| Receptionist (PP frontend) | Status `PENDING_APPROVAL` or `CONFIRMED`, and today < `checkOutDate` | 100% |
| Anyone | `CANCELLED` or `COMPLETED` | `409 STATE_CONFLICT` |
- A cancellation **releases the reserved quantity immediately**, then starts the return (Medium payout / Ultimo refund). The booking is `CANCELLED` even while the return is `PENDING` or `FAILED`. A failed return is retried by PP (3 attempts) and stays visible to both sides (PP-MONEY-M03).

### D-09 Mapping booking status to CP's three booking groups (CP-BOOK-S02)
PP supplies `status` and the dates. CP combines them with its own review data (CP owns reviews):

| CP group | Rule |
|---|---|
| 1. Pending and Active | `status ∈ {PENDING_APPROVAL, CONFIRMED}` and today ≤ `checkOutDate` |
| 2. Not Reviewed | `status ∈ {CONFIRMED, COMPLETED}`, today ≥ `checkInDate`, and CP has **no** review for this booking |
| 3. Past | Reviewed by the customer, and today > `checkOutDate` |
| (Cancelled) | `status = CANCELLED`, shown in a separate filter in CP |
A confirmed, ongoing stay with no review appears in groups 1 and 2. CP decides how to present that overlap.
- **CP Modular Monolith implementation:** CP's `BookingModule` (`GET /api/v1/customer/bookings?group=PENDING_AND_ACTIVE|NOT_REVIEWED|PAST|CANCELLED`) fetches bookings via `PP-OP-08` and joins them in-process with `RatingModule` via `IRatingExternalService` (`ReviewedBookingIdsDto`).

### D-10 Review eligibility (PP-BOOK-S01, PP-RATING-S01, CP-RATING-S01)
- A booking is eligible for a **provider-level** review when: `status ∈ {CONFIRMED, COMPLETED}`, the requesting `customerId` owns the booking, and today (branch local) ≥ `checkInDate`.
- PP returns `reviewableFrom = checkInDate`. A cancelled booking is never eligible. Eligibility is checked per booking, so one review per booking (CP's rule).
- **CP endpoint alignment:** CP exposes `GET /api/v1/customer/bookings/{bookingId}/review-eligibility` (backed by `PP-OP-10`) and re-verifies eligibility on `POST /api/v1/customer/reviews`, returning `403 RATING_ELIGIBILITY_DENIED` if ineligible.

### D-11 Rating statistics: denominators and PP caching (PP-RATING-S01, M01; CP-RATING-M03)
- **Overall:** `average` = mean of the Overall scores of **active** (non-archived) reviews. `count` = number of active reviews. A distribution of counts per star value 1-5 is included.
- **Subcategory average:** mean over the active reviews that scored that subcategory.
- **Preset option percentage:** `selectedCount / denominator × 100`, rounded to 1 decimal. **`denominator` = the number of reviews whose score for that subcategory falls in the option's star group.** Options are only offered for that group, and customers may pick 0, 1 or 2 (CP-RATING-M02). Reviews that picked no option still count in the denominator.
- **PP caching:** PP caches CP's response in Redis (`rating:provider:{providerId}`, TTL **10 min**) to show ratings in search results and the provider dashboard. PP **never recalculates**. On a cache miss with CP unavailable, PP shows "Rating temporarily unavailable" and does **not** substitute a value of its own.
- **CP local endpoints:** CP's `GET /api/v1/customer/reviews/preset-options` and `GET /api/v1/customer/providers/{providerId}/reviews` read directly from CP's `providerId`-sharded `RatingModule` (`BE-M07`) using this same denominator calculation.

### D-12 Event suggestions: ranking and the two-month rule
- **Top-2 ranking (PP-EVENT-S02, CP-EVENT-M02):** The candidates are active branches in the event's `city` + `country` with ≥ 1 available room for the event dates. They are ranked by `overallAverage` (from CP statistics) descending, then `totalReviews` descending, then `lowestPricePerNight` ascending. Branches with 0 reviews rank after rated ones. If fewer than 2 candidates exist, PP returns what it has (possibly an empty list, with `reason`).
- **Two-month rule (Ultimo, CP-EVENT-U03, PP-EVENT-U02):**
  - `notificationWindowStart = (eventStartDate − 2 calendar months − 1 day)` at 00:00 in the event's time zone. This reproduces the SRS worked example: an event starting **12 Apr 2027** gives a window start of **11 Feb 2027**.
  - Favorited **on or after** the window start, and before the event ends → PP publishes **immediately**.
  - Favorited **before** the window start → PP schedules publication **at** the window start.
  - Event already ended → nothing is published.
  - **Edits & Deletion:** Only a change to `startDate` or `endDate` (`EVENT_DATES_CHANGED`) re-computes the schedule. Any other event edit (title, description) does **not** trigger or move a notification. If an admin deletes an event (`EVENT_DELETED`), PP cancels all pending scheduled notifications for that `eventId`. A notification that was already published is not re-sent.
  - Unfavorite before publication (`FAVORITE_REMOVED`) → the scheduled publication is cancelled.
- **Open point (lecturer confirmation):** whether the "−1 day" interpretation of the example is intended.

### D-13 Medium "refund" wording vs a separate payout
- **Conflict:** CP-MONEY-M03 says "trigger a refund". PP-MONEY-M02 says the return is a **separate** provider-to-customer payout and is "not the original payment's refund-API operation".
- **Decision:** Follow PP-MONEY-M02, the beneficiary's own specification: Medium uses a **PayPal payout**. CP displays it to the customer as a "refund", but in data it is `returnPaymentReference` (payout), separate from `originalPaymentReference`. At Ultimo, escrow uses the real Stripe refund.

### D-14 Booking rejected after payment was captured
- **Problem:** At Medium/Ultimo, CP captures the payment **before** sending the booking. The booking can then be rejected (rooms sold out, quote expired, validation error).
- **Mitigation:** PP-OP-05 places a **15-minute quote hold** on the inventory. PP atomically consumes it and enforces unique quote, CP order and gateway-payment bindings when creating the booking; a hold reduces risk but does not replace rejection/reconciliation rules.
- **Terminal rejection:** PP must durably close the create request and verify no booking/payment binding exists before returning `refundRequiredByPayer=true`. Atomically mark the quote, CP order and payment identities `REJECTED_COMPENSATION_AUTHORIZED` so no request under another key can later create a booking with them. CP then compensates its own verified, unbound original capture and displays the exact cause. Replays return the recorded rejection; a new purchase needs new quote/order/payment identities.
- **Ambiguous failure:** Timeout/503, lost acknowledgement or a duplicate binding is not proof of rejection. Preserve the write key and reconcile through the durable replay result and PP-OP-08's customer/order lookup. Never refund solely because a response was lost or an in-flight lookup was empty. Unique bindings remain after Redis expiry and workflow archiving.

### D-15 Time zones
- Stay dates and "today" checks use the **branch's** IANA time zone (e.g. `Asia/Ho_Chi_Minh`, `Asia/Bangkok`).
- Event timing uses the **event's** time zone. Timestamps on the wire are always UTC.

### D-16 Data minimisation (PP-SEARCH-S02, BE-M05)
- Search and catalogue responses never contain provider account email, phone, password hashes, payment account IDs, or PMS subscription data.
- PP-OP-05 returns `payeeAccountId` **only** to the authenticated CP partner, and only in a quote.
- CP sends only `CustomerSnapshot` fields. Passport number and birthday are never shared.

### D-17 SRS errata noted by the squad
Recorded so that reviewers see these were noticed and handled:

| Item | Observation | Handling |
|---|---|---|
| CP-BOOK-S02 | ID used twice (quantity rule and three booking groups) | Referenced as CP-BOOK-S02(a)/(b) in our design |
| CP-MONEY-M02 | ID used under both Simplex and Medium | Referenced as CP-MONEY-M02(S)/(M) |
| CP-LOGIN-U05, PP-LOGIN-U05 | Missing from the sequence in both SRSs | No action |
| PP-PMS-S02 | Listed under Ultimo with an "S" ID, and says "while the premium membership is active" although Section 2.9 is about the provider's PMS subscription | Treated as an Ultimo requirement gated on the provider's **PMS subscription** (not customer Premium) |
| PP-ROOM-U02 | Same text as PP-SEARCH-U02 | Covered by PP-OP-01…04 Kafka binding |
| PP-SEARCH-U01 | Mentions "rating information" | Interpreted as "search information" |
| CP exchange table | Mentions a redundant rating service at Ultimo | **Confirmed by CP:** CP runs a standby redundant rating instance in consumer group `cp-rating-service` (`04-kafka.md` §5), so PP's resend policy works seamlessly. |
| CP-RATING-S01 | Says "create a review for a room", while CP Section 2.6 and PP Section 2.7 say reviews target the provider | Reviews target the **provider**; PP-OP-10 returns `providerId` as the review target |
| CP-SEARCH-S02 | Refers to "CP-SEARCH-01" | Read as CP-SEARCH-S01 |
| PP Section 2.4.3 | States there are no Ultimo room requirements, but PP-ROOM-U02 appears in Section 2.6.3 | PP-ROOM-U02 is honoured through the Kafka binding of PP-OP-01 to PP-OP-04 |
| CP-SUB-S01 evidence | "sends configured emails" on expiry | CP-only; no PP impact |
