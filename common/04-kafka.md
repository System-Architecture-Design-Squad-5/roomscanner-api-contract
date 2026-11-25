# 04: Kafka Integration (Ultimo)

These are the Kafka rules between CP and PP: paired topics, correlation and retries (`INT-U01` to `INT-U03`). The [PMS draft](../pms/PMS-cross-ecosystem-draft.md) proposes separate cross-squad rules pending partner agreement. Inside PP, `BE-U02` applies to microservice messaging. CP modules call each other in-process through external interfaces and DTOs (`BE-M03` to `BE-M06`).

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

- Use a fresh `correlationId` for each logical request. Related requests can share a `traceId`.
- The generated schemas tie each `type` to its payload, producer and, for requests, reply topic. A reply includes `causationId` and `status`: `OK` carries the result; `ERROR` carries the standard error with `httpStatus`.
- One-way events use the operation's documented aggregate or favorite ID for correlation. They have no pending request, request-only fields or response status.

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

1. Before sending, the requester stores `pending:{source}:{type}:{correlationId}` in Redis. Keep `expectedResponseType`, `traceId`, optional `idempotencyKey`, `attempt`, `deadline`, `originalPayload` and `waiterInstanceId`. Expire the entry 60 s after the absolute deadline.
2. It produces to the request topic, with `replyTo` set to the paired response topic.
3. The responder validates the authenticated producer, message type and paired `replyTo`, then returns the **same** `correlationId` and `traceId`. `causationId` identifies the transport attempt that caused this response.
4. The requester's **dedicated response consumer** resolves the expected request type and looks up `pending:{source}:{type}:{correlationId}`. It verifies response type, producer and trace before applying it:
   - found and still waiting -> handle retryable errors under §4 without completing the call. For a final result, persist it in the shared pending record and notify `waiterInstanceId`. Any reply consumer may receive the response, so the owning HTTP instance must also be able to read that stored result if a notification is missed. Delete the key after the waiter consumes the result, or let its TTL expire.
   - not found (late duplicate) -> log it and ignore it.
5. A successful business result returns `status: OK`. A business rejection, including a validation error, returns `status: ERROR`. Infrastructure failures can cause a timeout. Late results are retained/reconciled by business identity; an expired HTTP waiter does not undo a committed booking.

## 4. Resend policy (INT-U03)

| Message type | Timeout per attempt | Max attempts | Backoff between attempts | Overall budget |
|---|---|---|---|---|
| Search (`SEARCH_PROVIDERS`, `GET_BRANCH`, `GET_ROOM`, `LIST_ROOMS`) | 3 s | 3 | 0.5 s, 1 s | 12 s |
| `CREATE_QUOTE`, `CREATE_BOOKING`, `CANCEL_BOOKING` | 10 s | 3 | 2 s, 4 s | 45 s |
| `GET_BOOKING`, `LIST_BOOKINGS`, `GET_ELIGIBILITY` | 3 s | 3 | 0.5 s, 1 s | 12 s |
| `GET_RATING_STATISTICS` (PP-RATING-U02) | 5 s | 3 | 1 s, 2 s | 20 s |
| `GET_MEMBERSHIP` | 3 s | 3 | 0.5 s, 1 s | 12 s |

**When to resend**

- Resend after a publish failure, an attempt timeout or a transient `ERROR` reply (`error.httpStatus` is `503` or `504`). A success or a non-retryable error, such as invalid input or a business rejection, ends the request.
- Count the first send toward the attempt limit. Use the backoff above and stop when the attempt limit or the original deadline is reached. Keep the same `correlationId`, `traceId`, payload, `deadline` and `idempotencyKey` (for writes). Use a new `messageId` and increment `attempt`.
- A retryable reply does not complete the call. Use `causationId` to match it to the request attempt. 
    - A duplicate or a reply to an older attempt must not schedule another resend. 
    - A valid final reply to any sent attempt can complete a request that is still waiting within its deadline.
- When retries run out, return `503 SERVICE_UNAVAILABLE` to the calling portal's frontend. CP maps it to `errorCode: "SERVICE_UNAVAILABLE"` and `validInputExample: null` (see [conventions §5.2](01-conventions.md#5-error-format)). For rating statistics, PP shows cached data marked stale, or “Rating temporarily unavailable” if none is cached (D-11).

