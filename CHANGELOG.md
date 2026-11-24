# Changelog

All notable changes to the squad API contract. Versioning follows the rules in `README.md` Section 5 (MAJOR for breaking changes, MINOR for additive changes, PATCH for wording).

## [Unreleased] - 2026-11-24 (CP–PP consistency audit)

Principle: PP is the reference. Where the two sides differed, CP was aligned to PP; PP files changed only to copy codes already in PP's own OpenAPI into its Markdown and to fix one example country.

### Fixed
- `tools/generate_specs.py` crashed on `EVENT_DELETED` (added to CP-04 but not to the Kafka type registry), and the checked-in AsyncAPI schema rejected every `EVENT_DELETED` message. Registered the type, added its payload branch and an example, and a regression test in `tools/validate_specs.py`. Added `EVENT_DELETED` to the `rs.event.favorite.v1` row in `04-kafka.md` and to the CP index.
- Countries aligned to the squad's **Vietnam (VN) and Singapore (SG)**: README control table, D-15 time zones (`Asia/Singapore`), PP-04 example booking code (`RS-SG-…`).
- `01-conventions.md` §3: `X-Correlation-Id` now means one logical operation (as in `04-kafka.md` and the OpenAPI); added the missing `X-Trace-Id` row (business flow); `Idempotency-Key` row states durable uniqueness.
- Added the required `traceId` to the CP-01, CP-02 and CP-04 Kafka envelope examples; documented the CP-04 one-way envelope and correlation rule.
- Markdown error tables now match the generated OpenAPI: 401/403/429/503 (and 400 where missing) for PP-OP-05 to PP-OP-10 and CP-OP-01 to CP-OP-04. `IDEMPOTENCY_CONFLICT` (already a convention for every write) is listed for PP-OP-05 and PP-OP-09 in both forms. `event-suggestion:write` now has a rate-limit class (write). No PP behaviour changed.
- CP-04: CP admins create events only in VN/SG cities with PP's city naming, so PP-OP-12 / CP-OP-05 never carry an out-of-region city (CP adapts; no new PP error).
- CP-01: replaced the non-existent requirement ID `CP-EXCH-U01` with CP SRS §3.
- **Architecture levels made explicit and consistent:** PP = Ultimo frontend (headless) + Ultimo backend (microservices); CP = Ultimo frontend (headless) + **Medium** backend (modular monolith). Stated in README, `01-conventions.md` §1 and D-01. Removed wording that implied CP microservices: CP's deployed host is now `cp-api.<squad>…` (CP has no API Gateway), CP rating redundancy is a second instance of the monolith (not a "standby rating service"), CP's partner rate limiting sits in its cross-cutting filter layer, and the Simplex ID `BE-S03` was dropped from CP's description.
- PP-OP-06 OpenAPI examples now cover every code in its Markdown error table (`QUOTE_MISMATCH`, `INSUFFICIENT_AVAILABILITY`, `ORDER_ALREADY_BOUND`, `QUOTE_ALREADY_CONSUMED`, `BOOKING_QUANTITY_EXCEEDS_GUESTS`, `OCCUPANCY_EXCEEDED`, `PAYMENT_REFERENCE_MISMATCH`).
- The generated `429 RATE_LIMITED` example no longer claims the read limit (120/60 s) on write and webhook operations; it points to `01-conventions.md` §7.
- `04-kafka.md` §4 resend table names `CREATE_QUOTE` explicitly (was "Quote").
- README §2 and §8.1 referenced a `.github/pull_request_template.md` that never existed; removed the references (TW-M02 evidence is the PR reviews themselves).

### Breaking changes
- CP deployed base URL host renamed `cp-gateway.<squad>.roomscanner.local` → `cp-api.<squad>.roomscanner.local` (paths unchanged). Nothing is deployed yet; PP must use the new host in its CP client config.

### Clarified
- `ESCROW` is an optional Ultimo flow (M1 bonus) that replaces `DIRECT` only for the bookings that use it; both stay documented pending lecturer confirmation (D-07, `PaymentMode`).
- `pms/PMS-cross-ecosystem-draft.md`: new §5 lists where the separate PMS contract touches this CP–PP contract, including the conflict with the lecturer's "all four teams connect" answer.

