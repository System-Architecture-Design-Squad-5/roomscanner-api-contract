# RoomScanner Squad API Contract

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

This repository is the single source of truth for every interaction between the two RoomScanner subsystems:

- **Provider Portal (PP)** (*frontend Ultimo, headless components*; *backend Ultimo, microservices*, `BE-U01`–`BE-U09`): the authoritative owner of providers, branches, rooms, availability, discount policies, reservations/bookings and beneficiary-side payment outcomes.
- **Customer Portal (CP)** (*frontend Ultimo, headless components*; *backend Medium, modular monolith*, `BE-M01`–`BE-M08`): the authoritative owner of customers, Premium membership, regional events and favorites, reviews and rating statistics, and payer-side payment initiation.

The contract is published in two equivalent forms:

| Form | Files | Purpose |
|---|---|---|
| Human-readable specification | `common/`, `provider-portal/`, `customer-portal/`, `pms/` | Business rules, agreed decisions, field tables, examples and rationale |
| Machine-readable specification | `specs/openapi/*.yaml` (OpenAPI 3.0.3), `specs/asyncapi/roomscanner-kafka.yaml` (AsyncAPI 3.0.0) | Industry-standard definitions for REST and Kafka. Open in Swagger Editor, Redoc or the AsyncAPI Studio; usable for client generation, mock servers and contract tests. |

It satisfies **TW-S02, TW-S06, TW-M01 and TW-U04** of the Common Technical Requirements. Every operation documents its endpoint or channel, protocol, description, typed request/response fields and example JSON objects (Section 8 maps each requirement to its location).

---

## 1. How to read this contract

Each **operation** (e.g. `PP-OP-06 CreateBooking`) is defined **once**, with one payload schema. The schema is then bound to the transport required by the integration level:

| Integration level | Transport used between PP and CP | Requirement |
|---|---|---|
| Simplex | REST (a standalone mock of the partner is allowed) | INT-S01, INT-S02 |
| Medium | REST against the **real** partner, with partner authentication. WebSocket for event suggestions. | INT-M01 to M03, PP-EVENT-M01 |
| **Ultimo** (target) | **Kafka request/response** with a send channel, a receive channel, a correlation ID and resend | INT-U01 to U03, BE-U09 |

Payload bodies are **identical across transports**, so moving up a level changes only the binding, never the data. This keeps the design consistent with the rule that "where a higher tier replaces an implementation, demonstrate the replacement rather than both versions".

## 2. Repository layout

