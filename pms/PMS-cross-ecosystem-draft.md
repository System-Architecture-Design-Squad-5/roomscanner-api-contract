# Shared PMS: Cross-Ecosystem Contract (DRAFT)

> **Status:** Draft (pending agreement with the partner squad). Fields, identifiers, authorised operations and implementation ownership **must be agreed with the partner squad** (PP §2.9). Kept here so that both teams' diagrams show the same PMS boundary.

**SRS:** PP-PMS-S01, PP-PMS-S02 (Ultimo) · BE-U09 · DEP-U05 · Common Req. §1 (Booking.com/Agoda example) · CP exchange "Cross-ecosystem PMS"

## 1. Roles
| Party | Responsibility |
|---|---|
| Shared PMS (Machine 5, shared by both squads) | Stores the rooms published for cross-platform sharing and routes cross-platform booking requests to the owning squad |
| Our PP | Publishes its subscribed providers' shared rooms. Answers bookings for its own rooms. Enforces the provider's **USD 200/year PMS subscription** entitlement. |
| Our CP | Shows PMS rooms from partner squads in search (through our PP). Sends only the squad-agreed customer/order fields. |
| Partner squad | Same roles, mirrored |

## 2. Entitlement rule (PP-PMS-S01, S02)
- A provider's rooms are published to the PMS **only while** its subscription is `ACTIVE` (`validUntil` > now).
- When it expires, PP publishes `ROOM_UNPUBLISHED` for all of the provider's rooms, and further cross-platform operations are rejected with `403 PMS_SUBSCRIPTION_INACTIVE`.

## 3. Proposed Kafka topics (on the PMS broker)
| Topic | Producer → Consumer | Key | Purpose |
|---|---|---|---|
| `pms.room.published.v1` | squad PP → PMS | `roomId` | Room created/updated/unpublished (`ROOM_PUBLISHED`, `ROOM_UPDATED`, `ROOM_UNPUBLISHED`) |
| `pms.search.request.v1` / `pms.search.response.v1` | squad PP ↔ PMS | `correlationId` | Search shared rooms from other squads |
| `pms.booking.request.v1` / `pms.booking.response.v1` | PMS ↔ owning squad PP | `roomId` | Cross-platform booking create/cancel, routed by `ownerSquadId` |
| `pms.rating-summary.v1` | squad CP (via PP) → PMS | `providerId` | Rating summary attached to shared providers (customer ratings visible across platforms) |

## 4. Proposed shared room fields
`pmsRoomId` (globally unique: `<squadId>:<roomId>`), `ownerSquadId`, `providerName`, `branchName`, `category`, `roomType`, `amenities[]`, `location`, `pricePerNight`, `imageUrls[]`, `totalQuantity`, `ratingSummary`, `updatedAt`.
**Excluded:** provider account data, payment accounts, discount packages (squad-specific), and customer identity beyond `customerId`, `email` and `phone`.

## 5. Open questions for the partner squad
1. Who hosts and operates the PMS service and its database?
2. Currency and payment for cross-squad bookings: whose gateway collects?
3. How do we avoid ID collisions? Proposed: prefix with `squadId`.
4. Kafka credentials and ACLs for each squad on the PMS broker.