No operation, path, topic or field was removed or renamed (only the CP deployed host, see Breaking changes). `EVENT_DELETED` was already in the CP-04 markdown; the schema now accepts it. Needs one reviewer from each team before merge.

## [Unreleased] - 2026-11-22 (unsigned Milestone 1 draft corrections)

### Corrected
- Bound Kafka message types, producers, paired reply topics, request metadata and response success/error payloads in generated schemas. Enforced mode-specific payment fields and favorite-event fields.
- Separated the business-flow `traceId` / `X-Trace-Id` from one logical request's `correlationId`; added explicit stable write `idempotencyKey`. Defined overall retry budgets (12/20/45 seconds), durable write replay and safe timeout reconciliation; corrected successful results to `status: OK`.
- Defined quote ownership/one-time consumption, durable CP-order and gateway-payment uniqueness, creation-time Premium checks, and a durable terminal-rejection barrier before payer compensation. Added exact customer-order filtering to the existing booking-list operation.
- Specified one squad-owned Stripe Connect sandbox platform with separate service credentials, payment metadata/ownership verification, webhook responsibilities, and independent transfer-reversal versus customer-refund references and outcomes.
- Preserved the custom JSON token endpoint and represented it as HTTP bearer authentication with explicit `x-required-scopes`, replacing the incompatible OAuth2 declaration.
- Updated JSON examples and regenerated OpenAPI/AsyncAPI files. Added repeatable validation and malformed-payload regression checks.

These are pre-sign-off corrections to the v1.0.0 **draft**, including new required envelope fields. Existing operation paths/topics are retained; both teams must review the revised baseline before adoption. No sign-off, country selection or PMS agreement is asserted by this change.

## [1.0.0] - 2026-11-20 (Milestone 1 baseline)

### Added
- **CP Contract Offer Review & Sign-Off**: Modularized `customer-portal/` into `CP-01-rating-statistics.md`, `CP-02-customer-membership.md`, `CP-03-orders-and-booking-events.md`, and `CP-04-regional-event-favorites.md` (with `CP-services-required-by-PP.md` as index); documented **CP Modular Monolith (`BE-M01`–`BE-M08`) vs. PP Microservices (`BE-U01`–`BE-U09`)** across `common/`, `provider-portal/PP-01`–`PP-06`, and `tools/generate_specs.py`; regenerated OpenAPI/AsyncAPI specs in `specs/`; updated `common/03-agreed-decisions.md` (`D-01`–`D-17`) to `Agreed` and confirmed CP redundant rating service in `common/04-kafka.md` §5.
- Common conventions: base URLs, partner client-credentials authentication and scopes, webhook HMAC signatures, error model, cursor pagination, rate limits, timeouts and versioning.
- Shared types: enumerations and objects (Money in minor units, ProviderSearchResult, RoomSummary/RoomDetail, PriceBreakdown, BookingSummary, payment status objects).
- Agreed decisions D-01 to D-17, covering SRS conflicts, business rules and SRS errata.
- Kafka integration: request and response envelopes, error envelope, topic catalogue, correlation, resend policy, redundancy and ACLs.
- Operations provided by PP (PP-OP-01 to PP-OP-13): search, catalogue, quote, booking lifecycle, status events, payment flows and event suggestions, each with field tables, examples and error tables.
- Operations provided by CP (CP-OP-01 to CP-OP-05), drafted by PP for CP approval.
- Machine-readable specification: OpenAPI 3.0.3 for both partner REST APIs and AsyncAPI 3.0.0 for the Kafka integration, generated by `tools/generate_specs.py`. All examples validated against their schemas.
- Kafka example for every message type (markdown and AsyncAPI), and a statement that the Kafka contract is independent of the partner's modular-monolith or microservice architecture.
- Requirement coverage matrix and sign-off table in `README.md`.
- Pull request template with one reviewer per team.
- Draft of the shared PMS cross-ecosystem contract.

### Changed (pre-release review)
- Example identifiers normalised to UUID v4, matching the identifier convention.
- Example JSON split into separate, valid request and response blocks.
- Status markers in decisions and drafts changed to text labels (Proposed, Agreed, Lecturer confirmation).

| Pull request | Author | Reviewers (PP / CP) |
|---|---|---|
| `#[PR]` | `[NAME]` | `[PP REVIEWER]` / `[CP REVIEWER]` |

## [0.1.0] - 2026-11-17
- Initial skeleton and operation index.
