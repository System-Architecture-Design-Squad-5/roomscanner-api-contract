# RoomScanner Squad API Contract

**Start here:** [Shared conventions](common/01-conventions.md) | [Kafka rules](common/04-kafka.md) | [Cross-squad PMS draft](pms/PMS-cross-ecosystem-draft.md) (pending partner agreement)

| Document control | |
|---|---|
| Contract version | 1.0.0 |
| Contract deadline | Friday 20 November 2026, 18:00 ICT |
| Status | CP-reviewed baseline; 24 Nov audit corrections pending joint review |
| Squad | `5` |
| Sub-region and countries | Southeast Asia; Vietnam (`VN`) and Singapore (`SG`). "Country" is where the accommodation is located (lecturer answer, 23 Nov 2026). |
| Provider Portal team | `Team 9` |
| Customer Portal team | `Team 10` |
| Repository | `https://github.com/System-Architecture-Design-Squad-5/roomscanner-api-contract` |

This contract covers the APIs between Provider Portal (PP) and Customer Portal (CP). See the [operation index](#3-operation-index) and [ownership table](#4-ownership-boundaries-who-is-authoritative).

**Chosen architecture levels**

| Portal | Frontend | Backend |
|---|---|---|
| Provider Portal (PP) | **Ultimo** - headless components (`FE-U01`, `FE-U02`) | **Ultimo** - microservices (`BE-U01`–`BE-U09`) |
| Customer Portal (CP) | **Ultimo** - headless components (`FE-U01`, `FE-U02`) | **Medium** - modular monolith (`BE-M01`–`BE-M08`) |

The CP and PP integration target is **Ultimo Kafka** for both portals.

**Contract formats**

| Format | Where to look | What it covers |
|---|---|---|
| Human-readable (Markdown) | [Shared rules](common/), [PP operations](provider-portal/), [CP operations](customer-portal/CP-services-required-by-PP.md) | Endpoints, topics, business rules, typed fields and JSON examples. Start here for design and review. |
| Machine-readable (YAML) | [PP REST](specs/openapi/provider-portal-partner-api.yaml) and [CP REST](specs/openapi/customer-portal-partner-api.yaml) (OpenAPI 3.0.3); [Kafka](specs/asyncapi/roomscanner-kafka.yaml) (AsyncAPI 3.0.0) | Schemas and examples for validation, client generation and mocks. |

See [requirement coverage](#8-requirement-coverage) for the mapping to `TW-S02`, `TW-S06`, `TW-M01`, `TW-U04` and the integration requirements.

The cross-squad PMS draft has its own typed operations and examples. It is outside the binding CP-PP contract and generated specs until the squads sign a separate agreement.

---

## 1. How to read this contract

The operation ID stays the same across its supported transports. Use the binding for the selected integration level:

| Integration level | Transport used between PP and CP | Requirement |
|---|---|---|
| Simplex | REST (a standalone mock of the partner is allowed) | INT-S01, INT-S02 |
| Medium | REST against the **real** partner, with partner authentication. WebSocket for event suggestions. | INT-M01 to M03, PP-EVENT-M01 |
| **Ultimo** (target) | **Kafka request/response** with paired topics, correlation and retries; one-way topics for event publications | INT-U01 to U03 |

For operations with both bindings, Kafka combines REST path parameters, query parameters and any JSON body into one request payload. See the [Kafka envelope](common/04-kafka.md#1-message-envelope) for the response and error formats. At Ultimo, use Kafka wherever it replaces a lower-tier binding; there is no need to implement both.

## 2. Repository layout

```
roomscanner-api-contract/
|-- README.md                          index, operation catalogue, sign-off, requirement coverage
|-- CHANGELOG.md                       version history
|-- common/
|   |-- 01-conventions.md              base URLs, authentication, headers, errors, pagination, rate limits
|   |-- 02-shared-types.md             enumerations and reusable objects (Money, ProviderSearchResult, ...)
|   |-- 03-agreed-decisions.md         business rules and open SRS questions (D-01 to D-17)
|   `-- 04-kafka.md                    envelope, topic catalogue, correlation, resend policy, ACLs
|-- provider-portal/                   services PP provides to CP
|   |-- PP-01-search-and-catalogue.md
|   |-- PP-02-pricing-and-discounts.md
|   |-- PP-03-bookings.md
|   |-- PP-04-booking-status-events.md
|   |-- PP-05-payment-flows.md
|   `-- PP-06-regional-event-suggestions.md
|-- customer-portal/                   services CP provides to PP
|   |-- CP-services-required-by-PP.md    index of CP partner operations
|   |-- CP-01-rating-statistics.md       CP-OP-01 GetRatingStatistics
|   |-- CP-02-customer-membership.md     CP-OP-02 GetCustomerMembership
|   |-- CP-03-orders-and-booking-events.md  CP-OP-03, CP-OP-04
|   `-- CP-04-regional-event-favorites.md   CP-OP-05 EventFavoriteChanged
|-- pms/
|   `-- PMS-cross-ecosystem-draft.md   to be agreed with the partner squad
|-- specs/
|   |-- openapi/
|   |   |-- provider-portal-partner-api.yaml   REST API provided by PP (OpenAPI 3.0.3)
|   |   `-- customer-portal-partner-api.yaml   REST API provided by CP (OpenAPI 3.0.3)
|   `-- asyncapi/
|       `-- roomscanner-kafka.yaml             Kafka topics and messages (AsyncAPI 3.0.0)
`-- tools/
    |-- generate_specs.py              regenerates specs/ from one shared schema set
    |-- validate_specs.py              validates examples, schema regressions and generator sync
    `-- requirements-validation.txt    pinned validation dependencies
```

### 2.1 Viewing and validating the machine-readable specification

Browse the REST specs in [Swagger Editor](https://editor.swagger.io) and the Kafka spec in [AsyncAPI Studio](https://studio.asyncapi.com). To run the contract checks (Python 3.9 or newer):

```sh
python -m pip install -r tools/requirements-validation.txt
python tools/validate_specs.py
```

The script checks OpenAPI structure, payloads, examples and whether the specs match the generator. After changing a schema, run `python tools/generate_specs.py .` and rerun the checks. Use `asyncapi validate specs/asyncapi/roomscanner-kafka.yaml` separately to check AsyncAPI document structure. Gateway access, duplicate writes and failover need tests in the portal repositories.

## 3. Operation index

### 3.1 Provided by Provider Portal (consumed by CP)

| ID | Operation | REST (Simplex/Medium) | Kafka (Ultimo) | SRS traceability |
|---|---|---|---|---|
| PP-OP-01 | SearchProviders | `GET /api/v1/partner/search/providers` | `rs.search.request.v1` → `rs.search.response.v1` | PP-SEARCH-S01, S02, M01, M02, U01, U02 · CP-SEARCH-S01, S02, M01, M02 |
| PP-OP-02 | GetBranchDetails | `GET /api/v1/partner/branches/{branchId}` | same search topics (`type=GET_BRANCH`) | PP-SEARCH-S02 · CP-SEARCH-S03 |
| PP-OP-03 | ListBranchRooms | `GET /api/v1/partner/branches/{branchId}/rooms` | same search topics (`type=LIST_ROOMS`) | PP-SEARCH-S03, PP-ROOM-U02 · CP-SEARCH-S03 |
| PP-OP-04 | GetRoomDetails | `GET /api/v1/partner/rooms/{roomId}` | same search topics (`type=GET_ROOM`) | PP-ROOM-S05, S06 · CP-SEARCH-S03 |
| PP-OP-05 | CreatePriceQuote | `POST /api/v1/partner/quotes` | `rs.booking.request.v1` (`type=CREATE_QUOTE`) | PP-DISCOUNT-S01, S02 · CP exchange "Premium room discounts" |
| PP-OP-06 | CreateBooking | `POST /api/v1/partner/bookings` | `rs.booking.request.v1` → `rs.booking.response.v1` | PP-BOOK-S01, S02, U01, PP-MONEY-M01, U01 · CP-BOOK-S01, S02, CP-MONEY-M01, U01, U04 |
| PP-OP-07 | GetBooking | `GET /api/v1/partner/bookings/{bookingId}` | `rs.booking.request.v1` (`type=GET_BOOKING`) | PP-MONEY-M03 · CP-MONEY-U02 |
| PP-OP-08 | ListCustomerBookings | `GET /api/v1/partner/customers/{customerId}/bookings` | `rs.booking.request.v1` (`type=LIST_BOOKINGS`) | CP-BOOK-S02 (3 booking groups) |
| PP-OP-09 | CancelBookingByCustomer | `POST /api/v1/partner/bookings/{bookingId}/cancellations` | `rs.booking.request.v1` (`type=CANCEL_BOOKING`) | PP-BOOK-S02, PP-MONEY-S01, M02 · CP-MONEY-M03, U03 |
| PP-OP-10 | GetReviewEligibility | `GET /api/v1/partner/bookings/{bookingId}/review-eligibility` | `rs.booking.request.v1` (`type=GET_ELIGIBILITY`) | PP-BOOK-S01, PP-RATING-S01 · CP-RATING-S01 |
| PP-OP-11 | BookingStatusEvent (PP → CP push) | PP calls CP webhook `POST /api/v1/partner/booking-events` (see CP-OP-04) | `rs.booking.events.v1` | PP-MONEY-S01, M03, U01 · CP-MONEY-S01, M02, U02 |
| PP-OP-12 | RequestEventSuggestions | Simplex: `POST /api/v1/partner/event-suggestions` · Medium: STOMP over WebSocket | N/A | PP-EVENT-S01, S02, M01 · CP-EVENT-M02, M03 |
| PP-OP-13 | PublishEventNotification | N/A | PP publishes to the CP-created `rs.event.notification.v1` | PP-EVENT-U01, U02 · CP-EVENT-U01 to U03 |

### 3.2 Provided by Customer Portal (consumed by PP)

| ID | Operation | REST (Simplex/Medium) | Kafka (Ultimo) | SRS traceability |
|---|---|---|---|---|
| CP-OP-01 | GetRatingStatistics | `GET /api/v1/partner/providers/{providerId}/rating-statistics` | `rs.rating-stats.request.v1` → `rs.rating-stats.response.v1` | PP-RATING-S01, M01, U01, U02 · CP-RATING-M03, U01, U02 |
| CP-OP-02 | GetCustomerMembership | `GET /api/v1/partner/customers/{customerId}/membership` | `rs.membership.request.v1` → `rs.membership.response.v1` | PP-DISCOUNT-S02 |
| CP-OP-03 | UpdateSimulatedOrder (Simplex only) | `PATCH /api/v1/partner/orders/{orderId}` | N/A (replaced by real payment at Medium+) | PP-MONEY-S01 · CP-MONEY-S01 |
| CP-OP-04 | ReceiveBookingEvent (webhook) | `POST /api/v1/partner/booking-events` | N/A (replaced by `rs.booking.events.v1`) | PP-MONEY-S01, M03 · CP-MONEY-M02 |
| CP-OP-05 | EventFavoriteChanged | N/A | `rs.event.favorite.v1` (CP → PP) | CP-EVENT-U01, U03 · PP-EVENT-U02 |

## 4. Ownership boundaries (who is authoritative)

| Data | Owner | The other side may... | The other side must NOT... |
|---|---|---|---|
| Providers, branches, rooms, images, amenities, availability | **PP** | read via PP-OP-01…04 | store availability as its source of truth |
| Discount packages and room policies; price calculation | **PP** | request quotes (PP-OP-05) | compute discounts itself |
| Reservations/bookings, approval, cancellation outcome | **PP** | create (PP-OP-06), request cancellation (PP-OP-09), read status | approve a booking or complete the lifecycle alone (CP-MONEY-M02) |
| Customers, Premium membership | **CP** | read membership (CP-OP-02); receive a booking-time snapshot | read customer accounts beyond the agreed fields |
| Reviews and rating statistics | **CP** | request statistics (CP-OP-01) | recalculate statistics (PP-RATING-S01, M01) |
| Regional events and favorites | **CP** | receive event/city info (PP-OP-12, CP-OP-05) | administer events or store favorites as authoritative |
| Payer-side payment initiation (authorize/capture) | **CP** | verify with the gateway using the reference | charge the customer again |
| Beneficiary-side payout/release/refund | **PP** | display the outcome | trigger a provider payout |

## 5. Change process

1. Open a **pull request** to `main` with **one reviewer from each team**. Record how you addressed their feedback (`TW-M02`).
2. Bump the contract version: **MAJOR** for breaking changes (and a new `/v2` path or `.v2` topic), **MINOR** for new optional fields or operations, **PATCH** for wording.
3. Record every change in `CHANGELOG.md`, with the GitHub issue/task number.
4. Breaking changes inside 7 days of a milestone deadline need both team leads to approve them.

## 6. Contract task on the Project Board

Track this contract as a **separate task** in the *Documentation* column (Common Req. Section 4.1), with an assignee, deadline, effort estimate, reviewer and this Definition of Done:

- [x] All PP-provided operations documented with endpoint, protocol, description, typed fields and example JSON
- [x] All CP-provided operations required by PP listed and confirmed by CP
- [x] OpenAPI and AsyncAPI files regenerated and validated
- [ ] Agreed decisions signed off by both teams (`common/03-agreed-decisions.md`): fill in Section 7
- [ ] Reviewed by at least one CP member and one PP member; feedback addressed and recorded in the PR
- [ ] Tagged `v1.0.0` before Fri 20 Nov 2026, 18:00

## 7. Sign-off

Both teams must sign off on the revised Milestone 1 draft. The earlier review does not approve the [unreleased changes](CHANGELOG.md), including the required trace and idempotency fields. Items marked “Lecturer confirmation” in the [decisions log](common/03-agreed-decisions.md) remain open but do not block sign-off on the CP↔PP draft.

The open decisions include escrow scope (D-07), the two-month event notification cutoff (D-12), and the other lecturer-confirmation items listed in the decisions log. The cross-squad PMS agreement has its own review.

**Points each team confirms by signing:**
1. **Integration level.** Both teams use the **Ultimo Kafka bindings** in the operation index, regardless of backend architecture ([D-01](common/03-agreed-decisions.md#d-01-target-integration-level-and-transports)).
2. **Payment compensation (D-14).** At Medium (`DIRECT`) PP refunds a terminally rejected, unbound capture; at Ultimo (`ESCROW`) CP refunds its own platform charge.
3. **CP module names** used in this contract (`MembershipModule`, `EventModule`, `RatingModule`, `BookingModule`, `SearchModule`, `PartnerIntegrationModule`) match CP's C4 component diagrams (ARCH-D06).

| Team | Name | Role | Date | Pull request |
|---|---|---|---|---|
| Provider Portal | `[NAME]` | Team lead | | `#[PR]` |
| Provider Portal | `[NAME]` | Reviewer | | `#[PR]` |
| Customer Portal | `[NAME]` | Team lead | | `#[PR]` |
| Customer Portal | `[NAME]` | Reviewer | | `#[PR]` |

## 8. Requirement coverage

### 8.1 Contract documentation requirements (Common Technical Requirements)

| Requirement | Evidence |
|---|---|
| `TW-S02` | This separate contract repository in the squad's GitHub organization. |
| `TW-S06` | [Operation index](#3-operation-index) and operation pages: endpoints, protocols, descriptions and request/response outlines. Check GitHub history for publication by Friday of Week N−2. |
| `TW-M01`, `TW-U04` | Typed request/response fields and JSON examples in the operation pages and generated specs. |
| `TW-M02` | Review task and PR: owner and reviewer assignments, plus how feedback was addressed. See the [change process](#5-change-process). |
| `INT-S01`–`INT-S02`, `INT-M01`–`INT-M02` | [REST bindings](#3-operation-index) for both directions: mocks allowed at Simplex; actual partner at Medium. |
| `INT-M03` | [Partner authentication](common/01-conventions.md#4-partner-authentication-and-authorization-int-m03): credentials, scopes and rejection of untrusted callers. |
| `INT-U01`–`INT-U03` | [Kafka rules](common/04-kafka.md) and [AsyncAPI](specs/asyncapi/roomscanner-kafka.yaml): paired topics, correlation and retries. |
| `BE-U04` | [Rate limits](common/01-conventions.md#7-rate-limits): scope, threshold, window and response. |
| `BE-U09`, `DEP-U05` | [PMS draft](pms/PMS-cross-ecosystem-draft.md): broker-based cross-squad exchange, typed operations, Machine 5 and untrusted-system rejection. Partner agreement pending. |

### 8.2 Functional exchanges (SRS Section 3 of both subsystems)

| SRS exchange | Operations | Key decisions |
|---|---|---|
| Room search, catalogue and availability | PP-OP-01 to PP-OP-04 | D-02, D-03, D-04, D-05 |
| Reservations, customer eligibility and booking outcomes | PP-OP-06 to PP-OP-10, PP-OP-11 | D-08, D-09, D-10, D-14 |
| Monetary order and status | PP-OP-06, PP-OP-09, PP-OP-11, CP-OP-03, CP-OP-04; `provider-portal/PP-05-payment-flows.md` | D-07, D-13, D-14 |
| Reviews and rating statistics | CP-OP-01 | D-11 |
| Premium discounts | PP-OP-05, CP-OP-02 | D-06 |
| Regional-event notifications | PP-OP-12, PP-OP-13, CP-OP-05 | D-12 |
| Cross-ecosystem PMS | `pms/PMS-cross-ecosystem-draft.md` (draft, pending partner squad) | PP-PMS-S01, S02 |
