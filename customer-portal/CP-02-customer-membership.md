# CP-02: Customer Membership (provided by CP)

**Owner:** Customer Portal · **Consumer:** Provider Portal · **Scope:** `membership:read`
**SRS:** PP-DISCOUNT-S02 · CP-SUB-S01, S02 · **Decisions:** D-06

Customer Portal is the authoritative owner of customer accounts and \$100/year Premium subscriptions. Within CP's **Modular Monolith**, `PartnerIntegrationModule` calls `EventModule` via `IEventExternalService` (`CustomerMembershipExternalDto`).

---

## CP-OP-02 GetCustomerMembership

| Binding | Value |
|---|---|
| REST | `GET {CP}/api/v1/partner/customers/{customerId}/membership` |
| Kafka (Ultimo) | PP → `rs.membership.request.v1` (`type=GET_MEMBERSHIP`, key `customerId`) · CP → `rs.membership.response.v1` (`type=GET_MEMBERSHIP_RESULT`, same `correlationId`) |

### Request

| Field | In | Type | Required | Notes |
|---|---|---|---|---|
| `customerId` | path / payload | string (uuid) | yes | CP application user ID |

**Request (REST)**

`GET {CP}/api/v1/partner/customers/7d1e2f30-0000-4000-8000-000000000901/membership`

**Request (Kafka payload, `type=GET_MEMBERSHIP`)**

```json
{ "customerId": "7d1e2f30-0000-4000-8000-000000000901" }
```

### Response `200`

| Field | Type | Notes |
|---|---|---|
| `customerId` | string | |
| `tier` | MembershipTier | `STANDARD` or `PREMIUM` |
| `status` | MembershipStatus | `ACTIVE`, `EXPIRED`, or `NONE` |
| `validFrom` / `validUntil` | string | UTC. Present for `PREMIUM` (active or expired). |

**Response (REST `200`)**

```json
{
  "customerId": "7d1e2f30-0000-4000-8000-000000000901",
  "tier": "PREMIUM",
  "status": "ACTIVE",
  "validFrom": "2026-08-01T00:00:00Z",
  "validUntil": "2027-08-01T00:00:00Z"
}
```

**Response (Kafka envelope, Ultimo `type=GET_MEMBERSHIP_RESULT`)**

```json
{
  "messageId": "7d1e2f30-0000-4000-8000-000000000909",
  "correlationId": "0c4a7d22-0000-4000-8000-00000000c0bb",
  "traceId": "7ace0000-0000-4000-8000-000000000001",
  "causationId": "0c4a7d22-0000-4000-8000-00000000c002",
  "type": "GET_MEMBERSHIP_RESULT",
  "schemaVersion": "1.0",
  "source": "CP",
  "timestamp": "2026-12-01T04:00:01Z",
  "status": "OK",
  "payload": {
    "customerId": "7d1e2f30-0000-4000-8000-000000000901",
    "tier": "PREMIUM",
    "status": "ACTIVE",
    "validFrom": "2026-08-01T00:00:00Z",
    "validUntil": "2027-08-01T00:00:00Z"
  }
}
```

### Shard Routing (`CP-LOGIN-U03`, `CP-REG-U03`)
CP routes customer membership lookups directly to the customer's account shard (`countryOfResidence` shard key via Redis mapping) without scatter-gather scans.

### Errors
- `400 VALIDATION_ERROR`: `customerId` is not a UUID.
- `404 RESOURCE_NOT_FOUND`: unknown `customerId`.
- `503 SERVICE_UNAVAILABLE`: shard or Redis routing unavailable. PP fails closed: no Premium discount is applied without verification (`D-06`).
- `401 PARTNER_UNAUTHENTICATED` / `403 PARTNER_FORBIDDEN` / `429 RATE_LIMITED`: standard partner errors, see `common/01-conventions.md` (read limit: 120 requests per 60 s).

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Customer 7d1e2f30-0000-4000-8000-000000000999 was not found.",
    "requestId": "0c4a7d22-0000-4000-8000-00000000c003",
    "timestamp": "2026-12-01T04:00:02Z"
  }
}
```
