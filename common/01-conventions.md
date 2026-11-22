# 01: Common Conventions

These rules apply to **every** operation in this contract unless an operation says otherwise.

## 1. Base URLs

Partner-facing APIs are kept separate from frontend-facing APIs (such as CP's `/api/v1/customer` end-user JWE endpoints) under a `/api/v1/partner` prefix. Each subsystem can then apply partner-only authentication, scopes, IP allowlists and rate limits (`INT-M03`).

| Subsystem | Environment | Base URL |
|---|---|---|
| PP | Local / Simplex | `http://localhost:8080/api/v1/partner` |
| PP | Deployed (Microservices via PP API Gateway + Service Discovery, Machine 4) | `https://pp-gateway.<squad>.roomscanner.local/api/v1/partner` |
| CP | Local / Simplex | `http://localhost:9080/api/v1/partner` |
| CP | Deployed (Modular Monolith `PartnerIntegrationModule`) | `https://cp-gateway.<squad>.roomscanner.local/api/v1/partner` |
| Kafka | Deployed (Machine 4) | `kafka.<squad>.roomscanner.local:9093` (SASL_SSL) |

**Subsystem architectures (Common Req. §5):**
- **Provider Portal (PP)** uses a **Microservices** architecture (`BE-U01`–`BE-U09`). Its API Gateway resolves partner routes through **service discovery** (`BE-U05`, `BE-U06`), keeping the redundant booking service (`PP-BOOK-U01`) transparent to CP.
- **Customer Portal (CP)** uses a **Modular Monolith** architecture (`BE-M01`–`BE-M08`). Partner authentication, rate limiting, and webhook verification are enforced in CP's Cross-Cutting Layer (`BE-S03`), and requests are handled by `PartnerIntegrationModule` and dispatched in-process via external service interfaces (`IRatingExternalService`, `IEventExternalService`, `IBookingExternalService`).

## 2. Data formats

| Concern | Rule | Example |
|---|---|---|
| Encoding | UTF-8 JSON, `Content-Type: application/json` | |
| Field naming | `camelCase` | `checkInDate` |
| Identifiers | UUID v4 strings (lower-case, hyphenated). Clients must treat them as opaque. Human-readable codes such as `bookingCode` are separate fields. | `"7c1f6d0e-3b7a-4a8e-9f0d-2a6b1c9e4f11"` |
| Stay dates | ISO-8601 calendar date, interpreted in the **branch's local time zone** | `"2027-04-10"` |
| Timestamps | ISO-8601 UTC with `Z` (optional `.SSS` milliseconds accepted by both subsystems) | `"2026-11-20T11:00:00Z"` or `"2027-02-15T10:00:00.000Z"` |
| Money | `Money` object, amount in **minor units** (integer), ISO-4217 currency. This avoids floating-point rounding. | `{ "amountMinor": 9000, "currency": "USD" }` = USD 90.00 |
| Country | ISO 3166-1 alpha-2 | `"VN"` |
| Email | `local-part@domain`, `< 255` characters, single `@`, domain has at least one `.`; only alphanumeric, `-`, and `_` in local and domain parts (PP-REG-M02, CP-REG-M02) | `"customer@example.com"` |
| Phone | E.164: `+` dialing code, then fewer than 13 digits (PP-REG-M03, CP-REG-M03) | `"+84901234567"` |
| Enums | `UPPER_SNAKE_CASE`, defined in `02-shared-types.md` | `"PENDING_APPROVAL"` |
| Nulls | Omit optional fields that have no value. Never send `""` to mean "none". | |

## 3. Standard headers

| Header | Direction | Required | Description |
|---|---|---|---|
| `Authorization: Bearer <partnerToken>` | request | Medium+ | Partner access token (§4) |
| `X-Request-Id` | request/response | yes | UUID per HTTP call. The server echoes it. |
| `X-Correlation-Id` (or `X-Correlation-ID`) | request/response | yes | UUID shared by every call in one business flow (e.g. quote → booking → events). HTTP header matching is case-insensitive. |
| `Idempotency-Key` | request | yes on `POST` that creates or cancels | UUID. A retry with the same key returns the **original** result without a second side effect. Kept for 24 h in Redis. |
| `X-RS-Signature` | webhook request | Medium+ | HMAC signature for PP → CP webhooks (§4.3) |
| `X-RateLimit-Limit` / `-Remaining` / `-Reset` | response | yes | Rate-limit status (§7) |
| `Retry-After` | response | on 429/503 | Seconds before the client should retry |

## 4. Partner authentication and authorization (INT-M03)

### 4.1 Partner access token (client-credentials)

Each subsystem issues tokens for its own partner API. The calling subsystem exchanges a **client ID and secret** (shared out-of-band, held in environment variables and never committed) for a short-lived token.

**`POST /api/v1/partner/auth/token`**

Request:

| Field | Type | Required | Notes |
|---|---|---|---|
| clientId | string | yes | `cp-subsystem` or `pp-subsystem` |
| clientSecret | string | yes | ≥ 32 random characters |
| scope | string[] | no | Defaults to every scope granted to the client |

Response `200`:

| Field | Type | Notes |
|---|---|---|
| accessToken | string | Signed JWT (JWS, RS256). Claims: `iss`, `sub`=clientId, `aud`, `scope`, `iat`, `exp` |
| tokenType | string | Always `"Bearer"` |
| expiresIn | integer | Seconds. Default `900` (15 min). |
| scope | string[] | Granted scopes |

**Request**

```json
{
  "clientId": "cp-subsystem",
  "clientSecret": "<from env>",
  "scope": [
    "search:read",
    "booking:write"
  ]
}
```

**Response `200`**

```json
{
  "accessToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6InBwLTIwMjYtMTEifQ...",
  "tokenType": "Bearer",
  "expiresIn": 900,
  "scope": [
    "search:read",
    "booking:write"
  ]
}
```

> Partner tokens identify a **system**, not an end user, so a signed JWS is enough. End-user identity tokens (JWE, CP/PP-LOGIN-M01) are **never** forwarded between subsystems. CP sends the `customerId` and a membership snapshot in the payload instead.

### 4.2 Scopes

| Scope | Granted to | Allows |
|---|---|---|
| `search:read` | CP | PP-OP-01…04 |
| `quote:write` | CP | PP-OP-05 |
| `booking:write` | CP | PP-OP-06, PP-OP-09 |
| `booking:read` | CP | PP-OP-07, PP-OP-08, PP-OP-10 |
| `event-suggestion:write` | CP | PP-OP-12 |
| `rating:read` | PP | CP-OP-01 |
| `membership:read` | PP | CP-OP-02 |
| `order:write` | PP | CP-OP-03 |
| `booking-event:write` | PP | CP-OP-04 |

Missing or invalid token → `401 PARTNER_UNAUTHENTICATED`. Valid token without the needed scope → `403 PARTNER_FORBIDDEN`. The gateway also applies an **IP allowlist** for the partner machines (defence in depth).

### 4.3 Webhook signature (PP → CP)

Each webhook call carries `X-RS-Signature: t=<unixSeconds>,v1=<hex>`, where `v1 = HMAC-SHA256(webhookSecret, t + "." + rawBody)`. CP rejects the request if the signature does not match, or if `|now − t| > 300 s` (replay protection).

### 4.4 Kafka

Each subsystem connects with its own **SASL/SCRAM-SHA-512** user (`pp-svc`, `cp-svc`) over TLS, and topic **ACLs** restrict who may produce or consume. See `04-kafka.md` §6.

## 5. Error format

Every non-2xx response, and every Kafka response whose `status` is `ERROR`, uses this body:

| Field | Type | Notes |
|---|---|---|
| error.code | string | Stable machine code (table below) |
| error.message | string | Human-readable message, safe to show to end users |
| error.details | object[] | Optional. Field-level problems: `{ "field": string, "issue": string }` |
| error.httpStatus | integer | Kafka responses only: the equivalent HTTP status (omitted on REST, where the status line carries it) |
| error.refundRequiredByPayer | boolean | PP-OP-06 only: `true` when CP must refund a payment it already captured (D-14) |
| error.requestId | string | Echo of `X-Request-Id` / Kafka `messageId` |
| error.timestamp | string | UTC timestamp |

```json
{
  "error": {
    "code": "BOOKING_QUANTITY_EXCEEDS_GUESTS",
    "message": "Requested room quantity (4) must not exceed adults + children (3).",
    "details": [{ "field": "quantity", "issue": "must be <= adults + children" }],
    "requestId": "0b6f8f4c-5a5e-4c55-8a39-31b2f1b9b0a7",
    "timestamp": "2026-11-20T11:00:00Z"
  }
}
```

### 5.1 Common error codes

| HTTP | Code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Malformed or missing fields |
| 401 | `PARTNER_UNAUTHENTICATED` | Missing, expired or invalid partner token or signature |
| 403 | `PARTNER_FORBIDDEN` | Token lacks the scope, or the resource is outside the agreed data scope |
| 404 | `RESOURCE_NOT_FOUND` | Unknown or archived ID (archived rooms and branches are **not** returned) |
| 409 | `IDEMPOTENCY_CONFLICT` | Same `Idempotency-Key` reused with a different body |
| 409 | `STATE_CONFLICT` | Operation not allowed in the current state |
| 422 | `BUSINESS_RULE_VIOLATION` | Generic business-rule failure (specific codes per operation) |
| 429 | `RATE_LIMITED` | Rate limit exceeded |
| 503 | `SERVICE_UNAVAILABLE` | Destination down or circuit open. Always **distinct** from 4xx business errors (CP/PP-LOGIN-U06). |
| 504 | `UPSTREAM_TIMEOUT` | A dependency (e.g. the payment gateway) timed out |

### 5.2 Customer Portal Frontend Error Translation (`/api/v1/partner/*` → `/api/v1/customer/*`)

On **partner-to-partner** calls (`/api/v1/partner/*` and Kafka topics), both subsystems use the partner error schema in Section 5 above. When Customer Portal proxies a partner operation to its own web frontend (`/api/v1/customer/*`), CP's `PartnerIntegrationModule` and Global Exception Handler translate the partner error into CP's 4-field customer-facing error convention (`roomscanner-customer-portal/docs/server/api_conventions_standards.md` §5):

| Partner Error Field (`/api/v1/partner/*` / Kafka) | CP Customer-Facing Field (`/api/v1/customer/*`) | Mapping Rule |
|---|---|---|
| `error.code` | `error.errorCode` | Mapped 1:1 (e.g. `BOOKING_QUANTITY_EXCEEDS_GUESTS`, `QUOTE_EXPIRED`, `CANCELLATION_WINDOW_CLOSED`, `SERVICE_UNAVAILABLE`). |
| `error.message` | `error.description` | Human-readable summary describing the error. |
| `error.details[0].issue` (or `error.message`) | `error.cause` | Specific violated rule or failure cause. |
| *(Derived by CP per endpoint)* | `error.validInputExample` | Single valid input value example (`string \| null`; `null` for `503 SERVICE_UNAVAILABLE`). |

## 6. Pagination (lazy loading, PP-SEARCH-M02 / CP-SEARCH-M02)

List operations use **cursor pagination**, so infinite scroll stays stable while new rooms are added.

| Query param | Type | Default | Notes |
|---|---|---|---|
| limit | integer | 10 | 1-50 |
| cursor | string | N/A | Opaque value from the previous `pageInfo.nextCursor` |

Response wrapper:

```json
{
  "items": [],
  "pageInfo": { "limit": 10, "nextCursor": "eyJzY29yZSI6MC44MSwiaWQiOiJiLTEyIn0", "hasMore": true }
}
```

## 7. Rate limits

These are applied per partner `clientId` at the subsystem edge/gateway with a Redis-backed sliding window (whether deployed as a Modular Monolith or Microservices).

| Scope | Threshold | Window | When exceeded |
|---|---|---|---|
| Read operations (`search:read`, `booking:read`, `rating:read`, `membership:read`) | 120 requests | 60 s | `429 RATE_LIMITED` + `Retry-After` |
| Write operations (`quote:write`, `booking:write`, `order:write`) | 30 requests | 60 s | `429 RATE_LIMITED` + `Retry-After` |
| Webhooks (`booking-event:write`) | 60 requests | 60 s | `429`. PP backs off as in PP-OP-11. |
| Token endpoint | 10 requests | 60 s | `429` |

## 8. Timeouts and client retries (REST)

| Call type | Client timeout | Retries |
|---|---|---|
| GET (safe) | 3 s | Up to 2, exponential backoff (200 ms, 800 ms) on 503/504/network errors |
| POST with `Idempotency-Key` | 10 s | Up to 2, **same key**, on 503/504/network errors |
| Never retried | N/A | 4xx responses other than 429 |

## 9. Versioning

- REST: the major version is in the path (`/api/v1`). Kafka: the major version is in the topic name (`.v1`).
- Additive changes (new optional fields) are non-breaking. Consumers **must ignore unknown fields**.
- Removing or renaming fields, or changing their meaning, needs a new major version (see README §5).