```
roomscanner-api-contract/
|-- README.md                          index, operation catalogue, sign-off, requirement coverage
|-- CHANGELOG.md                       version history
|-- common/
|   |-- 01-conventions.md              base URLs, authentication, headers, errors, pagination, rate limits
|   |-- 02-shared-types.md             enumerations and reusable objects (Money, ProviderSearchResult, ...)
|   |-- 03-agreed-decisions.md         resolved SRS ambiguities and business rules (D-01 to D-17)
|   `-- 04-kafka.md                    envelope, topic catalogue, correlation, resend policy, ACLs
|-- provider-portal/                   services PP PROVIDES to CP
|   |-- PP-01-search-and-catalogue.md
|   |-- PP-02-pricing-and-discounts.md
|   |-- PP-03-bookings.md
|   |-- PP-04-booking-status-events.md
|   |-- PP-05-payment-flows.md
|   `-- PP-06-regional-event-suggestions.md
|-- customer-portal/                   services CP PROVIDES to PP (confirmed by CP)
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

| Task | How |
|---|---|
| Browse the REST APIs | Paste a file from `specs/openapi/` into https://editor.swagger.io, or run `npx @redocly/cli preview-docs specs/openapi/provider-portal-partner-api.yaml` |
| Browse the Kafka API | Paste `specs/asyncapi/roomscanner-kafka.yaml` into https://studio.asyncapi.com |
| Regenerate after a schema change | `python -m pip install -r tools/requirements-validation.txt`, then `python tools/generate_specs.py .` |
| Validate | OpenAPI: `openapi-spec-validator` or `redocly lint`. AsyncAPI: `asyncapi validate`. Every example in the three files has been checked against its schema. |

For the repository's repeatable checks, run:

```sh
python -m pip install -r tools/requirements-validation.txt
python tools/generate_specs.py .
python tools/validate_specs.py
```

The checks cover both OpenAPI documents, all embedded machine-readable examples, complete Markdown Kafka examples, JSON syntax, example price arithmetic, malformed Kafka/payment/event payloads, request/response correlation, retry budgets, custom bearer authentication, CP-order reconciliation and generator/spec consistency. Use Python 3.9 or newer. AsyncAPI document structure is a separate check (`asyncapi validate specs/asyncapi/roomscanner-kafka.yaml`); the Python suite validates its payloads and examples. This validates the contract; runtime duplicate protection, transactions, gateway access and failover still require implementation tests in the portal repositories.

The corrections recorded under **Unreleased** in `CHANGELOG.md` revise the unsigned v1.0.0 draft. Required trace/idempotency fields and stricter validation must be reviewed by both teams before the baseline is signed/tagged; these edits do not constitute team sign-off or a deployed API migration.

The 24 November review used `ProviderPortalSRS_v1.0.pdf`, `CustomerPortalSRS_v1.0.pdf`, `CommonRequirements_v1.0.pdf`, and the supplied `Lecturer_Answers_Project_Discussion.md` (23 November answers, last read 24 November). CP's Ultimo frontend + Medium modular monolith backend and PP's Ultimo frontend + microservices backend are compatible with independent architecture levels and Ultimo Kafka integration. This repository specifies partner APIs; it does not verify either frontend implementation or either backend's runtime behavior.

Remaining agreement points are the separate cross-squad PMS contract (typed messages, payments, shared review retrieval, storage and ownership), escrow selection given the conflicting SRS wording, and the two-month example's extra day. The existing lecturer-confirmation markers for amenities/search semantics, payment-return wording and SRS errata also remain in D-02, D-03, D-13 and D-17; the audit does not turn those interpretations into lecturer approval. The PMS draft now proposes direct CP and PP connections, as the lecturer's all-four-teams clarification requires. Existing D-01 to D-17 agreement labels record the earlier baseline review; they do not sign off these audit corrections.

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

1. Every change goes through a **pull request** to `main` and needs **one reviewer from each team** (this satisfies TW-M02 evidence).
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

The contract is binding for Milestone 1 once both teams have signed off below. Decisions marked "Lecturer confirmation" in `common/03-agreed-decisions.md` remain open points and do not block sign-off.

**Points each team confirms by signing:**
1. **Integration level.** Both teams implement the **Ultimo Kafka binding** of every CP↔PP operation (CP-MONEY-U01, CP-RATING-U01, CP-EVENT-U01 to U03 ↔ PP-SEARCH-U02, PP-RATING-U01, PP-EVENT-U01/U02), independent of each team's backend architecture (D-01).
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

| Requirement | What it asks for | Where it is met |
|---|---|---|
| TW-S02 | API contract in the squad's GitHub organization | This repository (separate repository, Section 2) |
| TW-S06 | Endpoint, protocol, brief description, abstract request/response for every API supplied to the partner, by Friday of Week N-2 | Section 3 index; every operation section in `provider-portal/` and `customer-portal/` |
| TW-M01 | JSON request and response structures with fields and data types | Field tables in every operation; `common/02-shared-types.md`; `specs/` schemas |
| TW-U04 | Example JSON objects for every endpoint | Example blocks in every operation; `examples` in `specs/openapi/*.yaml` and the AsyncAPI messages |
| TW-M02 | Reviewer assigned alongside the owner; feedback addressed | Section 5 change process; PR reviews (one reviewer from each team) |
| INT-S01, INT-S02 | Backend APIs for the partner; mocks allowed at Simplex | REST bindings of every operation |
| INT-M01, INT-M02 | Real partner REST in both directions | Section 3.1 (PP provides) and Section 3.2 (CP provides) |
| INT-M03 | Authenticate and authorize partner APIs; reject untrusted systems | `common/01-conventions.md` Section 4 (client credentials, scopes, webhook HMAC, IP allowlist) |
| INT-U01 to INT-U03 | Kafka request/response, send and receive channel, correlation, resend | `common/04-kafka.md` Sections 1 to 4; `specs/asyncapi/roomscanner-kafka.yaml` |
| BE-U04 | Rate limit: scope, threshold, window, response | `common/01-conventions.md` Section 7 |
| BE-U09 | Cross-ecosystem communication through the PMS over a message broker | `pms/PMS-cross-ecosystem-draft.md` |

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
