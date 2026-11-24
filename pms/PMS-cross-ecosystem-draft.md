# Shared PMS: Cross-Ecosystem Contract (DRAFT)

> **Draft.** The two squads still need to agree on fields, IDs, allowed operations and who implements them (PP SRS §2.9). This outline records the proposed boundary; it is not the binding contract.

**SRS:** PP-PMS-S01, PP-PMS-S02 (Ultimo) · BE-U09 · DEP-U05 · Common Req. §1 (Booking.com/Agoda example) · CP exchange "Cross-ecosystem PMS"

## 1. Roles
| Party | Responsibility |
|---|---|
| Shared PMS (Machine 5) | Routes bookings to the owning squad. Keeping a copy of shared rooms is a proposal, not a storage decision. |
| Our PP | Publishes its subscribed providers' shared rooms. Answers bookings for its own rooms. Enforces the provider's **USD 200/year PMS subscription** entitlement. |
| Our CP | Connects directly to PMS for cross-platform search, booking requests and CP-owned review/rating exchange. Sends only the squad-agreed customer/order fields; PMS routes bookings to the authoritative owning PP. |
| Partner squad | Same roles, mirrored |

## 2. Entitlement rule (PP-PMS-S01, S02)
- A provider's rooms are published to the PMS **only while** its subscription is `ACTIVE` (`validUntil` > now).
- When it expires, PP publishes `ROOM_UNPUBLISHED` for all of the provider's rooms, and further cross-platform operations are rejected with `403 PMS_SUBSCRIPTION_INACTIVE`.

## 3. Proposed Kafka topics (on the PMS broker)
| Topic | Producer → Consumer | Key | Purpose |
|---|---|---|---|
| `pms.room.published.v1` | squad PP → PMS | `roomId` | Room created/updated/unpublished (`ROOM_PUBLISHED`, `ROOM_UPDATED`, `ROOM_UNPUBLISHED`) |
| `pms.search.request.v1` / `pms.search.response.v1` | squad CP ↔ PMS | `correlationId` | Search shared rooms from other squads |
| `pms.booking.request.v1` / `pms.booking.response.v1` | squad CP ↔ PMS ↔ owning squad PP | `roomId` | Cross-platform booking create/cancel, routed by `ownerSquadId`; replies return to the requesting CP |
| `pms.rating-summary.v1` | squad CP → PMS | `providerId` | Rating summary attached to shared providers; full cross-platform review retrieval remains to be specified |

## 4. Proposed shared room fields
`pmsRoomId` (globally unique: `<squadId>:<roomId>`), `ownerSquadId`, `providerName`, `branchName`, `category`, `roomType`, `amenities[]`, `location`, `pricePerNight`, `imageUrls[]`, `totalQuantity`, `ratingSummary`, `updatedAt`.
**Excluded:** provider account data, payment accounts, discount packages (squad-specific), and customer identity beyond `customerId`, `email` and `phone`.

## 5. Touch points with the CP–PP contract (this repository)
Each squad keeps a copy of the separate PMS agreement once it is signed (lecturer answer, 23 Nov 2026). These are the points where it meets the CP–PP contract:

| Touch point | CP–PP contract today | Open issue |
|---|---|---|
| CP access to PMS rooms | Direct CP ↔ PMS is proposed in Sections 1 and 3 | Matches the lecturer's **all four teams connect** clarification. Topic names, credentials, response routing and typed messages still need the other squad's agreement. |
| Search results containing partner-squad rooms | Local PP `ProviderSearchResult` has no `ownerSquadId` / `pmsRoomId` | CP merges local PP results and PMS results at its own boundary. PMS identifiers belong in the separate PMS contract; local PP endpoints do not accept foreign room IDs. |
| Bookings of partner-squad rooms | PP-OP-06 accepts only our own `roomId` | Not covered by PP-OP-05/06; to be defined in the PMS contract. |
| Entitlement | Provider USD 200/year PMS subscription (D-17) | PP-PMS-S02 wording ("premium membership") awaits lecturer confirmation. |

## 6. Open questions for the partner squad
1. Who hosts and operates the PMS service and its database?
2. Currency and payment for cross-squad bookings: whose gateway collects?
3. How do we avoid ID collisions? Proposed: prefix with `squadId`.
4. Kafka credentials and ACLs for each squad on the PMS broker.
5. What are the request, response and error fields, including for cross-platform review retrieval? Add JSON examples and agree on correlation, retries, idempotency and booking/payment outcomes.
6. Whether PMS stores its own room projection, and how updates, availability checks and unpublication remain consistent with the owning PP.
