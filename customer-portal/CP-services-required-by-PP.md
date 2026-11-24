# CP Services Required by Provider Portal

> **Status:** Agreed (Reviewed & Confirmed by Customer Portal team; CP is the owner of these operations).

**Owner:** Customer Portal · **Consumer:** Provider Portal

Customer Portal implements these partner-facing services inside its **Modular Monolith** (`PartnerIntegrationModule` -> external service interfaces `IRatingExternalService`, `IEventExternalService`, `IBookingExternalService`).

---

## Operation Index

| File | Operation(s) | Scope / Transport | Summary |
|---|---|---|---|
| [CP-01-rating-statistics.md](./CP-01-rating-statistics.md) | `CP-OP-01 GetRatingStatistics` | `rating:read` · REST + Kafka | On-demand provider rating statistics from `providerId`-sharded review store (a second monolith instance joins consumer group `cp-rating-service` for redundancy). |
| [CP-02-customer-membership.md](./CP-02-customer-membership.md) | `CP-OP-02 GetCustomerMembership` | `membership:read` · REST + Kafka | Verifies active `PREMIUM` membership status from `countryOfResidence`-sharded customer accounts. |
| [CP-03-orders-and-booking-events.md](./CP-03-orders-and-booking-events.md) | `CP-OP-03 UpdateSimulatedOrder`, `CP-OP-04 ReceiveBookingEvent` | `order:write`, `booking-event:write` · REST + Webhook | Completes/cancels Simplex orders and receives `X-RS-Signature` verified booking status webhooks. |
| [CP-04-regional-event-favorites.md](./CP-04-regional-event-favorites.md) | `CP-OP-05 EventFavoriteChanged` | Kafka (`rs.event.favorite.v1`) | Publishes `FAVORITE_ADDED`, `FAVORITE_REMOVED`, `EVENT_DATES_CHANGED` and `EVENT_DELETED` events to trigger PP top-2 stay suggestions. |
