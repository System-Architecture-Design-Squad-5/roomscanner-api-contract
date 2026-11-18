# 04: Kafka Integration (Ultimo)

This file implements INT-U01 (services exchanged through Kafka), INT-U02 (a send channel and a receive channel per request, with correlation), INT-U03 (resend on failure), BE-U02 (broker-based communication) and BE-U09 (PMS through Kafka).

## 1. Message envelope

Every Kafka message value is a JSON envelope. The `payload` is exactly the REST request or response body of the operation.

| Field | Type | Required | Notes |
|---|---|---|---|
| messageId | string (UUID) | yes | Unique per message. A resend gets a **new** messageId. |
| correlationId | string (UUID) | yes | Set by the requester. Copied unchanged into the response, and kept the same on every resend. |
| causationId | string (UUID) | no | messageId of the message that caused this one |
| type | string | yes | Operation type, e.g. `CREATE_BOOKING`, `CREATE_BOOKING_RESULT` |
| schemaVersion | string | yes | `"1.0"` |
| source | string | yes | `"PP"` or `"CP"` (with the squad prefix for PMS) |
| replyTo | string | requests only | Topic for the response (the receive channel) |
| attempt | integer | requests only | 1 for the first send, then incremented on each resend |
| deadline | string | requests only | UTC. The responder may skip requests that are already past this time. |
| timestamp | string | yes | UTC |
| status | string | responses only | `OK` or `ERROR` |
| payload | object | yes | Request body, response body, or the error body (`01-conventions.md` §5) |

```json
{
  "messageId": "1d8e0c5a-6a11-4b0e-9a6f-0f2b3e4c5d6e",
  "correlationId": "a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8",
  "type": "CREATE_BOOKING",
  "schemaVersion": "1.0",
  "source": "CP",
  "replyTo": "rs.booking.response.v1",
  "attempt": 1,
  "deadline": "2026-12-01T03:00:10Z",
  "timestamp": "2026-12-01T03:00:00Z",
  "payload": { "...": "PP-OP-06 request body" }
}
```

### 1.1 Response envelope (success)

A response copies `correlationId`, sets `causationId` to the request's `messageId`, and carries `status`. It has no `replyTo`, `attempt` or `deadline`.

```json
{
  "messageId": "6b0e2a71-0000-4000-8000-00000000a102",
  "correlationId": "a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8",
  "causationId": "1d8e0c5a-6a11-4b0e-9a6f-0f2b3e4c5d6e",
  "type": "CREATE_BOOKING_RESULT",
  "schemaVersion": "1.0",
  "source": "PP",
  "timestamp": "2026-12-01T03:00:01Z",
  "status": "OK",
  "payload": { "bookingId": "8c9d0e1f-0000-4000-8000-000000000801", "status": "PENDING_APPROVAL" }
}
```

The `payload` above is abridged; a real `CREATE_BOOKING_RESULT` payload is the full PP-OP-06 `201` body.

### 1.2 Response envelope (business error)

The `payload` is the standard error body from `01-conventions.md` Section 5. The `httpStatus` field inside `error` carries the equivalent HTTP status, so the requester can map the error to its own REST response without a lookup table.

```json
{
  "messageId": "6b0e2a71-0000-4000-8000-00000000a103",
  "correlationId": "a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8",
  "causationId": "1d8e0c5a-6a11-4b0e-9a6f-0f2b3e4c5d6e",
  "type": "CREATE_BOOKING_RESULT",
  "schemaVersion": "1.0",
  "source": "PP",
  "timestamp": "2026-12-01T03:00:01Z",
  "status": "ERROR",
  "payload": {
    "error": {
      "code": "QUOTE_EXPIRED",
      "httpStatus": 409,
      "message": "The price quote expired at 2026-12-01T02:59:00Z. Request a new quote.",
      "refundRequiredByPayer": true,
      "requestId": "1d8e0c5a-6a11-4b0e-9a6f-0f2b3e4c5d6e",
      "timestamp": "2026-12-01T03:00:01Z"
    }
  }
}
```

## 2. Topic catalogue

Naming: `rs.<domain>.<channel>.v<major>`. Each request topic is paired with a response topic (INT-U02).

| Topic | Producer → Consumer | Created by | Key (ordering) | Message types | Operations |
|---|---|---|---|---|---|
| `rs.search.request.v1` | CP → PP | PP | `correlationId` | `SEARCH_PROVIDERS`, `GET_BRANCH`, `LIST_ROOMS`, `GET_ROOM` | PP-OP-01…04 |
| `rs.search.response.v1` | PP → CP | PP | `correlationId` | `*_RESULT` | PP-OP-01…04 |
| `rs.booking.request.v1` | CP → PP | PP | `customerId` (create/list/quote) or `bookingId` | `CREATE_QUOTE`, `CREATE_BOOKING`, `GET_BOOKING`, `LIST_BOOKINGS`, `CANCEL_BOOKING`, `GET_ELIGIBILITY` | PP-OP-05…10 |
| `rs.booking.response.v1` | PP → CP | PP | same as the request | `*_RESULT` | PP-OP-05…10 |
| `rs.booking.events.v1` | PP → CP | PP | `bookingId` | `BOOKING_CONFIRMED`, `BOOKING_CANCELLED`, `BOOKING_COMPLETED`, `RETURN_PAYMENT_UPDATED`, `ESCROW_RELEASE_UPDATED` | PP-OP-11 |
| `rs.rating-stats.request.v1` | PP → CP | CP | `providerId` | `GET_RATING_STATISTICS` | CP-OP-01 |
| `rs.rating-stats.response.v1` | CP → PP | CP | `providerId` | `GET_RATING_STATISTICS_RESULT` | CP-OP-01 |
| `rs.membership.request.v1` | PP → CP | CP | `customerId` | `GET_MEMBERSHIP` | CP-OP-02 |
| `rs.membership.response.v1` | CP → PP | CP | `customerId` | `GET_MEMBERSHIP_RESULT` | CP-OP-02 |
| `rs.event.favorite.v1` | CP → PP | **CP** | `eventId` | `FAVORITE_ADDED`, `FAVORITE_REMOVED`, `EVENT_DATES_CHANGED` | CP-OP-05 |
| `rs.event.notification.v1` | PP → CP | **CP** (CP-EVENT-U01, "Customer Portal creates the topics") | `customerId` | `REGIONAL_EVENT_NOTIFICATION` | PP-OP-13 |
| `<topic>.dlq` | consumer → ops | topic creator | original key | original message + `errorReason` | all |