**What to cache**

- Cache only final business outcomes (success or terminal rejection) for 24 h under `processed:{source}:{type}:{correlationId}`. 
    - Do not cache a transient error or timeout as a final outcome. 
    - On replay, use a new response `messageId` and `timestamp`, copy the request's `correlationId` and `traceId`, and set `causationId`. For errors, set `error.requestId` to the current attempt's `messageId`.
- For writes, check the durable record keyed by authenticated partner + operation + `idempotencyKey` before retrying the work. Replay a final outcome, if the write is still in flight or its outcome is uncertain, do not start another write or authorize compensation. Changed input returns `IDEMPOTENCY_CONFLICT`. [Quote, order and payment uniqueness and terminal rejections](../provider-portal/PP-03-bookings.md#pp-op-06-createbooking) survive Redis expiry.
- For a D-14 rejection, read mutable refund status from the durable record on replay. Do not replay a cached refund status.

**Example: CP recovers during a rating request.** PP sends `GET_RATING_STATISTICS`. CP's review shard is down, so CP replies with `ERROR` and `error.httpStatus: 503` without caching it as final. PP waits 1 s and resends with the same correlation ID, a new message ID and `attempt: 2`. The shard has recovered, so CP queries it again and replies `OK`. PP completes the request.

**Consumer retries** are separate from these requester resends. A consumer that cannot process a message after 3 local retries (e.g. malformed JSON) sends it to `<topic>.dlq` and commits the offset, so the partition is not blocked.

## 5. Redundancy and delivery guarantees

- **Delivery:** at-least-once. Producers use `acks=all` and `enable.idempotence=true`. Consumers commit offsets **after** processing. Responders are idempotent (§4).
- **PP booking failover (`PP-BOOK-U01`):** The instances on Machines 1 and 2 share the booking store and join `pp-booking-service`. If one fails, Kafka moves its partitions to the other, which resumes from the last committed offset. CP keeps the same Kafka entry point. For PP's own frontend, the gateway routes through service discovery and the circuit breaker.
- **CP rating failover (CP SRS §3):** `PartnerIntegrationModule` joins `cp-rating-service` on `rs.rating-stats.request.v1` in both instances of the monolith. If one fails, Kafka moves its partitions to the other. CP does not deploy a separate rating service.
- **Ordering:** guaranteed per key. All events for one `bookingId` arrive in order.
- **Backend independence (`PP-SEARCH-U02`, `PP-ROOM-U02`, `PP-RATING-U01`, `CP-RATING-U01`):** CP runs its Kafka producers and consumers in `PartnerIntegrationModule`. A microservice deployment could use the same topics, envelopes and groups in §6 without a contract change.

## 6. Security and ACLs

| Principal | Produce | Consume (consumer groups) |
|---|---|---|
| `pp-svc` | `rs.search.response.v1`, `rs.booking.response.v1`, `rs.booking.events.v1`, `rs.rating-stats.request.v1`, `rs.membership.request.v1`, `rs.event.notification.v1`, PP DLQs | `rs.search.request.v1` (`pp-search-service`), `rs.booking.request.v1` (`pp-booking-service`), `rs.rating-stats.response.v1` (`pp-rating-reply`), `rs.membership.response.v1` (`pp-membership-reply`), `rs.event.favorite.v1` (`pp-event-service`) |
| `cp-svc` | `rs.search.request.v1`, `rs.booking.request.v1`, `rs.rating-stats.response.v1`, `rs.membership.response.v1`, `rs.event.favorite.v1`, CP DLQs | `rs.search.response.v1` (`cp-search-reply`), `rs.booking.response.v1` (`cp-booking-reply`), `rs.booking.events.v1` (`cp-booking-events`), `rs.rating-stats.request.v1` (`cp-rating-service`), `rs.membership.request.v1` (`cp-membership-service`), `rs.event.notification.v1` (`cp-event-notification-consumer`, the **dedicated consumer** required by CP-EVENT-U02) |

- Listener: `SASL_SSL` with SCRAM-SHA-512. No anonymous access. Topic auto-creation is **disabled**, so topics exist only if their creator team made them.
- Message payloads contain no passwords, tokens or card data.
