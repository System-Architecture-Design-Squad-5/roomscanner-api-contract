# 04: Kafka Integration (Ultimo)

This file implements **inter-subsystem** Kafka communication: `INT-U01` (services exchanged through Kafka between CP and PP), `INT-U02` (a send channel and a receive channel per request, with correlation), `INT-U03` (resend on failure), and Cross-Ecosystem PMS over Kafka. *(Note: `BE-U02` inter-microservice Kafka applies inside **Provider Portal's Microservices** architecture; inside **Customer Portal's Modular Monolith**, modules communicate in-process via External Interfaces and External DTOs per `BE-M03`–`BE-M06`.)*

## 1. Message envelope

Every Kafka message value is a JSON envelope. The `payload` uses the REST operation's fields and types. For requests, merge path identifiers, query parameters and any JSON body into one object (for example, `CANCEL_BOOKING` adds the REST path's `bookingId` to `CancelBookingRequest`). Success payloads equal the REST response body; Kafka errors additionally require `error.httpStatus`.

| Field | Type | Required | Notes |
|---|---|---|---|
| messageId | string (UUID) | yes | Unique per message. A resend gets a **new** messageId. |
| correlationId | string (UUID) | yes | Set by the requester. Copied unchanged into the response, and kept the same on every resend. |
| traceId | string (UUID) | yes | Business-flow trace shared by related logical requests/events. Maps to `X-Trace-Id`; never a pending-request or deduplication key. |
| idempotencyKey | string (UUID) | CREATE_QUOTE / CREATE_BOOKING / CANCEL_BOOKING only | Stable write identity scoped to authenticated partner + operation; unchanged on resend or transport retry. Maps to `Idempotency-Key`. |
| causationId | string (UUID) | required on responses | messageId of the request attempt that caused this response; optional on requests/events |
| type | string | yes | Operation type, e.g. `CREATE_BOOKING`, `CREATE_BOOKING_RESULT` |
| schemaVersion | string | yes | `"1.0"` |
| source | string | yes | `"PP"` or `"CP"` (with the squad prefix for PMS) |
| replyTo | string | required on requests | Must be the operation's paired response topic (the receive channel); arbitrary destinations are rejected. Forbidden on responses/events. |
| attempt | integer | required on requests | 1 for the first send, then incremented on each resend; forbidden on responses/events. |
| deadline | string | required on requests | Absolute UTC deadline covering the whole logical request and all retries. Unchanged on resend; forbidden on responses/events. |
| timestamp | string | yes | UTC |
| status | string | required on responses | `OK` or `ERROR`; forbidden on requests/events |
| payload | object | yes | Request body, response body, or the error body (`01-conventions.md` §5) |

`correlationId` identifies **one logical service request**, not the whole business flow. A new operation gets a new correlation ID even when it shares a trace ID with earlier calls. One-way events use the documented aggregate/favorite correlation and do not create pending requests. The generated schemas bind each `type` to its exact payload, producer and response channel. Responses require `causationId` and `status`; `OK` carries that operation's success payload and `ERROR` carries the standard error including `httpStatus`. Event envelopes have neither response status nor request-only fields.

```json
{
  "messageId": "1d8e0c5a-6a11-4b0e-9a6f-0f2b3e4c5d6e",
  "correlationId": "a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "type": "CREATE_BOOKING",
  "schemaVersion": "1.0",
  "source": "CP",
  "replyTo": "rs.booking.response.v1",
  "attempt": 1,
  "deadline": "2026-12-01T03:00:45Z",
  "timestamp": "2026-12-01T03:00:00Z",
  "payload": {
    "...": "PP-OP-06 request body"
  },
  "idempotencyKey": "a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8"
}
```

### 1.1 Response envelope (success)

A response copies `correlationId`, sets `causationId` to the request's `messageId`, and carries `status`. It has no `replyTo`, `attempt` or `deadline`.

```json
{
  "messageId": "6b0e2a71-0000-4000-8000-00000000a102",
  "correlationId": "a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "causationId": "1d8e0c5a-6a11-4b0e-9a6f-0f2b3e4c5d6e",
  "type": "CREATE_BOOKING_RESULT",
  "schemaVersion": "1.0",
  "source": "PP",
  "timestamp": "2026-12-01T03:00:01Z",
  "status": "OK",
  "payload": {
    "bookingId": "8c9d0e1f-0000-4000-8000-000000000801",
    "status": "PENDING_APPROVAL"
  }
}
```