**Topic settings:** 6 partitions; replication factor 1 (one broker on Machine 4, DEP-U04); `retention.ms` = 7 days; DLQ retention 14 days; `cleanup.policy=delete`.

## 3. Request/response correlation (INT-U02)

1. The requester generates a `correlationId`. It stores `pending:{correlationId}` in Redis with `{type, attempt, deadline, originalPayload}`, TTL = deadline + 60 s.
2. It produces to the request topic, with `replyTo` set to the paired response topic.
3. The responder processes the request and produces to `replyTo` with the **same** `correlationId` and `status`.
4. The requester's **dedicated response consumer** looks up `pending:{correlationId}`:
   - found → complete the waiting call (the REST call from the frontend is answered, or the frontend is pushed via WebSocket) and delete the key.
   - not found (late duplicate) → log it and ignore it.
5. Every business result (including validation errors) comes back as a response with `status: ERROR`. Only infrastructure failures cause a timeout.

## 4. Resend policy (INT-U03)

| Message type | Response timeout | Max attempts | Backoff between attempts |
|---|---|---|---|
| Search (`SEARCH_PROVIDERS`, `GET_*`, `LIST_ROOMS`) | 3 s | 3 | 0.5 s, 1 s |
| Quote, `CREATE_BOOKING`, `CANCEL_BOOKING` | 10 s | 3 | 2 s, 4 s |
| `GET_BOOKING`, `LIST_BOOKINGS`, `GET_ELIGIBILITY` | 3 s | 3 | 0.5 s, 1 s |
| `GET_RATING_STATISTICS` (PP-RATING-U02) | 5 s | 3 | 1 s, 2 s |
| `GET_MEMBERSHIP` | 3 s | 3 | 0.5 s, 1 s |

- A resend keeps the **same `correlationId`**, gets a **new `messageId`**, and increments `attempt`.
- **Idempotent responders:** The responder stores `processed:{type}:{correlationId}` → response in Redis for 24 h. A duplicate request gets the **cached response** again, with no second booking and no second cancellation.
- After the last attempt fails, the requester returns `503 SERVICE_UNAVAILABLE` to its own frontend (a controlled failure, BE-U07). For rating statistics, PP shows the last cached statistics marked "stale", or "temporarily unavailable".
- A consumer that cannot process a message after 3 local retries (e.g. malformed JSON) sends it to `<topic>.dlq` and commits the offset, so the partition is not blocked.

## 5. Redundancy and delivery guarantees

- **Delivery:** at-least-once. Producers use `acks=all` and `enable.idempotence=true`. Consumers commit offsets **after** processing. Responders are idempotent (§4).
- **PP booking redundancy (PP-BOOK-U01):** Both PP booking-service instances (Machine 1 and Machine 2) join the consumer group `pp-booking-service`. If the primary fails, Kafka rebalances its partitions to the redundant instance, which continues from the last committed offset. CP needs no change. REST traffic from the PP frontend fails over through the API Gateway + service discovery (+ circuit breaker) in the same way.
- **Ordering:** guaranteed per key. All events for one `bookingId` arrive in order.
- **Partner architecture independence (PP-SEARCH-U02, PP-ROOM-U02, PP-RATING-U01, CP-RATING-U01):** The contract depends only on topic names, the envelope and the consumer-group names in Section 6. CP may consume and produce from a single modular-monolith process or from separate microservices; either way it uses the same groups (for example `cp-search-reply`), so Kafka delivers each response once per group. Neither side needs to know how the other is deployed.

## 6. Security and ACLs

| Principal | Produce | Consume (consumer groups) |
|---|---|---|
| `pp-svc` | `rs.search.response.v1`, `rs.booking.response.v1`, `rs.booking.events.v1`, `rs.rating-stats.request.v1`, `rs.membership.request.v1`, `rs.event.notification.v1`, PP DLQs | `rs.search.request.v1` (`pp-search-service`), `rs.booking.request.v1` (`pp-booking-service`), `rs.rating-stats.response.v1` (`pp-rating-reply`), `rs.membership.response.v1` (`pp-membership-reply`), `rs.event.favorite.v1` (`pp-event-service`) |
| `cp-svc` | `rs.search.request.v1`, `rs.booking.request.v1`, `rs.rating-stats.response.v1`, `rs.membership.response.v1`, `rs.event.favorite.v1`, CP DLQs | `rs.search.response.v1` (`cp-search-reply`), `rs.booking.response.v1` (`cp-booking-reply`), `rs.booking.events.v1` (`cp-booking-events`), `rs.rating-stats.request.v1` (`cp-rating-service`), `rs.membership.request.v1` (`cp-membership-service`), `rs.event.notification.v1` (`cp-event-notification-consumer`, the **dedicated consumer** required by CP-EVENT-U02) |

- Listener: `SASL_SSL` with SCRAM-SHA-512. No anonymous access. Topic auto-creation is **disabled**, so topics exist only if their creator team made them.
- Message payloads contain no passwords, tokens or card data.