The `payload` above is abridged; a real `CREATE_BOOKING_RESULT` payload is the full PP-OP-06 `201` body.

### 1.2 Response envelope (business error)

The `payload` is the standard error body from `01-conventions.md` Section 5. The `httpStatus` field inside `error` carries the equivalent HTTP status, so the requester can map the error to its own REST response without a lookup table.

```json
{
  "messageId": "6b0e2a71-0000-4000-8000-00000000a103",
  "correlationId": "a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
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
| `rs.event.favorite.v1` | CP → PP | **CP** | `eventId` | `FAVORITE_ADDED`, `FAVORITE_REMOVED`, `EVENT_DATES_CHANGED`, `EVENT_DELETED` | CP-OP-05 |
| `rs.event.notification.v1` | PP → CP | **CP** (CP-EVENT-U01, "Customer Portal creates the topics") | `customerId` | `REGIONAL_EVENT_NOTIFICATION` | PP-OP-13 |
| `<topic>.dlq` | consumer → ops | topic creator | original key | original message + `errorReason` | all |

**Topic settings:** 6 partitions; replication factor 1 (one broker on Machine 4, DEP-U04); `retention.ms` = 7 days; DLQ retention 14 days; `cleanup.policy=delete`.

## 3. Request/response correlation (INT-U02)

1. The requester generates a fresh `correlationId` for this logical operation and retains the business `traceId`. It stores `pending:{source}:{type}:{correlationId}` in Redis with `{expectedResponseType, traceId, idempotencyKey?, attempt, deadline, originalPayload, waiterInstanceId}`. Expire the entry at the absolute deadline + 60 s (`EXPIREAT`, or an equivalent relative duration).
2. It produces to the request topic, with `replyTo` set to the paired response topic.
3. The responder validates the authenticated producer, message type and paired `replyTo`, then returns the **same** `correlationId` and `traceId`. `causationId` identifies the transport attempt that caused this response.
4. The requester's **dedicated response consumer** resolves the expected request type and looks up `pending:{source}:{type}:{correlationId}`. It verifies response type, producer and trace before applying it:
   - found and still waiting → persist the result in the shared pending record and notify `waiterInstanceId`. Any reply consumer may receive the response, so the owning HTTP instance must also be able to read that stored result if a notification is missed. Delete the key after the waiter consumes the result, or let its TTL expire.
   - not found (late duplicate) → log it and ignore it.
5. A successful business result returns `status: OK`. A business rejection, including a validation error, returns `status: ERROR`. Infrastructure failures can cause a timeout. Late results are retained/reconciled by business identity; an expired HTTP waiter does not undo a committed booking.

## 4. Resend policy (INT-U03)

| Message type | Timeout per attempt | Max attempts | Backoff between attempts | Overall budget |
|---|---|---|---|---|
| Search (`SEARCH_PROVIDERS`, `GET_BRANCH`, `GET_ROOM`, `LIST_ROOMS`) | 3 s | 3 | 0.5 s, 1 s | 12 s |
| `CREATE_QUOTE`, `CREATE_BOOKING`, `CANCEL_BOOKING` | 10 s | 3 | 2 s, 4 s | 45 s |
| `GET_BOOKING`, `LIST_BOOKINGS`, `GET_ELIGIBILITY` | 3 s | 3 | 0.5 s, 1 s | 12 s |
| `GET_RATING_STATISTICS` (PP-RATING-U02) | 5 s | 3 | 1 s, 2 s | 20 s |
| `GET_MEMBERSHIP` | 3 s | 3 | 0.5 s, 1 s | 12 s |

- A resend keeps the **same `correlationId`**, gets a **new `messageId`**, and increments `attempt`.
- **Idempotent responders:** The responder caches the business outcome under `processed:{source}:{type}:{correlationId}` for 24 h. A duplicate gets that outcome in a fresh response envelope: new `messageId` and `timestamp`, `causationId` set to the current attempt's `messageId`, and the request's `correlationId` and `traceId`. For errors, `error.requestId` also identifies the current attempt. Do not replay an old transport envelope. Write outcomes are additionally replayed by authenticated partner + operation + `idempotencyKey`; changed input returns `IDEMPOTENCY_CONFLICT`. Durable quote/order/payment uniqueness and terminal rejections survive Redis expiry (PP-03).
- After the last attempt fails, the requester returns `503 SERVICE_UNAVAILABLE` to its own frontend (a controlled failure; on CP's `/api/v1/customer/*` endpoints this is translated into CP's 4-field `"error"` payload with `errorCode: "SERVICE_UNAVAILABLE"` and `validInputExample: null`, see `01-conventions.md` §5.2). For rating statistics, PP shows the last cached statistics marked "stale" if it still holds them, otherwise "Rating temporarily unavailable" (D-11).
- A consumer that cannot process a message after 3 local retries (e.g. malformed JSON) sends it to `<topic>.dlq` and commits the offset, so the partition is not blocked.

## 5. Redundancy and delivery guarantees

- **Delivery:** at-least-once. Producers use `acks=all` and `enable.idempotence=true`. Consumers commit offsets **after** processing. Responders are idempotent (§4).
- **PP booking redundancy (PP-BOOK-U01):** Both PP booking-service instances (Machine 1 and Machine 2) join the consumer group `pp-booking-service`. If the primary fails, Kafka rebalances its partitions to the redundant instance, which continues from the last committed offset. CP needs no change. REST traffic from the PP frontend fails over through the API Gateway + service discovery (+ circuit breaker) in the same way.
- **CP rating redundancy (CustomerPortalSRS §3):** CP runs a second instance of the CP modular monolith (same single deployable, all modules). In both instances `PartnerIntegrationModule`'s consumer joins group `cp-rating-service` on `rs.rating-stats.request.v1`. If one instance fails, Kafka rebalances its partitions to the other, so on-demand rating statistics continue to be served. CP stays a modular monolith; this is horizontal scaling of the one deployable, not a separate rating microservice.
- **Ordering:** guaranteed per key. All events for one `bookingId` arrive in order.
- **Partner architecture independence (PP-SEARCH-U02, PP-ROOM-U02, PP-RATING-U01, CP-RATING-U01):** The contract depends only on topic names, the envelope and the consumer-group names in Section 6. CP is a **modular monolith** (Medium backend): every CP producer and consumer group (for example `cp-search-reply`) runs inside the monolith process, in `PartnerIntegrationModule`. The contract would not change if a partner were deployed as microservices instead, as the SRS requires. A partition is assigned to one member of a group at a time; at-least-once redelivery remains possible and requires deduplication. Neither side needs to know how the other is deployed.

## 6. Security and ACLs

| Principal | Produce | Consume (consumer groups) |
|---|---|---|
| `pp-svc` | `rs.search.response.v1`, `rs.booking.response.v1`, `rs.booking.events.v1`, `rs.rating-stats.request.v1`, `rs.membership.request.v1`, `rs.event.notification.v1`, PP DLQs | `rs.search.request.v1` (`pp-search-service`), `rs.booking.request.v1` (`pp-booking-service`), `rs.rating-stats.response.v1` (`pp-rating-reply`), `rs.membership.response.v1` (`pp-membership-reply`), `rs.event.favorite.v1` (`pp-event-service`) |
| `cp-svc` | `rs.search.request.v1`, `rs.booking.request.v1`, `rs.rating-stats.response.v1`, `rs.membership.response.v1`, `rs.event.favorite.v1`, CP DLQs | `rs.search.response.v1` (`cp-search-reply`), `rs.booking.response.v1` (`cp-booking-reply`), `rs.booking.events.v1` (`cp-booking-events`), `rs.rating-stats.request.v1` (`cp-rating-service`), `rs.membership.request.v1` (`cp-membership-service`), `rs.event.notification.v1` (`cp-event-notification-consumer`, the **dedicated consumer** required by CP-EVENT-U02) |

- Listener: `SASL_SSL` with SCRAM-SHA-512. No anonymous access. Topic auto-creation is **disabled**, so topics exist only if their creator team made them.
- Message payloads contain no passwords, tokens or card data.
