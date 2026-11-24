"""Generate the OpenAPI and AsyncAPI specifications for the RoomScanner squad API contract.

One schema dictionary feeds all three files so field names and types cannot drift.
Usage (from the repository root): python -m pip install -r tools/requirements-validation.txt
                                 python tools/generate_specs.py .
"""
import copy
from datetime import datetime, timedelta
import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(sys.argv[1])
VERSION = "1.0.0"


# ---------------------------------------------------------------- helpers
def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


def _t(typ, desc=None, **kw):
    d = {"type": typ}
    if desc:
        d["description"] = desc
    d.update(kw)
    return d


def s(desc=None, **kw):
    return _t("string", desc, **kw)


def i(desc=None, **kw):
    return _t("integer", desc, **kw)


def num(desc=None, **kw):
    return _t("number", desc, **kw)


def b(desc=None, **kw):
    return _t("boolean", desc, **kw)


def uuid(desc=None):
    return s(desc, format="uuid")


def date(desc=None):
    return s(desc, format="date")


def dt(desc=None):
    return s(desc, format="date-time")


def arr(items, desc=None, **kw):
    d = {"type": "array", "items": items}
    if desc:
        d["description"] = desc
    d.update(kw)
    return d


def obj(props, req=(), desc=None, **kw):
    d = {"type": "object"}
    if desc:
        d["description"] = desc
    d["properties"] = props
    if req:
        d["required"] = list(req)
    d.update(kw)
    return d


def enum(values, desc):
    return {"type": "string", "enum": values, "description": desc}


def described(schema_ref, desc):
    """Attach a description to a $ref (OpenAPI 3.0 ignores siblings of $ref, so wrap in allOf)."""
    return {"allOf": [schema_ref], "description": desc}


def absent(*names):
    """OpenAPI 3.0-compatible prohibition of context-inappropriate fields."""
    return {"not": {"anyOf": [{"required": [name]} for name in names]}}


TIME_HHMM = s("Local time, HH:mm", pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
COUNTRY = s("ISO 3166-1 alpha-2 country code", pattern=r"^[A-Z]{2}$")
PHONE = s("E.164: '+' and the international dialing code, followed by fewer than 13 digits (PP-REG-M03, CP-REG-M03)",
          pattern=r"^\+[1-9][0-9]{1,15}$")

# ---------------------------------------------------------------- schemas
S = {}
S["ProviderCategory"] = enum(["RESORT", "HOTEL", "MOTEL_HOSTEL", "HOMESTAY"], "Accommodation-provider category (PP-ROOM-S06, PP Section 2.3).")
S["RoomType"] = enum(["BUNK_BED", "SINGLE_TWIN_BED", "DOUBLE_BED"], "Room type (CP-SEARCH-S01).")
S["Amenity"] = enum(["FREE_WIFI", "KITCHEN", "WASHING_MACHINE", "PETS_ALLOWED", "PRIVATE_BATHROOM", "AIR_CONDITIONING", "DISABLED_FACILITIES"],
                    "Unified amenity/service list: union of PP-ROOM-S06 and CP-SEARCH-S02 (Decision D-02).")
S["MembershipTier"] = enum(["STANDARD", "PREMIUM"], "Customer membership tier. There is no other tier (PP Section 2.8).")
S["MembershipStatus"] = enum(["ACTIVE", "EXPIRED", "NONE"], "Customer membership status.")
S["BookingStatus"] = enum(["PENDING_APPROVAL", "CONFIRMED", "CANCELLED", "COMPLETED"],
                          "Authoritative booking status owned by PP. PENDING_APPROVAL has no automatic expiry (PP-BOOK-S02).")
S["CancelledBy"] = enum(["CUSTOMER", "RECEPTIONIST"], "Actor that cancelled the booking.")
S["PaymentMode"] = enum(["SIMULATED", "DIRECT", "ESCROW"], "SIMULATED = Simplex, DIRECT = Medium, ESCROW = optional Ultimo flow that replaces DIRECT for the bookings that use it (Decision D-07).")
S["PaymentGateway"] = enum(["NONE", "PAYPAL_SANDBOX", "STRIPE_SANDBOX"], "Payment gateway used for the booking (Decision D-07).")
S["PaymentState"] = enum(["SIMULATED_ISSUED", "CAPTURED", "CAPTURED_HELD"], "Payer-side payment state reported by CP in CreateBooking.")
S["ReturnPaymentStatus"] = enum(["NOT_REQUIRED", "PENDING", "SUCCEEDED", "FAILED"],
                                "Beneficiary-side status of the money returned to the customer (PP-MONEY-M03).")
S["EscrowReleaseStatus"] = enum(["HELD", "RELEASE_PENDING", "RELEASED", "RELEASE_FAILED", "REFUNDED"], "Escrow state (Ultimo, PP-MONEY-U01).")
S["DiscountType"] = enum(["PERCENTAGE", "FIXED_PER_NIGHT"], "PERCENTAGE: value is 1-100. FIXED_PER_NIGHT: value is minor units off each room-night.")
S["StarGroup"] = enum(["ONE_TO_TWO", "THREE", "FOUR_TO_FIVE"], "Star group that a preset feedback option belongs to (CP-RATING-M02).")
S["RatingSubcategory"] = enum(["SERVICE", "FRIENDLINESS", "ROOM"], "Rating subcategory (CP-RATING-M01).")
S["StatisticsScope"] = enum(["OVERALL", "SUBCATEGORIES", "PRESET_OPTIONS", "COMMENTS"], "Part of the rating statistics requested.")
S["SearchSort"] = enum(["RELEVANCE", "RATING_DESC", "PRICE_ASC"], "Sort order for provider search.")
S["MatchMode"] = enum(["ANY", "ALL"], "ANY = OR semantics (default, PP-SEARCH-M01). ALL = strict AND matching.")

S["Money"] = obj({
    "amountMinor": i("Amount in minor units (cents). Integer to avoid floating-point rounding.", minimum=0),
    "currency": s("ISO 4217 currency code. The squad uses USD.", pattern=r"^[A-Z]{3}$"),
}, ["amountMinor", "currency"], "Monetary amount.")

S["Location"] = obj({
    "addressLine": s("Public property address (branch), never a private account address"),
    "city": s("City inside the squad's sub-region (PP-ROOM-S01)"),
    "country": COUNTRY,
    "timeZone": s("IANA time zone, e.g. Asia/Ho_Chi_Minh"),
    "latitude": num(minimum=-90, maximum=90),
    "longitude": num(minimum=-180, maximum=180),
}, ["addressLine", "city", "country", "timeZone"], "Branch location.")

S["RatingSummary"] = obj({
    "overallAverage": num("Mean Overall score, 1.0-5.0, one decimal. Omitted when totalReviews is 0.", minimum=1, maximum=5),
    "totalReviews": i(minimum=0),
    "source": enum(["CP"], "Always CP. PP never computes ratings (PP-RATING-S01)."),
    "asOf": dt("Timestamp of the CP statistics this value came from"),
}, ["totalReviews", "source", "asOf"], "Rating summary sourced from CP statistics and cached by PP (Decision D-11).")

S["ProviderSearchResult"] = obj({
    "providerId": uuid(),
    "providerName": s("Company name of the accommodation provider"),
    "branchId": uuid(),
    "branchName": s("Property name shown to customers"),
    "category": ref("ProviderCategory"),
    "logoUrl": s("Resized provider logo (PP-PROFILE-M01)", format="uri"),
    "location": ref("Location"),
    "roomTypesOffered": arr(ref("RoomType"), "Room types with active listings"),
    "amenities": arr(ref("Amenity"), "Union of amenities across active rooms"),
    "availableRoomCount": i("Sum of available quantity for the requested dates", minimum=0),
    "lowestPricePerNight": ref("Money"),
    "ratingSummary": ref("RatingSummary"),
    "matchedFields": arr(s(), "Medium FTS only: fields that matched"),
    "relevanceScore": num("Medium FTS only: rank between 0 and 1", minimum=0, maximum=1),
}, ["providerId", "providerName", "branchId", "branchName", "category", "logoUrl", "location", "roomTypesOffered",
    "amenities", "availableRoomCount", "lowestPricePerNight", "ratingSummary"],
    "One branch (property at one address) of a provider. The unit of a search result (Decision D-04).")

S["PageInfo"] = obj({
    "limit": i(minimum=1, maximum=50),
    "nextCursor": s("Opaque cursor for the next page. Omitted when hasMore is false."),
    "hasMore": b(),
}, ["limit", "hasMore"], "Cursor pagination metadata (lazy loading, PP-SEARCH-M02).")

S["DiscountPolicySummary"] = obj({
    "discountPackageId": uuid(),
    "name": s(),
    "type": ref("DiscountType"),
    "value": i("Percentage (1-100) or minor units per night", minimum=1),
    "eligibleTier": described(ref("MembershipTier"), "Always PREMIUM"),
    "active": b("false once the discount program is cancelled"),
}, ["discountPackageId", "name", "type", "value", "eligibleTier", "active"], "Discount policy assigned to a room (PP-DISCOUNT-S01).")

S["RoomSummary"] = obj({
    "roomId": uuid(),
    "branchId": uuid(),
    "name": s(),
    "roomType": ref("RoomType"),
    "maxOccupancy": i("Guests per room", minimum=1),
    "totalQuantity": i(minimum=0),
    "availableQuantity": i("Available for the requested dates (Decision D-05)", minimum=0),
    "pricePerNight": ref("Money"),
    "premiumPricePerNight": described(ref("Money"), "Present when a discount policy is assigned. Display only; the binding price comes from CreatePriceQuote."),
    "amenities": arr(ref("Amenity")),
    "thumbnailUrl": s(format="uri"),
    "imageUrls": arr(s(format="uri"), "All room images (PP-ROOM-S05)"),
}, ["roomId", "branchId", "name", "roomType", "maxOccupancy", "totalQuantity", "availableQuantity", "pricePerNight",
    "amenities", "thumbnailUrl", "imageUrls"], "Room listing summary (PP-SEARCH-S03).")

S["RoomDetail"] = {"allOf": [ref("RoomSummary"), obj({
    "description": s(maxLength=2000),
    "sizeSqm": num(minimum=0),
    "bedCount": i(minimum=1),
    "discountPolicy": ref("DiscountPolicySummary"),
    "provider": ref("ProviderSearchResult"),
    "checkInTime": TIME_HHMM,
    "checkOutTime": TIME_HHMM,
}, ["description", "bedCount", "provider", "checkInTime", "checkOutTime"])], "description": "Full room details."}

S["AppliedDiscount"] = obj({
    "discountPackageId": uuid(),
    "name": s(),
    "type": ref("DiscountType"),
    "value": i(minimum=1),
    "amount": described(ref("Money"), "Total discount for the whole booking"),
}, ["discountPackageId", "name", "type", "value", "amount"], "Discount snapshot stored on a quote or booking.")

S["PriceBreakdown"] = obj({
    "nights": i(minimum=1),
    "quantity": i(minimum=1),
    "unitPricePerNight": ref("Money"),
    "subtotal": described(ref("Money"), "unitPricePerNight x nights x quantity"),
    "discount": ref("AppliedDiscount"),
    "total": described(ref("Money"), "subtotal - discount. The exact amount CP must charge."),
}, ["nights", "quantity", "unitPricePerNight", "subtotal", "total"], "Price calculated by PP (Decision D-06).")

S["CustomerSnapshot"] = obj({
    "customerId": uuid("CP application user ID"),
    "email": s(format="email"),
    "phone": PHONE,
    "countryOfResidence": COUNTRY,
}, ["customerId", "email", "phone", "countryOfResidence"],
    "Customer fields PP needs at booking time. Passport number and birthday are never shared (Decision D-16).")

S["MembershipSnapshot"] = obj({
    "tier": ref("MembershipTier"),
    "status": ref("MembershipStatus"),
    "validUntil": dt("Present when tier is PREMIUM"),
}, ["tier", "status"], "Membership snapshot sent by CP. PP re-verifies it with CP-OP-02 before applying a discount.")

S["PaymentInfo"] = obj({
    "mode": ref("PaymentMode"),
    "gateway": ref("PaymentGateway"),
    "orderId": uuid("CP order ID (payer side)"),
    "paymentReference": s("Required for DIRECT and ESCROW: PayPal capture ID or Stripe PaymentIntent ID", minLength=1),
    "chargeReference": s("ESCROW only: Stripe Charge ID", minLength=1),
    "state": ref("PaymentState"),
    "amount": described(ref("Money"), "Must equal the quote's priceBreakdown.total"),
    "paidAt": dt("Required for DIRECT and ESCROW"),
}, ["mode", "gateway", "orderId", "state", "amount"], "Payer-side payment information sent by CP with CreateBooking.")
S["PaymentInfo"]["oneOf"] = [
    {"properties": {"mode": {"enum": ["SIMULATED"]}, "gateway": {"enum": ["NONE"]},
                    "state": {"enum": ["SIMULATED_ISSUED"]}},
     **absent("paymentReference", "chargeReference", "paidAt")},
    {"properties": {"mode": {"enum": ["DIRECT"]}, "gateway": {"enum": ["PAYPAL_SANDBOX"]},
                    "state": {"enum": ["CAPTURED"]}},
     "required": ["paymentReference", "paidAt"], **absent("chargeReference")},
    {"properties": {"mode": {"enum": ["ESCROW"]}, "gateway": {"enum": ["STRIPE_SANDBOX"]},
                    "state": {"enum": ["CAPTURED_HELD"]}},
     "required": ["paymentReference", "chargeReference", "paidAt"]},
]

S["TransferReversalStatus"] = enum(["NOT_REQUIRED", "PENDING", "SUCCEEDED", "FAILED"],
    "Recovery of a previously released Stripe transfer; separate from the customer refund outcome.")

S["BookingPaymentStatus"] = obj({
    "mode": ref("PaymentMode"),
    "orderId": uuid("Original CP order ID; retained for reconciliation"),
    "originalPaymentReference": s("Preserved after cancellation (PP-MONEY-M03)", minLength=1),
    "escrowStatus": ref("EscrowReleaseStatus"),
    "releaseReference": s("Stripe Transfer ID once released (ESCROW)", minLength=1),
    "transferReversalStatus": ref("TransferReversalStatus"),
    "transferReversalReference": s("Stripe TransferReversal ID (trr_...), retained after a successful reversal", minLength=1),
    "transferReversalFailureCause": s("Failure to recover a released transfer; distinct from a refund failure", minLength=1),
    "returnPaymentStatus": ref("ReturnPaymentStatus"),
    "returnPaymentReference": s("PayPal payout batch ID or Stripe Refund ID. Separate from the original payment.", minLength=1),
    "failureCause": s("Gateway failure reason, when available"),
}, ["mode", "returnPaymentStatus"], "Beneficiary-side payment status of a booking.")
S["BookingPaymentStatus"]["allOf"] = [
    {"oneOf": [
        {"properties": {"mode": {"enum": ["SIMULATED"]}}},
        {"properties": {"mode": {"enum": ["DIRECT"]}}, "required": ["originalPaymentReference"]},
        {"properties": {"mode": {"enum": ["ESCROW"]}}, "required": ["originalPaymentReference", "escrowStatus"]},
    ]},
    {"oneOf": [
        absent("transferReversalStatus", "transferReversalReference", "transferReversalFailureCause"),
        {"properties": {"mode": {"enum": ["ESCROW"]}, "transferReversalStatus": {"enum": ["NOT_REQUIRED", "PENDING"]}},
         "required": ["transferReversalStatus"], **absent("transferReversalReference", "transferReversalFailureCause")},
        {"properties": {"mode": {"enum": ["ESCROW"]}, "transferReversalStatus": {"enum": ["SUCCEEDED"]}},
         "required": ["transferReversalStatus", "transferReversalReference"], **absent("transferReversalFailureCause")},
        {"properties": {"mode": {"enum": ["ESCROW"]}, "transferReversalStatus": {"enum": ["FAILED"]}},
         "required": ["transferReversalStatus", "transferReversalFailureCause"]},
    ]},
]

S["CancellationInfo"] = obj({
    "cancelledBy": ref("CancelledBy"),
    "reason": s(maxLength=500),
    "cancelledAt": dt(),
}, ["cancelledBy", "cancelledAt"])

S["BookingSummary"] = obj({
    "bookingId": uuid("PP booking reference"),
    "bookingCode": s("Short human-readable code", pattern=r"^RS-[A-Z]{2}-[A-Z0-9]{5}$"),
    "status": ref("BookingStatus"),
    "customerId": uuid(),
    "providerId": uuid(), "branchId": uuid(), "roomId": uuid(),
    "providerName": s(), "branchName": s(), "roomName": s(),
    "checkInDate": date(), "checkOutDate": date(),
    "quantity": i(minimum=1), "adults": i(minimum=1), "children": i(minimum=0),
    "priceBreakdown": ref("PriceBreakdown"),
    "payment": ref("BookingPaymentStatus"),
    "cancellation": described(ref("CancellationInfo"), "Present when status is CANCELLED"),
    "createdAt": dt(), "updatedAt": dt(),
}, ["bookingId", "bookingCode", "status", "customerId", "providerId", "branchId", "roomId", "providerName", "branchName",
    "roomName", "checkInDate", "checkOutDate", "quantity", "adults", "children", "priceBreakdown", "payment", "createdAt",
    "updatedAt"], "Authoritative booking state owned by PP.")

S["Booking"] = {"allOf": [ref("BookingSummary"), obj({
    "reviewableFrom": date("Equal to checkInDate (Decision D-10)"),
    "receptionistContact": obj({"branchName": s(), "branchPhone": PHONE}, ["branchName", "branchPhone"], "Branch public desk contact"),
})], "description": "Booking returned on creation."}

S["ErrorDetail"] = obj({"field": s(), "issue": s()}, ["field", "issue"])
S["Error"] = obj({
    "error": obj({
        "code": s("Stable machine-readable code"),
        "message": s("Human-readable message, safe to show to end users"),
        "details": arr(ref("ErrorDetail")),
        "httpStatus": i("Kafka responses only: equivalent HTTP status"),
        "refundRequiredByPayer": b("CreateBooking only: CP must refund a payment it already captured (Decision D-14)"),
        "availableQuantity": i("INSUFFICIENT_AVAILABILITY only", minimum=0),
        "requestId": s("Echo of X-Request-Id or the Kafka messageId"),
        "timestamp": dt(),
    }, ["code", "message", "requestId", "timestamp"]),
}, ["error"], "Standard error body (01-conventions.md Section 5).")

S["TokenRequest"] = obj({
    "clientId": enum(["cp-subsystem", "pp-subsystem"], "Partner client ID"),
    "clientSecret": s("At least 32 random characters, held in environment variables", minLength=32),
    "scope": arr(s(), "Requested scopes. Defaults to every scope granted to the client."),
}, ["clientId", "clientSecret"])
S["TokenResponse"] = obj({
    "accessToken": s("Signed JWT (JWS, RS256) identifying the partner system, not an end user"),
    "tokenType": enum(["Bearer"], "Always Bearer"),
    "expiresIn": i("Seconds until expiry", minimum=1),
    "scope": arr(s()),
}, ["accessToken", "tokenType", "expiresIn", "scope"])

S["Comment"] = obj({
    "reviewId": uuid(), "overallScore": i(minimum=1, maximum=5), "text": s(), "createdAt": dt(), "updatedAt": dt(),
}, ["reviewId", "overallScore", "createdAt"], "Review comment sourced from CP.")

S["SearchProvidersResponse"] = obj({
    "items": arr(ref("ProviderSearchResult")),
    "pageInfo": ref("PageInfo"),
    "appliedFilters": obj({}, desc="Echo of interpreted filters, including FTS-recognised phrases under 'recognised'",
                          additionalProperties=True),
}, ["items", "pageInfo", "appliedFilters"])

S["BranchDetails"] = obj({
    "branch": ref("ProviderSearchResult"),
    "description": s(maxLength=2000),
    "imageUrls": arr(s(format="uri")),
    "checkInTime": TIME_HHMM, "checkOutTime": TIME_HHMM,
    "latestComments": arr(ref("Comment"), "Up to 3 recent comments from CP; empty if none or CP unavailable", maxItems=3),
}, ["branch", "description", "imageUrls", "checkInTime", "checkOutTime", "latestComments"])

S["RoomListResponse"] = obj({"items": arr(ref("RoomSummary")), "pageInfo": ref("PageInfo")}, ["items", "pageInfo"])
S["BookingListResponse"] = obj({"items": arr(ref("BookingSummary")), "pageInfo": ref("PageInfo")}, ["items", "pageInfo"])

S["QuoteRequest"] = obj({
    "customerId": uuid(),
    "membership": ref("MembershipSnapshot"),
    "roomId": uuid(),
    "checkInDate": date("On or after today in the branch time zone"),
    "checkOutDate": date("After checkInDate, at most 30 nights"),
    "quantity": i(minimum=1),
    "adults": i(minimum=1),
    "children": i("Rule: quantity <= adults + children (PP-BOOK-S02)", minimum=0),
    "paymentMode": ref("PaymentMode"),
}, ["customerId", "membership", "roomId", "checkInDate", "checkOutDate", "quantity", "adults", "children", "paymentMode"])

S["Payee"] = obj({
    "gateway": ref("PaymentGateway"),
    "payeeAccountId": s("PayPal merchant ID or Stripe connected account ID"),
    "payeeDisplayName": s(),
}, ["gateway", "payeeAccountId", "payeeDisplayName"], "Payee for the customer's payment (Decision D-07).")

S["Quote"] = obj({
    "quoteId": uuid(),
    "roomId": uuid(), "branchId": uuid(), "providerId": uuid(),
    "checkInDate": date(), "checkOutDate": date(),
    "quantity": i(minimum=1), "adults": i(minimum=1), "children": i(minimum=0),
    "priceBreakdown": ref("PriceBreakdown"),
    "membershipVerified": b("true when CP-OP-02 confirmed an active Premium membership"),
    "payee": described(ref("Payee"), "Omitted for SIMULATED"),
    "holdExpiresAt": dt("createdAt + 15 minutes"),
    "createdAt": dt(),
}, ["quoteId", "roomId", "branchId", "providerId", "checkInDate", "checkOutDate", "quantity", "adults", "children",
    "priceBreakdown", "membershipVerified", "holdExpiresAt", "createdAt"], "Binding price quote with a 15-minute inventory hold.")

S["CreateBookingRequest"] = obj({
    "quoteId": uuid("From CreatePriceQuote"),
    "customer": ref("CustomerSnapshot"),
    "membership": ref("MembershipSnapshot"),
    "roomId": uuid(),
    "checkInDate": date(), "checkOutDate": date(),
    "quantity": i(minimum=1), "adults": i(minimum=1), "children": i(minimum=0),
    "payment": ref("PaymentInfo"),
    "specialRequest": s(maxLength=500),
}, ["quoteId", "customer", "membership", "roomId", "checkInDate", "checkOutDate", "quantity", "adults", "children", "payment"])

S["CancelBookingRequest"] = obj({
    "customerId": uuid("Must own the booking"),
    "reason": s(maxLength=500),
}, ["customerId"])

S["ReviewEligibility"] = obj({
    "bookingId": uuid(), "customerId": uuid(),
    "providerId": uuid("Review target. Reviews are per provider, not per room."),
    "providerName": s("Accommodation provider company name"),
    "branchId": uuid(),
    "branchName": s("Booked branch property name"),
    "stayStartDate": date(), "stayEndDate": date(),
    "reviewableFrom": date(),
    "bookingStatus": ref("BookingStatus"),
    "eligible": b(),
    "reason": enum(["BEFORE_STAY_START", "BOOKING_CANCELLED", "NOT_CONFIRMED", "NOT_BOOKING_OWNER"], "Present when eligible is false"),
    "evaluatedAt": dt(),
}, ["bookingId", "customerId", "eligible", "evaluatedAt"], "Review eligibility (Decision D-10).")

S["EventInfo"] = obj({
    "eventId": uuid("CP event ID"),
    "name": s(),
    "summary": s(maxLength=300),
    "locationName": s(),
    "city": s(), "country": COUNTRY, "timeZone": s("IANA time zone"),
    "startDate": date(), "endDate": date(),
    "searchRoute": s("CP frontend route opening the city search"),
}, ["eventId", "name", "summary", "locationName", "city", "country", "timeZone", "startDate", "endDate", "searchRoute"],
    "Regional event data supplied by CP (CP owns events).")

S["EventSuggestion"] = obj({
    "rank": i(minimum=1, maximum=2),
    "providerId": uuid(),
    "providerName": s("Accommodation provider's (company) name"),
    "branchId": uuid(),
    "name": s("Accommodation (branch) name"),
    "type": ref("ProviderCategory"),
    "logoUrl": s(format="uri"),
    "pricePerNight": described(ref("Money"), "Lowest available price for the event dates"),
    "overallRating": num("From CP statistics. Omitted when there are no reviews.", minimum=1, maximum=5),
    "totalReviews": i(minimum=0),
}, ["rank", "providerId", "providerName", "branchId", "name", "type", "logoUrl", "pricePerNight", "totalReviews"],
    "One of the two most highly rated providers in the event city (PP-EVENT-S02).")

S["EventSuggestionRequest"] = obj({
    "requestId": uuid(), "favoriteId": uuid(), "customerId": uuid(), "event": ref("EventInfo"),
}, ["requestId", "favoriteId", "customerId", "event"])

S["EventSuggestionResponse"] = obj({
    "requestId": uuid(), "favoriteId": uuid(), "customerId": uuid(),
    "event": ref("EventInfo"),
    "suggestions": arr(ref("EventSuggestion"), maxItems=2),
    "reason": enum(["NO_AVAILABLE_PROVIDERS_IN_CITY", "ONLY_ONE_AVAILABLE_PROVIDER"], "Present when fewer than 2 suggestions"),
    "generatedAt": dt(),
}, ["requestId", "favoriteId", "customerId", "event", "suggestions", "generatedAt"])

S["EmailData"] = obj({
    "bookingCode": s(), "providerName": s(), "branchName": s(), "branchAddress": s(), "branchPhone": PHONE,
    "roomName": s(), "checkInDate": date(), "checkOutDate": date(), "checkInTime": TIME_HHMM,
    "quantity": i(minimum=1), "adults": i(minimum=1), "children": i(minimum=0), "total": ref("Money"),
}, ["bookingCode", "providerName", "branchName", "branchAddress", "branchPhone", "roomName", "checkInDate",
    "checkOutDate", "checkInTime", "quantity", "adults", "children", "total"], "Content for CP's customer email (PP-MONEY-S01).")

S["BookingStatusEvent"] = obj({
    "eventId": uuid("CP de-duplicates on this"),
    "eventType": enum(["BOOKING_CONFIRMED", "BOOKING_CANCELLED", "BOOKING_COMPLETED", "RETURN_PAYMENT_UPDATED", "ESCROW_RELEASE_UPDATED"], "Event type"),
    "occurredAt": dt(),
    "sequence": i("Increases per bookingId; CP ignores lower sequences", minimum=1),
    "booking": ref("BookingSummary"),
    "emailData": described(ref("EmailData"), "Present for BOOKING_CONFIRMED and BOOKING_CANCELLED"),
    "message": s("Short receptionist note shown to the customer"),
}, ["eventId", "eventType", "occurredAt", "sequence", "booking"], "Booking status change pushed by PP (PP-OP-11).")

S["BookingEventAck"] = obj({"eventId": uuid(), "accepted": b(), "duplicate": b()}, ["eventId", "accepted", "duplicate"])

S["StarDistribution"] = obj({k: i(minimum=0) for k in "12345"}, list("12345"), "Count of reviews per star value.")
S["OverallStatistics"] = obj({
    "average": num(minimum=1, maximum=5), "count": i(minimum=0), "distribution": ref("StarDistribution"),
}, ["count", "distribution"], "Overall statistics. Overall has no preset options.")
S["PresetOptionStatistics"] = obj({
    "optionId": s(), "starGroup": ref("StarGroup"), "label": s(),
    "selectedCount": i(minimum=0),
    "denominator": i("Reviews whose subcategory score falls in starGroup (Decision D-11)", minimum=0),
    "percentage": num("selectedCount / denominator x 100, one decimal; 0.0 when denominator is 0", minimum=0, maximum=100),
}, ["optionId", "starGroup", "label", "selectedCount", "denominator", "percentage"])
S["SubcategoryStatistics"] = obj({
    "subcategory": ref("RatingSubcategory"),
    "average": num(minimum=1, maximum=5), "count": i(minimum=0),
    "distribution": ref("StarDistribution"),
    "presetOptions": arr(ref("PresetOptionStatistics"), "Two per star group, six per subcategory", maxItems=6),
}, ["subcategory", "count", "distribution", "presetOptions"])
S["CommentsPage"] = obj({"items": arr(ref("Comment")), "nextCursor": s()}, ["items"])
S["RatingStatistics"] = obj({
    "providerId": uuid(), "asOf": dt(),
    "totalReviews": i("Active (non-archived) reviews", minimum=0),
    "overall": ref("OverallStatistics"),
    "subcategories": arr(ref("SubcategoryStatistics"), "Medium and above"),
    "comments": ref("CommentsPage"),
}, ["providerId", "asOf", "totalReviews", "overall"], "Provider-level statistics calculated by CP (CP-RATING-M03).")
S["Membership"] = obj({
    "customerId": uuid(), "tier": ref("MembershipTier"), "status": ref("MembershipStatus"),
    "validFrom": dt(), "validUntil": dt(),
}, ["customerId", "tier", "status"])
S["UpdateOrderRequest"] = obj({
    "action": enum(["COMPLETE", "CANCEL"], "COMPLETE on receptionist approval, CANCEL on cancellation"),
    "bookingId": uuid(), "reason": s(maxLength=500),
}, ["action", "bookingId"])
S["Order"] = obj({
    "orderId": uuid(), "status": enum(["ISSUED", "COMPLETED", "CANCELLED"], "Simulated order status"),
    "bookingId": uuid(), "updatedAt": dt(),
}, ["orderId", "status", "bookingId", "updatedAt"])

# Kafka-only payloads
S["SearchProvidersRequest"] = obj({
    "city": s(maxLength=100), "country": COUNTRY, "q": s(maxLength=200),
    "category": arr(ref("ProviderCategory")), "roomType": arr(ref("RoomType")), "amenities": arr(ref("Amenity")),
    "matchMode": ref("MatchMode"), "checkInDate": date(), "checkOutDate": date(),
    "rooms": i(minimum=1), "sort": ref("SearchSort"), "limit": i(minimum=1, maximum=50), "cursor": s(),
}, ["city"], "Kafka payload equivalent of the PP-OP-01 query parameters.")
S["GetBranchRequest"] = obj({"branchId": uuid(), "checkInDate": date(), "checkOutDate": date()}, ["branchId"])
S["ListRoomsRequest"] = obj({
    "branchId": uuid(), "checkInDate": date(), "checkOutDate": date(), "rooms": i(minimum=1),
    "roomType": arr(ref("RoomType")), "amenities": arr(ref("Amenity")), "membershipTier": ref("MembershipTier"),
    "limit": i(minimum=1, maximum=50), "cursor": s(),
}, ["branchId"])
S["GetRoomRequest"] = obj({"roomId": uuid(), "checkInDate": date(), "checkOutDate": date(), "membershipTier": ref("MembershipTier")}, ["roomId"])
S["GetBookingRequest"] = obj({"bookingId": uuid(), "customerId": uuid()}, ["bookingId", "customerId"])
S["ListBookingsRequest"] = obj({
    "customerId": uuid(), "orderId": uuid("Optional exact CP-order lookup for timeout reconciliation"),
    "status": arr(ref("BookingStatus")), "stayFrom": date(), "stayTo": date(),
    "sort": enum(["CHECK_IN_DESC", "CREATED_DESC"], "Sort order"), "limit": i(minimum=1, maximum=50), "cursor": s(),
}, ["customerId"])
S["CancelBookingCommand"] = obj({"bookingId": uuid(), "customerId": uuid(), "reason": s(maxLength=500)}, ["bookingId", "customerId"])
S["GetEligibilityRequest"] = obj({"bookingId": uuid(), "customerId": uuid()}, ["bookingId", "customerId"])
S["RatingStatisticsRequest"] = obj({
    "providerId": uuid(), "include": arr(ref("StatisticsScope")),
    "commentsLimit": i(minimum=1, maximum=50), "commentsCursor": s(),
}, ["providerId"])
S["MembershipRequest"] = obj({"customerId": uuid()}, ["customerId"])
S["EventFavoriteChanged"] = obj({
    "changeType": enum(["FAVORITE_ADDED", "FAVORITE_REMOVED", "EVENT_DATES_CHANGED", "EVENT_DELETED"], "Change type"),
    "favoriteId": uuid("Required for FAVORITE_*"),
    "customerId": uuid("Required for FAVORITE_*"),
    "favoritedAt": dt("Required for FAVORITE_ADDED"),
    "event": ref("EventInfo"),
}, ["changeType", "event"], "CP-OP-05 payload.")
S["EventFavoriteChanged"]["oneOf"] = [
    {"properties": {"changeType": {"enum": ["FAVORITE_ADDED"]}},
     "required": ["favoriteId", "customerId", "favoritedAt"]},
    {"properties": {"changeType": {"enum": ["FAVORITE_REMOVED"]}},
     "required": ["favoriteId", "customerId"]},
    {"properties": {"changeType": {"enum": ["EVENT_DATES_CHANGED"]}},
     **absent("favoriteId", "customerId", "favoritedAt")},
    {"properties": {"changeType": {"enum": ["EVENT_DELETED"]}},
     **absent("favoriteId", "customerId", "favoritedAt")},
]
S["RegionalEventNotification"] = obj({
    "notificationId": uuid("CP de-duplicates on this"),
    "favoriteId": uuid(), "customerId": uuid(),
    "trigger": enum(["IMMEDIATE_WITHIN_WINDOW", "IMMEDIATE_ONGOING", "SCHEDULED_TWO_MONTH"], "Why the notification was published (Decision D-12)"),
    "notificationWindowStart": date(),
    "event": ref("EventInfo"),
    "suggestions": arr(ref("EventSuggestion"), maxItems=2),
    "searchLink": s("Equal to event.searchRoute"),
    "publishedAt": dt(),
}, ["notificationId", "favoriteId", "customerId", "trigger", "notificationWindowStart", "event", "suggestions", "searchLink", "publishedAt"],
    "PP-OP-13 payload.")
S["KafkaEnvelope"] = obj({
    "messageId": uuid("Unique per message; a resend gets a new messageId"),
    "correlationId": uuid("Set by the requester; copied into the response; unchanged on resend"),
    "traceId": uuid("Business-flow trace shared by related logical requests and events; never a pending-request or deduplication key"),
    "idempotencyKey": uuid("Required for CREATE_QUOTE, CREATE_BOOKING and CANCEL_BOOKING; unchanged across retries"),
    "causationId": uuid("messageId of the message that caused this one"),
    "type": s("Operation type, e.g. CREATE_BOOKING or CREATE_BOOKING_RESULT"),
    "schemaVersion": enum(["1.0"], "Payload schema version"),
    "source": s("PP or CP (prefixed with the squad ID on the PMS broker)"),
    "replyTo": s("Requests only: response topic (receive channel)"),
    "attempt": i("Requests only: 1 on first send, incremented on each resend", minimum=1),
    "deadline": dt("Requests only: responder may skip requests past this time"),
    "timestamp": dt(),
    "status": enum(["OK", "ERROR"], "Responses only"),
    "payload": obj({}, desc="Request body, response body, or the Error body", additionalProperties=True),
}, ["messageId", "correlationId", "traceId", "type", "schemaVersion", "source", "timestamp", "payload"],
    "Envelope for every Kafka message (04-kafka.md Section 1).")


# ---------------------------------------------------------------- examples
def money(a):
    return {"amountMinor": a, "currency": "USD"}


IDS = dict(
    customer="7d1e2f30-0000-4000-8000-000000000901", provider="5b1c2d3e-0000-4000-8000-000000000150",
    branch="9a8b7c6d-0000-4000-8000-000000000250", room="3f2e1d0c-0000-4000-8000-000000000301",
    quote="1a2b3c4d-0000-4000-8000-000000000501", order="55aa66bb-0000-4000-8000-000000000701",
    booking="8c9d0e1f-0000-4000-8000-000000000801", discount="d15c0a7e-0000-4000-8000-000000000015",
    review="a1b2c3d4-0000-4000-8000-000000000601", event="e7e70000-0000-4000-8000-000000000c01",
    favorite="fa7e0000-0000-4000-8000-000000000b01", request="2e9b0c11-0000-4000-8000-000000000a01",
    trace="7ace0000-0000-4000-8000-000000000001",
)
LOC = {"addressLine": "21 Nguyen Phuc Chu", "city": "Hoi An", "country": "VN", "timeZone": "Asia/Ho_Chi_Minh"}
RATING = {"overallAverage": 4.8, "totalReviews": 41, "source": "CP", "asOf": "2026-11-20T10:40:00Z"}
BRANCH = {
    "providerId": IDS["provider"], "providerName": "Thu Bon Family Stays", "branchId": IDS["branch"],
    "branchName": "Riverside Homestay Hoi An", "category": "HOMESTAY",
    "logoUrl": "https://cdn.roomscanner.local/logos/thubon_256.webp", "location": LOC,
    "roomTypesOffered": ["SINGLE_TWIN_BED", "DOUBLE_BED"], "amenities": ["FREE_WIFI", "KITCHEN", "WASHING_MACHINE"],
    "availableRoomCount": 4, "lowestPricePerNight": money(2500), "ratingSummary": RATING,
}
ROOM = {
    "roomId": IDS["room"], "branchId": IDS["branch"], "name": "Garden Single Room", "roomType": "SINGLE_TWIN_BED",
    "maxOccupancy": 2, "totalQuantity": 3, "availableQuantity": 2, "pricePerNight": money(2500),
    "premiumPricePerNight": money(2125), "amenities": ["FREE_WIFI", "KITCHEN"],
    "thumbnailUrl": "https://cdn.roomscanner.local/rooms/301/1_thumb.webp",
    "imageUrls": ["https://cdn.roomscanner.local/rooms/301/1.webp", "https://cdn.roomscanner.local/rooms/301/2.webp"],
}
POLICY = {"discountPackageId": IDS["discount"], "name": "Premium 15% Off", "type": "PERCENTAGE", "value": 15, "eligibleTier": "PREMIUM", "active": True}
ROOM_DETAIL = dict(ROOM, bedCount=1, sizeSqm=18, description="Quiet single room facing the garden, shared kitchen access.",
                   checkInTime="14:00", checkOutTime="12:00", discountPolicy=POLICY, provider=BRANCH)
APPLIED = {"discountPackageId": IDS["discount"], "name": "Premium 15% Off", "type": "PERCENTAGE", "value": 15, "amount": money(2250)}
PRICE = {"nights": 3, "quantity": 2, "unitPricePerNight": money(2500), "subtotal": money(15000), "discount": APPLIED, "total": money(12750)}
MEMBERSHIP = {"tier": "PREMIUM", "status": "ACTIVE", "validUntil": "2027-08-01T00:00:00Z"}
STAY = {"checkInDate": "2027-04-10", "checkOutDate": "2027-04-13", "quantity": 2, "adults": 3, "children": 1}
QUOTE_REQ = dict(customerId=IDS["customer"], membership=MEMBERSHIP, roomId=IDS["room"], **STAY, paymentMode="ESCROW")
QUOTE = dict(quoteId=IDS["quote"], roomId=IDS["room"], branchId=IDS["branch"], providerId=IDS["provider"], **STAY,
             priceBreakdown=PRICE, membershipVerified=True,
             payee={"gateway": "STRIPE_SANDBOX", "payeeAccountId": "acct_1PxThuBonTEST", "payeeDisplayName": "Thu Bon Family Stays"},
             holdExpiresAt="2026-12-01T03:15:00Z", createdAt="2026-12-01T03:00:00Z")
CUSTOMER = {"customerId": IDS["customer"], "email": "tim.nguyen@example.com", "phone": "+84901234567", "countryOfResidence": "VN"}
PAYMENT = {"mode": "ESCROW", "gateway": "STRIPE_SANDBOX", "orderId": IDS["order"], "paymentReference": "pi_3QAbCdTEST0001",
           "chargeReference": "ch_3QAbCdTEST0001", "state": "CAPTURED_HELD", "amount": money(12750), "paidAt": "2026-12-01T03:02:10Z"}
BOOK_REQ = dict(quoteId=IDS["quote"], customer=CUSTOMER, membership=MEMBERSHIP, roomId=IDS["room"], **STAY,
                payment=PAYMENT, specialRequest="Late arrival around 22:00")
SUMMARY = dict(bookingId=IDS["booking"], bookingCode="RS-VN-24F7Q", status="PENDING_APPROVAL", customerId=IDS["customer"],
               providerId=IDS["provider"], branchId=IDS["branch"], roomId=IDS["room"], providerName="Thu Bon Family Stays",
               branchName="Riverside Homestay Hoi An", roomName="Garden Single Room", **STAY, priceBreakdown=PRICE,
               payment={"mode": "ESCROW", "orderId": IDS["order"], "originalPaymentReference": "pi_3QAbCdTEST0001", "escrowStatus": "HELD", "returnPaymentStatus": "NOT_REQUIRED"},
               createdAt="2026-12-01T03:02:12Z", updatedAt="2026-12-01T03:02:12Z")
BOOKING = dict(SUMMARY, reviewableFrom="2027-04-10", receptionistContact={"branchName": "Riverside Homestay Hoi An", "branchPhone": "+842353861234"})
CONFIRMED = dict(SUMMARY, status="CONFIRMED", updatedAt="2026-12-01T09:15:40Z",
                 payment={"mode": "ESCROW", "originalPaymentReference": "pi_3QAbCdTEST0001", "escrowStatus": "RELEASED",
                          "releaseReference": "tr_1QXyzTEST0001", "returnPaymentStatus": "NOT_REQUIRED"})
CANCELLED = dict(SUMMARY, status="CANCELLED", updatedAt="2026-12-03T05:00:00Z",
                 cancellation={"cancelledBy": "CUSTOMER", "reason": "Change of travel plans", "cancelledAt": "2026-12-03T05:00:00Z"},
                 payment={"mode": "ESCROW", "originalPaymentReference": "pi_3QAbCdTEST0001", "escrowStatus": "HELD", "returnPaymentStatus": "PENDING"})
ELIG = {"bookingId": IDS["booking"], "customerId": IDS["customer"], "providerId": IDS["provider"], "providerName": "Thu Bon Family Stays",
        "branchId": IDS["branch"], "branchName": "Riverside Homestay Hoi An",
        "stayStartDate": "2027-04-10", "stayEndDate": "2027-04-13", "reviewableFrom": "2027-04-10", "bookingStatus": "CONFIRMED",
        "eligible": False, "reason": "BEFORE_STAY_START", "evaluatedAt": "2027-04-09T10:00:00Z"}
EVENT = {"eventId": IDS["event"], "name": "Hùng Kings' Temple Festival",
         "summary": "National festival honouring the Hùng Kings with processions, folk games and xoan singing.",
         "locationName": "Hùng Kings' Temple, Viet Tri City, Phu Tho", "city": "Viet Tri", "country": "VN",
         "timeZone": "Asia/Ho_Chi_Minh", "startDate": "2027-04-12", "endDate": "2027-04-18",
         "searchRoute": "/search?city=Viet%20Tri&country=VN&checkIn=2027-04-12&checkOut=2027-04-13"}
SUGG = [
    {"rank": 1, "providerId": "5b1c2d3e-0000-4000-8000-000000000170", "providerName": "Phu Tho Tourism JSC",
     "branchId": "9a8b7c6d-0000-4000-8000-000000000270", "name": "Saigon Phu Tho Hotel", "type": "HOTEL",
     "logoUrl": "https://cdn.roomscanner.local/logos/sgpt_256.webp", "pricePerNight": money(4200), "overallRating": 4.7, "totalReviews": 63},
    {"rank": 2, "providerId": "5b1c2d3e-0000-4000-8000-000000000171", "providerName": "Song Lo Homes",
     "branchId": "9a8b7c6d-0000-4000-8000-000000000271", "name": "Song Lo Riverside Homestay", "type": "HOMESTAY",
     "logoUrl": "https://cdn.roomscanner.local/logos/songlo_256.webp", "pricePerNight": money(1800), "overallRating": 4.5, "totalReviews": 22},
]
EVSUG_REQ = {"requestId": IDS["request"], "favoriteId": IDS["favorite"], "customerId": IDS["customer"], "event": EVENT}
EVSUG_RESP = dict(EVSUG_REQ, suggestions=SUGG, generatedAt="2027-02-15T04:00:01Z")
EMAIL = {"bookingCode": "RS-VN-24F7Q", "providerName": "Thu Bon Family Stays", "branchName": "Riverside Homestay Hoi An",
         "branchAddress": "21 Nguyen Phuc Chu, Hoi An, VN", "branchPhone": "+842353861234", "roomName": "Garden Single Room",
         "checkInDate": "2027-04-10", "checkOutDate": "2027-04-13", "checkInTime": "14:00", "quantity": 2, "adults": 3,
         "children": 1, "total": money(12750)}
BOOKING_EVENT = {"eventId": "11112222-0000-4000-8000-000000000001", "eventType": "BOOKING_CONFIRMED",
                 "occurredAt": "2026-12-01T09:15:40Z", "sequence": 2, "booking": CONFIRMED, "emailData": EMAIL}
DIST = {"1": 0, "2": 0, "3": 1, "4": 1, "5": 3}
STATS = {
    "providerId": IDS["provider"], "asOf": "2026-12-01T04:00:00Z", "totalReviews": 5,
    "overall": {"average": 4.4, "count": 5, "distribution": DIST},
    "subcategories": [{
        "subcategory": "SERVICE", "average": 4.2, "count": 5, "distribution": {"1": 0, "2": 0, "3": 1, "4": 2, "5": 2},
        "presetOptions": [
            {"optionId": "SRV-45-A", "starGroup": "FOUR_TO_FIVE", "label": "The food is delicious", "selectedCount": 3, "denominator": 4, "percentage": 75.0},
            {"optionId": "SRV-45-B", "starGroup": "FOUR_TO_FIVE", "label": "The services are highly convenient and efficient", "selectedCount": 2, "denominator": 4, "percentage": 50.0},
            {"optionId": "SRV-3-A", "starGroup": "THREE", "label": "Service was acceptable", "selectedCount": 0, "denominator": 1, "percentage": 0.0},
            {"optionId": "SRV-3-B", "starGroup": "THREE", "label": "Staff were slow at peak times", "selectedCount": 1, "denominator": 1, "percentage": 100.0},
            {"optionId": "SRV-12-A", "starGroup": "ONE_TO_TWO", "label": "Requests were ignored", "selectedCount": 0, "denominator": 0, "percentage": 0.0},
            {"optionId": "SRV-12-B", "starGroup": "ONE_TO_TWO", "label": "Food quality was poor", "selectedCount": 0, "denominator": 0, "percentage": 0.0},
        ]}],
    "comments": {"items": [{"reviewId": IDS["review"], "overallScore": 5, "text": "Lovely hosts and a great breakfast.",
                            "createdAt": "2026-10-02T08:00:00Z", "updatedAt": "2026-10-02T08:00:00Z"}]},
}
MEMBER = {"customerId": IDS["customer"], "tier": "PREMIUM", "status": "ACTIVE", "validFrom": "2026-08-01T00:00:00Z", "validUntil": "2027-08-01T00:00:00Z"}
TOKEN_REQ_CP = {"clientId": "cp-subsystem", "clientSecret": "replace-with-secret-from-environment-0123456789", "scope": ["search:read", "booking:write"]}
TOKEN_REQ_PP = {"clientId": "pp-subsystem", "clientSecret": "replace-with-secret-from-environment-0123456789", "scope": ["rating:read", "membership:read"]}
TOKEN_RESP = lambda sc: {"accessToken": "eyJhbGciOiJSUzI1NiIsImtpZCI6InBwLTIwMjYtMTEifQ.eyJzdWIiOiJjcC1zdWJzeXN0ZW0ifQ.c2lnbmF0dXJl",
                         "tokenType": "Bearer", "expiresIn": 900, "scope": sc}


def err(code, msg, details=None, **extra):
    e = {"code": code, "message": msg}
    if details:
        e["details"] = details
    e.update(extra)
    e.update({"requestId": "0b6f8f4c-5a5e-4c55-8a39-31b2f1b9b0a7", "timestamp": "2026-11-20T11:00:00Z"})
    return {"error": e}


def ex(value, summary=None):
    d = {"value": value}
    if summary:
        d["summary"] = summary
    return d


# ---------------------------------------------------------------- OpenAPI building blocks
COMMON_PARAMS = {
    "XRequestId": {"name": "X-Request-Id", "in": "header", "required": True, "description": "UUID per HTTP call; echoed by the server.", "schema": uuid()},
    "XCorrelationId": {"name": "X-Correlation-Id", "in": "header", "required": True, "description": "UUID for one logical operation; reused only for its transport retries and response.", "schema": uuid()},
    "XTraceId": {"name": "X-Trace-Id", "in": "header", "required": True, "description": "Business-flow UUID shared by related operations; maps to Kafka traceId.", "schema": uuid()},
    "IdempotencyKey": {"name": "Idempotency-Key", "in": "header", "required": True,
                       "description": "UUID scoped to the authenticated partner and operation. Same key/body replays the original outcome; changed body returns 409. Durable booking/payment uniqueness survives Redis cache expiry.", "schema": uuid()},
    "Limit": {"name": "limit", "in": "query", "required": False, "description": "Page size.", "schema": i(minimum=1, maximum=50, default=10)},
    "Cursor": {"name": "cursor", "in": "query", "required": False, "description": "Opaque cursor from pageInfo.nextCursor.", "schema": s()},
    "CheckInDate": {"name": "checkInDate", "in": "query", "required": False, "description": "Must be sent with checkOutDate. Default: tonight (Decision D-05).", "schema": date()},
    "CheckOutDate": {"name": "checkOutDate", "in": "query", "required": False, "description": "After checkInDate, at most 30 nights.", "schema": date()},
    "MembershipTierQuery": {"name": "membershipTier", "in": "query", "required": False, "description": "When PREMIUM, premiumPricePerNight is filled where a policy is assigned.", "schema": ref("MembershipTier")},
}
RL_HEADERS = {
    "X-Request-Id": {"description": "Echo of the request header", "schema": uuid()},
    "X-Correlation-Id": {"description": "Echo of this logical operation's correlation ID", "schema": uuid()},
    "X-Trace-Id": {"description": "Echo of the business-flow trace ID", "schema": uuid()},
    "X-RateLimit-Limit": {"description": "Requests allowed in the window", "schema": i()},
    "X-RateLimit-Remaining": {"description": "Requests left in the window", "schema": i()},
    "X-RateLimit-Reset": {"description": "Seconds until the window resets", "schema": i()},
}


def path_param(name, desc):
    return {"name": name, "in": "path", "required": True, "description": desc, "schema": uuid()}


def err_resp(desc, examples, retry_after=False):
    headers = {name: RL_HEADERS[name] for name in ["X-Request-Id", "X-Correlation-Id", "X-Trace-Id"]}
    if retry_after:
        headers["Retry-After"] = {"description": "Seconds before retrying", "schema": i()}
    return {"description": desc, "headers": headers,
            "content": {"application/json": {"schema": ref("Error"), "examples": examples}}}


STD_RESPONSES = {
    "BadRequest": err_resp("Malformed or missing fields.", {"validation": ex(err("VALIDATION_ERROR", "checkOutDate must be after checkInDate.", [{"field": "checkOutDate", "issue": "must be after checkInDate"}]))}),
    "Unauthorized": err_resp("Missing, expired or invalid partner token or signature.", {"unauthenticated": ex(err("PARTNER_UNAUTHENTICATED", "The partner access token is missing or expired."))}),
    "Forbidden": err_resp("Token lacks the required scope, or the resource is outside the agreed data scope.", {"forbidden": ex(err("PARTNER_FORBIDDEN", "Scope booking:write is required."))}),
    "NotFound": err_resp("Unknown or archived resource.", {"notFound": ex(err("RESOURCE_NOT_FOUND", "The requested resource does not exist."))}),
    "TooManyRequests": err_resp("Rate limit exceeded (BE-U04).", {"rateLimited": ex(err("RATE_LIMITED", "Rate limit exceeded for this scope (see common/01-conventions.md Section 7). Retry after the Retry-After interval."))}, retry_after=True),
    "ServiceUnavailable": err_resp("Destination down or circuit open. Always distinct from 4xx business errors.", {"unavailable": ex(err("SERVICE_UNAVAILABLE", "The service is temporarily unavailable. Retry later."))}, retry_after=True),
}


def R(name):
    return {"$ref": f"#/components/responses/{name}"}


def P(name):
    return {"$ref": f"#/components/parameters/{name}"}


def ok(desc, schema, examples, code="200"):
    return {code: {"description": desc, "headers": RL_HEADERS,
                   "content": {"application/json": {"schema": schema, "examples": examples}}}}


def body(schema, examples):
    return {"required": True, "content": {"application/json": {"schema": schema, "examples": examples}}}


def std_errors(*codes):
    m = {"400": "BadRequest", "401": "Unauthorized", "403": "Forbidden", "404": "NotFound", "429": "TooManyRequests", "503": "ServiceUnavailable"}
    return {c: R(m[c]) for c in codes}


def op(op_id, contract_id, summary, desc, tag, scope, params=None, request=None, responses=None, kafka=None, srs=None, security=None):
    o = {"tags": [tag], "operationId": op_id, "summary": f"{contract_id} {summary}", "description": desc.strip()}
    if srs:
        o["description"] += f"\n\n**SRS traceability:** {srs}"
    if kafka:
        o["description"] += f"\n\n**Ultimo Kafka binding:** {kafka}"
    o["x-contract-id"] = contract_id
    o["parameters"] = [P("XRequestId"), P("XCorrelationId"), P("XTraceId")] + (params or [])
    if request:
        o["requestBody"] = request
    o["responses"] = responses
    o["security"] = security if security is not None else [{"partnerBearer": []}]
    o["x-required-scopes"] = [scope]
    return o


def collect_refs(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/schemas/"):
                out.add(v.split("/")[-1])
            else:
                collect_refs(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_refs(v, out)


def prune_schemas(doc):
    used, frontier = set(), set()
    collect_refs({k: v for k, v in doc.items() if k != "components"}, frontier)
    collect_refs({k: v for k, v in doc["components"].items() if k != "schemas"}, frontier)
    while frontier:
        name = frontier.pop()
        if name in used:
            continue
        used.add(name)
        nxt = set()
        collect_refs(S[name], nxt)
        frontier |= nxt - used
    doc["components"]["schemas"] = {k: copy.deepcopy(S[k]) for k in S if k in used}


def security_schemes(scopes):
    return {
        "partnerBearer": {
            "type": "http", "scheme": "bearer", "bearerFormat": "JWT",
            "description": "Custom JSON partner-token issuance at POST /api/v1/partner/auth/token (INT-M03), "
                           "not an OAuth2 token endpoint. The signed JWS identifies a subsystem. "
                           "The gateway enforces each operation's x-required-scopes. End-user JWE tokens are never forwarded.",
            "x-granted-scopes": scopes,
        }
    }


def token_op(req_ex, resp_ex):
    return {"post": {
        "tags": ["Partner authentication"], "operationId": "issuePartnerToken", "summary": "Issue a partner access token",
        "description": "Custom JSON credential exchange for a short-lived signed JWT; this is not an OAuth2 token endpoint. "
                       "Secrets are shared out-of-band and never committed. Rate limit: 10 requests per 60 s.",
        "x-contract-id": "AUTH-01", "security": [],
        "parameters": [P("XRequestId"), P("XCorrelationId"), P("XTraceId")],
        "requestBody": body(ref("TokenRequest"), {"default": ex(req_ex)}),
        "responses": {**ok("Token issued.", ref("TokenResponse"), {"default": ex(resp_ex)}), **std_errors("400", "401", "429")},
    }}


def info(title, desc):
    return {"title": title, "version": VERSION, "description": desc.strip(),
            "contact": {"name": "RoomScanner squad API contract", "url": "https://github.com/SQUAD-ORGANIZATION/roomscanner-api-contract"}}


def servers(port, host, deployed_desc="Deployed, through the API Gateway on Machine 4"):
    return [
        {"url": f"http://localhost:{port}/api/v1/partner", "description": "Local / Simplex"},
        {"url": f"https://{host}.{{squad}}.roomscanner.local/api/v1/partner",
         "description": deployed_desc,
         "variables": {"squad": {"default": "squad", "description": "Squad identifier"}}},
    ]


# ---------------------------------------------------------------- PP OpenAPI
PP_SCOPES = {"search:read": "PP-OP-01 to PP-OP-04", "quote:write": "PP-OP-05", "booking:write": "PP-OP-06, PP-OP-09",
             "booking:read": "PP-OP-07, PP-OP-08, PP-OP-10", "event-suggestion:write": "PP-OP-12"}
pp_paths = {"/auth/token": token_op(TOKEN_REQ_CP, TOKEN_RESP(["search:read", "booking:write"]))}

search_params = [
    {"name": "city", "in": "query", "required": True, "description": "Case-insensitive exact city match inside the squad's sub-region.", "schema": s(maxLength=100), "example": "Hoi An"},
    {"name": "country", "in": "query", "required": False, "description": "Narrows the request to one shard (PP-SEARCH-U01).", "schema": COUNTRY},
    {"name": "q", "in": "query", "required": False, "description": "Simplex: case-insensitive substring on provider and branch name. Medium: multi-field full-text search (Decision D-03).", "schema": s(maxLength=200)},
    {"name": "category", "in": "query", "required": False, "style": "form", "explode": True, "schema": arr(ref("ProviderCategory"))},
    {"name": "roomType", "in": "query", "required": False, "style": "form", "explode": True, "schema": arr(ref("RoomType"))},
    {"name": "amenities", "in": "query", "required": False, "style": "form", "explode": True, "schema": arr(ref("Amenity"))},
    {"name": "matchMode", "in": "query", "required": False, "schema": ref("MatchMode")},
    P("CheckInDate"), P("CheckOutDate"),
    {"name": "rooms", "in": "query", "required": False, "description": "Rooms needed. Branches with fewer available rooms are excluded.", "schema": i(minimum=1, default=1)},
    {"name": "sort", "in": "query", "required": False, "schema": ref("SearchSort")},
    P("Limit"), P("Cursor"),
]
SEARCH_RESP = {"items": [dict(BRANCH, matchedFields=["category", "roomType", "amenities"], relevanceScore=0.97)],
               "pageInfo": {"limit": 10, "nextCursor": "eyJzIjowLjk3LCJpZCI6IjI1MCJ9", "hasMore": True},
               "appliedFilters": {"city": "Hoi An", "q": "Single Bed Free WiFi Homestay", "matchMode": "ANY",
                                  "recognised": {"category": ["HOMESTAY"], "roomType": ["SINGLE_TWIN_BED"], "amenities": ["FREE_WIFI"]}}}
pp_paths["/search/providers"] = {"get": op(
    "searchProviders", "PP-OP-01", "Search providers", "Returns the branches in a city that match the keyword and filters, with cursor pagination for lazy loading. "
    "OR semantics with results ranked by number of matched terms (Decision D-03).", "Search and catalogue", "search:read",
    search_params, None,
    {**ok("Matching branches.", ref("SearchProvidersResponse"), {"mediumFts": ex(SEARCH_RESP, "Medium FTS, OR semantics (CP-SEARCH-M01 example)")}),
     "400": err_resp("Validation error, city outside the sub-region, or invalid cursor.",
                     {"cityOutsideSubregion": ex(err("CITY_OUTSIDE_SUBREGION", "Paris is not served by this squad.")),
                      "invalidCursor": ex(err("INVALID_CURSOR", "The cursor is invalid or expired."))}),
     **std_errors("401", "403", "429", "503")},
    "rs.search.request.v1 (type=SEARCH_PROVIDERS) -> rs.search.response.v1 (type=SEARCH_PROVIDERS_RESULT)",
    "PP-SEARCH-S01, S02, M01, M02, U01, U02; CP-SEARCH-S01, S02, M01, M02")}

BRANCH_DETAILS = {"branch": BRANCH, "description": "Family-run homestay on the Thu Bon river, 5 minutes' walk to the Ancient Town.",
                  "imageUrls": ["https://cdn.roomscanner.local/branches/250/1.webp"], "checkInTime": "14:00", "checkOutTime": "12:00",
                  "latestComments": [{"reviewId": IDS["review"], "overallScore": 5, "text": "Lovely hosts and a great breakfast.", "createdAt": "2026-10-02T08:00:00Z"}]}
pp_paths["/branches/{branchId}"] = {"get": op(
    "getBranchDetails", "PP-OP-02", "Get branch details", "Public profile of one branch with its rating summary and latest comments sourced from CP.",
    "Search and catalogue", "search:read", [path_param("branchId", "Branch ID"), P("CheckInDate"), P("CheckOutDate")], None,
    {**ok("Branch details.", ref("BranchDetails"), {"default": ex(BRANCH_DETAILS)}), **std_errors("400", "401", "403", "404", "429", "503")},
    "rs.search.request.v1 (type=GET_BRANCH) -> rs.search.response.v1 (type=GET_BRANCH_RESULT)", "PP-SEARCH-S02; CP-SEARCH-S03")}

pp_paths["/branches/{branchId}/rooms"] = {"get": op(
    "listBranchRooms", "PP-OP-03", "List branch rooms", "Available room listings of a selected branch: name, available quantity, price per night and images.",
    "Search and catalogue", "search:read",
    [path_param("branchId", "Branch ID"), P("CheckInDate"), P("CheckOutDate"),
     {"name": "rooms", "in": "query", "required": False, "schema": i(minimum=1, default=1)},
     {"name": "roomType", "in": "query", "required": False, "style": "form", "explode": True, "schema": arr(ref("RoomType"))},
     {"name": "amenities", "in": "query", "required": False, "style": "form", "explode": True, "schema": arr(ref("Amenity"))},
     P("MembershipTierQuery"), P("Limit"), P("Cursor")], None,
    {**ok("Room listings.", ref("RoomListResponse"), {"default": ex({"items": [ROOM], "pageInfo": {"limit": 10, "hasMore": False}})}),
     **std_errors("400", "401", "403", "404", "429", "503")},
    "rs.search.request.v1 (type=LIST_ROOMS) -> rs.search.response.v1 (type=LIST_ROOMS_RESULT)", "PP-SEARCH-S03, PP-ROOM-U02; CP-SEARCH-S03")}

pp_paths["/rooms/{roomId}"] = {"get": op(
    "getRoomDetails", "PP-OP-04", "Get room details", "Full details of one active room. Archived rooms return 404 (PP-ROOM-S04).",
    "Search and catalogue", "search:read", [path_param("roomId", "Room ID"), P("CheckInDate"), P("CheckOutDate"), P("MembershipTierQuery")], None,
    {**ok("Room details.", ref("RoomDetail"), {"default": ex(ROOM_DETAIL)}), **std_errors("400", "401", "403", "404", "429", "503")},
    "rs.search.request.v1 (type=GET_ROOM) -> rs.search.response.v1 (type=GET_ROOM_RESULT)", "PP-ROOM-S05, S06; CP-SEARCH-S03")}

pp_paths["/quotes"] = {"post": op(
    "createPriceQuote", "PP-OP-05", "Create price quote",
    "PP calculates the price, applying the room's Premium discount policy after verifying membership with CP-OP-02, and holds the inventory for 15 minutes. "
    "CP charges exactly priceBreakdown.total (Decision D-06).", "Pricing and discounts", "quote:write", [P("IdempotencyKey")],
    body(ref("QuoteRequest"), {"premium": ex(QUOTE_REQ, "Premium customer, 2 rooms x 3 nights")}),
    {**ok("Quote created.", ref("Quote"), {"premium": ex(QUOTE)}, code="201"),
     **std_errors("400", "401", "403", "404", "429"),
     "409": err_resp("Not enough rooms available, or the Idempotency-Key was reused with a different body.",
                     {"insufficient": ex(err("INSUFFICIENT_AVAILABILITY", "Only 1 room is available for these dates.", availableQuantity=1)),
                      "idempotency": ex(err("IDEMPOTENCY_CONFLICT", "This Idempotency-Key was already used with a different request body."))}),
     "422": err_resp("Business rule violation.", {"quantity": ex(err("BOOKING_QUANTITY_EXCEEDS_GUESTS", "Requested room quantity (4) must not exceed adults + children (3).", [{"field": "quantity", "issue": "must be <= adults + children"}])),
                                                 "occupancy": ex(err("OCCUPANCY_EXCEEDED", "5 guests exceed the capacity of 2 rooms x 2 guests."))}),
     "503": err_resp("Service unavailable, or Premium membership could not be verified (fail closed).",
                     {"membership": ex(err("MEMBERSHIP_VERIFICATION_UNAVAILABLE", "Premium membership could not be verified. Retry or quote as Standard."))}, retry_after=True)},
    "rs.booking.request.v1 (type=CREATE_QUOTE) -> rs.booking.response.v1 (type=CREATE_QUOTE_RESULT)", "PP-DISCOUNT-S01, S02")}

pp_paths["/bookings"] = {"post": op(
    "createBooking", "PP-OP-06", "Create booking",
    "Stores the authoritative reservation as PENDING_APPROVAL and reserves the rooms with no automatic expiry. At Medium and Ultimo PP verifies the "
    "captured payment directly with the gateway. Durable replay checks precede quote expiry checks. The quote must belong to the customer; "
    "quote, CP order and gateway payment may bind to only one booking. Re-verify Premium eligibility at creation (D-06). "
    "Terminal rejection after a captured, unbound payment carries refundRequiredByPayer=true (D-14); ambiguous timeouts and already-bound payments do not. "
    "Served by the primary or redundant booking instance (PP-BOOK-U01); the Idempotency-Key makes retries after failover safe.",
    "Bookings", "booking:write", [P("IdempotencyKey")],
    body(ref("CreateBookingRequest"), {"escrow": ex(BOOK_REQ, "Ultimo escrow payment")}),
    {**ok("Booking created.", ref("Booking"), {"escrow": ex(BOOKING)}, code="201"),
     **std_errors("400", "401", "403", "429"),
     "409": err_resp("Quote expired/mismatched/consumed, eligibility changed, availability lost, or duplicate business identity.",
                     {"quoteExpired": ex(err("QUOTE_EXPIRED", "The price quote has expired. Request a new quote.", refundRequiredByPayer=True)),
                      "eligibilityChanged": ex(err("MEMBERSHIP_ELIGIBILITY_CHANGED", "Premium eligibility changed before booking creation. Request a new quote.", refundRequiredByPayer=True)),
                      "quoteMismatch": ex(err("QUOTE_MISMATCH", "The booking dates do not match the quote. Request a new quote.", refundRequiredByPayer=True)),
                      "insufficient": ex(err("INSUFFICIENT_AVAILABILITY", "The held rooms are no longer available.", refundRequiredByPayer=True)),
                      "paymentBound": ex(err("PAYMENT_ALREADY_BOUND", "The payment is already bound to a booking. Reconcile the CP order; do not refund it automatically.", refundRequiredByPayer=False)),
                      "orderBound": ex(err("ORDER_ALREADY_BOUND", "This CP order is already bound to a booking. Reconcile it with PP-OP-08 (orderId).", refundRequiredByPayer=False)),
                      "quoteConsumed": ex(err("QUOTE_ALREADY_CONSUMED", "This quote was already used by another booking.", refundRequiredByPayer=False)),
                      "idempotency": ex(err("IDEMPOTENCY_CONFLICT", "This Idempotency-Key was used with a different request body.", refundRequiredByPayer=False))}),
     "422": err_resp("Business rule or payment verification failure.",
                     {"quantity": ex(err("BOOKING_QUANTITY_EXCEEDS_GUESTS", "Requested room quantity (4) must not exceed adults + children (3).", [{"field": "quantity", "issue": "must be <= adults + children"}], refundRequiredByPayer=True)),
                      "occupancy": ex(err("OCCUPANCY_EXCEEDED", "5 guests exceed the capacity of 2 rooms x 2 guests.", refundRequiredByPayer=True)),
                      "notCaptured": ex(err("PAYMENT_NOT_CAPTURED", "PaymentIntent pi_3QAbCdTEST0001 has no successful capture to return.", refundRequiredByPayer=False)),
                      "referenceMismatch": ex(err("PAYMENT_REFERENCE_MISMATCH", "chargeReference does not belong to the submitted PaymentIntent.", refundRequiredByPayer=False)),
                      "amountMismatch": ex(err("PAYMENT_AMOUNT_MISMATCH", "Paid amount 12000 does not equal the quote total 12750.", refundRequiredByPayer=True))}),
     "503": R("ServiceUnavailable")},
    "rs.booking.request.v1 (type=CREATE_BOOKING, key customerId) -> rs.booking.response.v1 (type=CREATE_BOOKING_RESULT)",
    "PP-BOOK-S01, S02, U01, PP-MONEY-M01, U01; CP-BOOK-S01, S02, CP-MONEY-M01, U01, U04")}

cust_q = {"name": "customerId", "in": "query", "required": True, "description": "Must own the booking.", "schema": uuid()}
pp_paths["/bookings/{bookingId}"] = {"get": op(
    "getBooking", "PP-OP-07", "Get booking", "Current authoritative state of one booking, so CP can reconcile with PP (CP-MONEY-U02). "
    "A booking not owned by customerId returns 404 so its existence is not disclosed.", "Bookings", "booking:read",
    [path_param("bookingId", "Booking ID"), cust_q], None,
    {**ok("Booking.", ref("BookingSummary"), {"default": ex(SUMMARY)}), **std_errors("400", "401", "403", "404", "429", "503")},
    "rs.booking.request.v1 (type=GET_BOOKING) -> rs.booking.response.v1 (type=GET_BOOKING_RESULT)", "PP-MONEY-M03; CP-MONEY-U02")}

pp_paths["/customers/{customerId}/bookings"] = {"get": op(
    "listCustomerBookings", "PP-OP-08", "List customer bookings", "Data for CP's three booking groups (CP-BOOK-S02, Decision D-09). "
    "An unknown customer returns 200 with an empty list. Optional orderId is an exact CP-order lookup for reconciling an ambiguous create timeout.", "Bookings", "booking:read",
    [path_param("customerId", "CP customer ID"),
     {"name": "orderId", "in": "query", "required": False, "description": "Exact original CP order ID; a committed matching booking is returned even after quote/cache expiry.", "schema": uuid()},
     {"name": "status", "in": "query", "required": False, "style": "form", "explode": True, "schema": arr(ref("BookingStatus"))},
     {"name": "stayFrom", "in": "query", "required": False, "description": "Filter on checkInDate", "schema": date()},
     {"name": "stayTo", "in": "query", "required": False, "description": "Filter on checkInDate", "schema": date()},
     {"name": "sort", "in": "query", "required": False, "schema": enum(["CHECK_IN_DESC", "CREATED_DESC"], "Sort order")},
     P("Limit"), P("Cursor")], None,
    {**ok("Bookings.", ref("BookingListResponse"), {"default": ex({"items": [CONFIRMED], "pageInfo": {"limit": 10, "hasMore": False}})}),
     **std_errors("400", "401", "403", "429", "503")},
    "rs.booking.request.v1 (type=LIST_BOOKINGS) -> rs.booking.response.v1 (type=LIST_BOOKINGS_RESULT)", "CP-BOOK-S02")}

pp_paths["/bookings/{bookingId}/cancellations"] = {"post": op(
    "cancelBookingByCustomer", "PP-OP-09", "Cancel booking (customer)",
    "Cancels the booking, releases the rooms immediately and starts the money return (Medium payout, Ultimo refund). "
    "The final return outcome arrives later as a RETURN_PAYMENT_UPDATED event (PP-OP-11).", "Bookings", "booking:write",
    [path_param("bookingId", "Booking ID"), P("IdempotencyKey")],
    body(ref("CancelBookingRequest"), {"default": ex({"customerId": IDS["customer"], "reason": "Change of travel plans"})}),
    {**ok("Booking cancelled.", ref("BookingSummary"), {"default": ex(CANCELLED)}),
     **std_errors("400", "401", "403", "404", "429", "503"),
     "409": err_resp("Booking already final, cancellation window closed (Decision D-08), or Idempotency-Key reused with a different body.",
                     {"state": ex(err("STATE_CONFLICT", "The booking is already CANCELLED.")),
                      "window": ex(err("CANCELLATION_WINDOW_CLOSED", "Customers can cancel only before the check-in date.")),
                      "idempotency": ex(err("IDEMPOTENCY_CONFLICT", "This Idempotency-Key was already used with a different request body."))})},
    "rs.booking.request.v1 (type=CANCEL_BOOKING, key bookingId) -> rs.booking.response.v1 (type=CANCEL_BOOKING_RESULT)",
    "PP-BOOK-S02, PP-MONEY-S01, M02; CP-MONEY-M03, U03")}

pp_paths["/bookings/{bookingId}/review-eligibility"] = {"get": op(
    "getReviewEligibility", "PP-OP-10", "Get review eligibility",
    "Whether the customer may review the provider for this booking: status CONFIRMED or COMPLETED, owned by the customer, and today on or after "
    "the first day of the stay (Decision D-10).", "Bookings", "booking:read",
    [path_param("bookingId", "Booking ID"), cust_q], None,
    {**ok("Eligibility.", ref("ReviewEligibility"), {"beforeStay": ex(ELIG, "Pre-stay request is not eligible")}),
     **std_errors("400", "401", "403", "404", "429", "503")},
    "rs.booking.request.v1 (type=GET_ELIGIBILITY) -> rs.booking.response.v1 (type=GET_ELIGIBILITY_RESULT)",
    "PP-BOOK-S01, PP-RATING-S01; CP-RATING-S01")}

pp_paths["/event-suggestions"] = {"post": op(
    "requestEventSuggestions", "PP-OP-12", "Request event suggestions",
    "Returns the two most highly rated providers in the city of a favorited event (Decision D-12). Simplex binding. "
    "At Medium the same bodies travel over STOMP/WebSocket (see PP-06 markdown); at Ultimo PP-OP-13 replaces this.",
    "Regional events", "event-suggestion:write", None,
    body(ref("EventSuggestionRequest"), {"default": ex(EVSUG_REQ)}),
    {**ok("Suggestions.", ref("EventSuggestionResponse"), {"default": ex(EVSUG_RESP)}), **std_errors("400", "401", "403", "429", "503")},
    None, "PP-EVENT-S01, S02, M01; CP-EVENT-M02, M03")}

pp_doc = {
    "openapi": "3.0.3",
    "info": info("RoomScanner Provider Portal - Partner API", """
REST API that the **Provider Portal (PP)** (*Microservices architecture*, `BE-U01` to `BE-U09`) provides to the **Customer Portal (CP)** (*Modular Monolith architecture*, `BE-M01` to `BE-M08`).
This file is the machine-readable form of `provider-portal/PP-01` to `PP-06` in the squad API contract; the markdown
documents remain the source for business rules (`common/03-agreed-decisions.md`).

* Simplex: REST, a standalone mock of the partner is allowed (INT-S01, INT-S02).
* Medium: REST against the real partner with partner authentication (INT-M01 to INT-M03).
* Ultimo: the same payloads are exchanged over Kafka (see `specs/asyncapi/roomscanner-kafka.yaml`).

PP pushes booking status changes to CP through CP's webhook (`POST /booking-events` in the Customer Portal specification) at Simplex and Medium,
and through the `rs.booking.events.v1` topic at Ultimo.
"""),
    "servers": servers(8080, "pp-gateway", "Deployed (PP Microservices via PP API Gateway + Service Discovery on Machine 4)"),
    "tags": [
        {"name": "Partner authentication", "description": "Client-credentials token for partner calls (INT-M03)"},
        {"name": "Search and catalogue", "description": "PP-01: authoritative search and room catalogue"},
        {"name": "Pricing and discounts", "description": "PP-02: Premium discount pricing and inventory hold"},
        {"name": "Bookings", "description": "PP-03: reservations (primary resource)"},
        {"name": "Regional events", "description": "PP-06: event suggestions"},
    ],
    "paths": pp_paths,
    "components": {"parameters": COMMON_PARAMS, "responses": STD_RESPONSES, "securitySchemes": security_schemes(PP_SCOPES), "schemas": {}},
}

# ---------------------------------------------------------------- CP OpenAPI
CP_SCOPES = {"rating:read": "CP-OP-01", "membership:read": "CP-OP-02", "order:write": "CP-OP-03", "booking-event:write": "CP-OP-04"}
cp_paths = {"/auth/token": token_op(TOKEN_REQ_PP, TOKEN_RESP(["rating:read", "membership:read"]))}
cp_paths["/providers/{providerId}/rating-statistics"] = {"get": op(
    "getRatingStatistics", "CP-OP-01", "Get rating statistics",
    "Provider-level statistics calculated by CP. On demand only; no rating-change push. A provider with no reviews returns 200 with totalReviews 0. "
    "CP routes the request to the single shard holding the provider's reviews (CP-RATING-U02).", "Ratings", "rating:read",
    [path_param("providerId", "Accommodation provider ID"),
     {"name": "include", "in": "query", "required": False, "style": "form", "explode": True, "schema": arr(ref("StatisticsScope"))},
     {"name": "commentsLimit", "in": "query", "required": False, "schema": i(minimum=1, maximum=50, default=10)},
     {"name": "commentsCursor", "in": "query", "required": False, "schema": s()}], None,
    {**ok("Statistics.", ref("RatingStatistics"), {"default": ex(STATS)}), **std_errors("400", "401", "403", "429", "503")},
    "rs.rating-stats.request.v1 (type=GET_RATING_STATISTICS) -> rs.rating-stats.response.v1 (type=GET_RATING_STATISTICS_RESULT)",
    "PP-RATING-S01, M01, U01, U02; CP-RATING-M03, U01, U02")}
cp_paths["/customers/{customerId}/membership"] = {"get": op(
    "getCustomerMembership", "CP-OP-02", "Get customer membership", "Current membership of a customer. PP fails closed: no discount without verification.",
    "Membership", "membership:read", [path_param("customerId", "CP customer ID")], None,
    {**ok("Membership.", ref("Membership"), {"default": ex(MEMBER)}), **std_errors("400", "401", "403", "404", "429", "503")},
    "rs.membership.request.v1 (type=GET_MEMBERSHIP) -> rs.membership.response.v1 (type=GET_MEMBERSHIP_RESULT)", "PP-DISCOUNT-S02")}
cp_paths["/orders/{orderId}"] = {"patch": op(
    "updateSimulatedOrder", "CP-OP-03", "Complete or cancel simulated order", "Simplex only. PP completes or cancels the simulated order issued by CP.",
    "Orders", "order:write", [path_param("orderId", "CP order ID"), P("IdempotencyKey")],
    body(ref("UpdateOrderRequest"), {"complete": ex({"action": "COMPLETE", "bookingId": IDS["booking"]})}),
    {**ok("Order updated.", ref("Order"), {"default": ex({"orderId": IDS["order"], "status": "COMPLETED", "bookingId": IDS["booking"], "updatedAt": "2026-12-01T09:15:41Z"})}),
     **std_errors("400", "401", "403", "404", "429", "503"),
     "409": err_resp("Order already final with a different action.", {"state": ex(err("STATE_CONFLICT", "The order is already CANCELLED."))})},
    None, "PP-MONEY-S01; CP-MONEY-S01")}
cp_paths["/booking-events"] = {"post": op(
    "receiveBookingEvent", "CP-OP-04", "Receive booking status event (webhook)",
    "Webhook that PP calls for every booking transition (PP-OP-11). CP acknowledges within 5 s and does email and socket work asynchronously. "
    "CP de-duplicates on eventId. The X-RS-Signature header carries t=<unixSeconds>,v1=HMAC-SHA256(secret, t + '.' + rawBody); "
    "requests older than 300 s are rejected.", "Booking events", "booking-event:write", None,
    body(ref("BookingStatusEvent"), {"confirmed": ex(BOOKING_EVENT, "Booking confirmed, escrow released")}),
    {**ok("Event accepted.", ref("BookingEventAck"), {"default": ex({"eventId": BOOKING_EVENT["eventId"], "accepted": True, "duplicate": False})}),
     **std_errors("400", "401", "429", "503")},
    "replaced by rs.booking.events.v1 (PP -> CP)", "PP-MONEY-S01, M03; CP-MONEY-S01, M02",
    security=[{"partnerBearer": [], "webhookSignature": []}])}

cp_doc = {
    "openapi": "3.0.3",
    "info": info("RoomScanner Customer Portal - Partner API", """
REST API that the **Customer Portal (CP)** (*Modular Monolith architecture*, `BE-M01` to `BE-M08`) provides to the **Provider Portal (PP)** (*Microservices architecture*, `BE-U01` to `BE-U09`).
This file is the machine-readable form of `customer-portal/CP-01` to `CP-04` (indexed in `customer-portal/CP-services-required-by-PP.md`). CP owns these operations and has reviewed and confirmed this specification.
Within CP's Modular Monolith, `PartnerIntegrationModule` dispatches requests in-process via external service interfaces (`IRatingExternalService`, `IEventExternalService`, `IBookingExternalService`).
At Ultimo the same payloads are exchanged over Kafka (see `specs/asyncapi/roomscanner-kafka.yaml`), with a second instance of the CP modular monolith whose rating consumer also joins group `cp-rating-service`.
"""),
    "servers": servers(9080, "cp-api", "Deployed (CP Modular Monolith, single deployable; no API Gateway; served by PartnerIntegrationModule)"),
    "tags": [
        {"name": "Partner authentication", "description": "Client-credentials token for partner calls (INT-M03)"},
        {"name": "Ratings", "description": "CP-owned review statistics"},
        {"name": "Membership", "description": "Customer Premium membership"},
        {"name": "Orders", "description": "Simplex simulated payment orders"},
        {"name": "Booking events", "description": "Webhook receiving PP booking status events"},
    ],
    "paths": cp_paths,
    "components": {"parameters": COMMON_PARAMS, "responses": STD_RESPONSES, "schemas": {},
                   "securitySchemes": {**security_schemes(CP_SCOPES),
                                       "webhookSignature": {"type": "apiKey", "in": "header", "name": "X-RS-Signature",
                                                            "description": "HMAC-SHA256 webhook signature (01-conventions.md Section 4.3)"}}},
}

for d in (pp_doc, cp_doc):
    prune_schemas(d)
    # drop unused parameters
    text = json.dumps(d["paths"])
    d["components"]["parameters"] = {k: v for k, v in d["components"]["parameters"].items() if f"#/components/parameters/{k}" in text}


# ---------------------------------------------------------------- AsyncAPI 3.0 (Provider Portal view)
REQUEST_PAYLOADS = {
    "SEARCH_PROVIDERS": "SearchProvidersRequest", "GET_BRANCH": "GetBranchRequest",
    "LIST_ROOMS": "ListRoomsRequest", "GET_ROOM": "GetRoomRequest",
    "CREATE_QUOTE": "QuoteRequest", "CREATE_BOOKING": "CreateBookingRequest",
    "GET_BOOKING": "GetBookingRequest", "LIST_BOOKINGS": "ListBookingsRequest",
    "CANCEL_BOOKING": "CancelBookingCommand", "GET_ELIGIBILITY": "GetEligibilityRequest",
    "GET_RATING_STATISTICS": "RatingStatisticsRequest", "GET_MEMBERSHIP": "MembershipRequest",
}
RESPONSE_PAYLOADS = {
    "SEARCH_PROVIDERS_RESULT": "SearchProvidersResponse", "GET_BRANCH_RESULT": "BranchDetails",
    "LIST_ROOMS_RESULT": "RoomListResponse", "GET_ROOM_RESULT": "RoomDetail",
    "CREATE_QUOTE_RESULT": "Quote", "CREATE_BOOKING_RESULT": "Booking",
    "GET_BOOKING_RESULT": "BookingSummary", "LIST_BOOKINGS_RESULT": "BookingListResponse",
    "CANCEL_BOOKING_RESULT": "BookingSummary", "GET_ELIGIBILITY_RESULT": "ReviewEligibility",
    "GET_RATING_STATISTICS_RESULT": "RatingStatistics", "GET_MEMBERSHIP_RESULT": "Membership",
}
BOOKING_EVENT_TYPES = ["BOOKING_CONFIRMED", "BOOKING_CANCELLED", "BOOKING_COMPLETED",
                       "RETURN_PAYMENT_UPDATED", "ESCROW_RELEASE_UPDATED"]
FAVORITE_EVENT_TYPES = ["FAVORITE_ADDED", "FAVORITE_REMOVED", "EVENT_DATES_CHANGED", "EVENT_DELETED"]
MUTATING_REQUESTS = {"CREATE_QUOTE", "CREATE_BOOKING", "CANCEL_BOOKING"}


def request_policy(type_):
    if type_ in MUTATING_REQUESTS:
        return "rs.booking.response.v1", "CP", 45
    if type_ == "GET_RATING_STATISTICS":
        return "rs.rating-stats.response.v1", "PP", 20
    if type_ == "GET_MEMBERSHIP":
        return "rs.membership.response.v1", "PP", 12
    if type_ in {"SEARCH_PROVIDERS", "GET_BRANCH", "LIST_ROOMS", "GET_ROOM"}:
        return "rs.search.response.v1", "CP", 12
    return "rs.booking.response.v1", "CP", 12


_example_counter = iter(range(1, 1000))
_request_examples = {}


def env_example(type_, source, payload, reply_to=None, correlation=None, status=None,
                ts="2026-12-01T03:00:00Z", mid=None):
    k = next(_example_counter)
    request = _request_examples.get(type_.removesuffix("_RESULT")) if status else None
    correlation = correlation or (request["correlationId"] if request else f"c0ffee00-0000-4000-8000-{k:012x}")
    mid = mid or f"e1a2b3c4-0000-4000-8000-{k:012x}"
    e = {"messageId": mid, "correlationId": correlation, "traceId": IDS["trace"],
         "type": type_, "schemaVersion": "1.0", "source": source}
    if reply_to:
        deadline = datetime.fromisoformat(ts.replace("Z", "+00:00")) + timedelta(seconds=request_policy(type_)[2])
        e.update({"replyTo": reply_to, "attempt": 1, "deadline": deadline.isoformat().replace("+00:00", "Z")})
        if type_ in MUTATING_REQUESTS:
            e["idempotencyKey"] = correlation
        _request_examples[type_] = e
    e["timestamp"] = ts
    if status:
        e["status"] = status
        if not request:
            raise ValueError(f"Response example has no request example: {type_}")
        e["causationId"] = request["messageId"]
        if e["correlationId"] != request["correlationId"]:
            raise ValueError(f"Response example correlation mismatch: {type_}")
    e["payload"] = payload
    return e


def envelope_schema(types, payload_refs, desc):
    branches = []
    for type_ in types:
        properties = {"type": {"enum": [type_]}}
        required = []
        if type_ in REQUEST_PAYLOADS:
            reply, source, _ = request_policy(type_)
            assert REQUEST_PAYLOADS[type_] in payload_refs
            properties.update({"source": {"enum": [source]}, "replyTo": {"enum": [reply]},
                               "payload": ref(REQUEST_PAYLOADS[type_])})
            required = ["replyTo", "attempt", "deadline"]
            forbidden = ["status"]
            if type_ in MUTATING_REQUESTS:
                required.append("idempotencyKey")
            else:
                forbidden.append("idempotencyKey")
            branches.append(obj(properties, required, **absent(*forbidden)))
        elif type_ in RESPONSE_PAYLOADS:
            assert RESPONSE_PAYLOADS[type_] in payload_refs
            source = "CP" if request_policy(type_.removesuffix("_RESULT"))[1] == "PP" else "PP"
            for status in ["OK", "ERROR"]:
                payload = ({"allOf": [ref(RESPONSE_PAYLOADS[type_]), absent("error")]} if status == "OK" else
                           {"allOf": [ref("Error"), obj({"error": obj({"httpStatus": i(minimum=400, maximum=599)}, ["httpStatus"])})]})
                branches.append(obj({**properties, "source": {"enum": [source]},
                                     "status": {"enum": [status]}, "payload": payload},
                                    ["status", "causationId"], **absent("replyTo", "attempt", "deadline", "idempotencyKey")))
        else:
            if type_ in BOOKING_EVENT_TYPES:
                payload = {"allOf": [ref("BookingStatusEvent"), obj({"eventType": {"enum": [type_]}})]}
                source = "PP"
            elif type_ in FAVORITE_EVENT_TYPES:
                payload = {"allOf": [ref("EventFavoriteChanged"), obj({"changeType": {"enum": [type_]}})]}
                source = "CP"
            elif type_ == "REGIONAL_EVENT_NOTIFICATION":
                payload, source = ref("RegionalEventNotification"), "PP"
            else:
                raise ValueError(f"Unknown Kafka message type: {type_}")
            branches.append(obj({**properties, "source": {"enum": [source]}, "payload": payload},
                                **absent("replyTo", "attempt", "deadline", "status", "idempotencyKey")))
    return {"allOf": [ref("KafkaEnvelope"), {"oneOf": branches}], "description": desc}


def message(name, title, summary, types, payload_refs, key_desc, examples):
    return {
        "name": name, "title": title, "summary": summary, "contentType": "application/json",
        "correlationId": {"$ref": "#/components/correlationIds/envelopeCorrelation"},
        "payload": envelope_schema(types, payload_refs, summary),
        "bindings": {"kafka": {"key": s(key_desc), "bindingVersion": "0.5.0"}},
        "examples": [{"name": n, "payload": p} for n, p in examples],
    }


A_MSG = {
    "SearchRequest": message("SearchRequest", "Search request", "CP asks PP for search or catalogue data (PP-OP-01 to PP-OP-04).",
                             ["SEARCH_PROVIDERS", "GET_BRANCH", "LIST_ROOMS", "GET_ROOM"],
                             ["SearchProvidersRequest", "GetBranchRequest", "ListRoomsRequest", "GetRoomRequest"], "correlationId",
                             [("searchProviders", env_example("SEARCH_PROVIDERS", "CP", {"city": "Hoi An", "country": "VN", "q": "Single Bed Free WiFi Homestay", "limit": 10}, "rs.search.response.v1"))]),
    "SearchResponse": message("SearchResponse", "Search response", "PP answers a search request with the same correlationId.",
                              ["SEARCH_PROVIDERS_RESULT", "GET_BRANCH_RESULT", "LIST_ROOMS_RESULT", "GET_ROOM_RESULT"],
                              ["SearchProvidersResponse", "BranchDetails", "RoomListResponse", "RoomDetail", "Error"], "correlationId",
                              [("searchProvidersResult", env_example("SEARCH_PROVIDERS_RESULT", "PP", SEARCH_RESP, status="OK", mid="6b0e2a71-0000-4000-8000-00000000a101", ts="2026-12-01T03:00:01Z"))]),
    "BookingRequest": message("BookingRequest", "Booking request", "CP sends quote, booking, cancellation and booking-query requests (PP-OP-05 to PP-OP-10).",
                              ["CREATE_QUOTE", "CREATE_BOOKING", "GET_BOOKING", "LIST_BOOKINGS", "CANCEL_BOOKING", "GET_ELIGIBILITY"],
                              ["QuoteRequest", "CreateBookingRequest", "GetBookingRequest", "ListBookingsRequest", "CancelBookingCommand", "GetEligibilityRequest"],
                              "customerId for CREATE_QUOTE, CREATE_BOOKING and LIST_BOOKINGS; bookingId otherwise",
                              [("createBooking", env_example("CREATE_BOOKING", "CP", BOOK_REQ, "rs.booking.response.v1", correlation="a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8"))]),
    "BookingResponse": message("BookingResponse", "Booking response", "PP answers a booking request with the same correlationId.",
                               ["CREATE_QUOTE_RESULT", "CREATE_BOOKING_RESULT", "GET_BOOKING_RESULT", "LIST_BOOKINGS_RESULT", "CANCEL_BOOKING_RESULT", "GET_ELIGIBILITY_RESULT"],
                               ["Quote", "Booking", "BookingSummary", "BookingListResponse", "ReviewEligibility", "Error"], "same key as the request",
                               [("createBookingResult", env_example("CREATE_BOOKING_RESULT", "PP", BOOKING, status="OK", correlation="a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8", mid="6b0e2a71-0000-4000-8000-00000000a102", ts="2026-12-01T03:00:01Z")),
                                ("quoteExpired", env_example("CREATE_BOOKING_RESULT", "PP", {"error": {"code": "QUOTE_EXPIRED", "httpStatus": 409, "message": "The price quote has expired. Request a new quote.", "refundRequiredByPayer": True, "requestId": "e1a2b3c4-0000-4000-8000-00000000a001", "timestamp": "2026-12-01T03:00:01Z"}}, status="ERROR", correlation="a3f1b2c4-5d6e-4f70-8192-a3b4c5d6e7f8", mid="6b0e2a71-0000-4000-8000-00000000a103", ts="2026-12-01T03:00:01Z"))]),
    "BookingStatusEvent": message("BookingStatusEvent", "Booking status event", "PP publishes every booking transition (PP-OP-11).",
                                  ["BOOKING_CONFIRMED", "BOOKING_CANCELLED", "BOOKING_COMPLETED", "RETURN_PAYMENT_UPDATED", "ESCROW_RELEASE_UPDATED"],
                                  ["BookingStatusEvent"], "bookingId",
                                  [("confirmed", env_example("BOOKING_CONFIRMED", "PP", BOOKING_EVENT, correlation=IDS["booking"], mid="11112222-0000-4000-8000-0000000000e1", ts="2026-12-01T09:15:40Z"))]),
    "RatingStatisticsRequest": message("RatingStatisticsRequest", "Rating statistics request", "PP asks CP for provider statistics on demand (CP-OP-01).",
                                       ["GET_RATING_STATISTICS"], ["RatingStatisticsRequest"], "providerId",
                                       [("request", env_example("GET_RATING_STATISTICS", "PP", {"providerId": IDS["provider"], "include": ["OVERALL", "SUBCATEGORIES", "PRESET_OPTIONS", "COMMENTS"], "commentsLimit": 10}, "rs.rating-stats.response.v1", correlation="0c4a7d22-0000-4000-8000-00000000c0aa", mid="0c4a7d22-0000-4000-8000-00000000c001"))]),
    "RatingStatisticsResponse": message("RatingStatisticsResponse", "Rating statistics response", "CP answers with the same correlationId.",
                                        ["GET_RATING_STATISTICS_RESULT"], ["RatingStatistics", "Error"], "providerId",
                                        [("result", env_example("GET_RATING_STATISTICS_RESULT", "CP", STATS, status="OK", correlation="0c4a7d22-0000-4000-8000-00000000c0aa", mid="0c4a7d22-0000-4000-8000-00000000c002"))]),
    "MembershipRequest": message("MembershipRequest", "Membership request", "PP verifies a customer's membership (CP-OP-02).",
                                 ["GET_MEMBERSHIP"], ["MembershipRequest"], "customerId",
                                 [("request", env_example("GET_MEMBERSHIP", "PP", {"customerId": IDS["customer"]}, "rs.membership.response.v1"))]),
    "MembershipResponse": message("MembershipResponse", "Membership response", "CP answers with the same correlationId.",
                                  ["GET_MEMBERSHIP_RESULT"], ["Membership", "Error"], "customerId",
                                  [("result", env_example("GET_MEMBERSHIP_RESULT", "CP", MEMBER, status="OK", mid="6b0e2a71-0000-4000-8000-00000000a104"))]),
    "EventFavoriteChanged": message("EventFavoriteChanged", "Event favorite changed", "CP tells PP that a Premium customer favorited or unfavorited an event, or that its dates changed or it was deleted (CP-OP-05).",
                                    ["FAVORITE_ADDED", "FAVORITE_REMOVED", "EVENT_DATES_CHANGED", "EVENT_DELETED"], ["EventFavoriteChanged"], "eventId",
                                    [("added", env_example("FAVORITE_ADDED", "CP", {"changeType": "FAVORITE_ADDED", "favoriteId": "fa7e0000-0000-4000-8000-000000000b02", "customerId": "7d1e2f30-0000-4000-8000-000000000902", "favoritedAt": "2026-12-12T03:00:00Z", "event": EVENT},
                                                           correlation="fa7e0000-0000-4000-8000-000000000b02", mid="3e550000-0000-4000-8000-000000000d01", ts="2026-12-12T03:00:00Z"))]),
    "RegionalEventNotification": message("RegionalEventNotification", "Regional event notification", "PP publishes the top-2 suggestions for a favorited event at the agreed time (PP-OP-13).",
                                         ["REGIONAL_EVENT_NOTIFICATION"], ["RegionalEventNotification"], "customerId",
                                         [("scheduled", env_example("REGIONAL_EVENT_NOTIFICATION", "PP", {"notificationId": "40710000-0000-4000-8000-000000000f01", "favoriteId": "fa7e0000-0000-4000-8000-000000000b02", "customerId": "7d1e2f30-0000-4000-8000-000000000902", "trigger": "SCHEDULED_TWO_MONTH", "notificationWindowStart": "2027-02-11", "event": EVENT, "suggestions": SUGG, "searchLink": EVENT["searchRoute"], "publishedAt": "2027-02-10T17:00:00Z"},
                                                                    correlation="fa7e0000-0000-4000-8000-000000000b02", mid="3e550000-0000-4000-8000-000000000e01", ts="2027-02-10T17:00:00Z"))]),
}

# One example per message type (TW-U04 at Ultimo).
def _more(msg, items):
    A_MSG[msg]["examples"] += [{"name": n, "payload": pl} for n, pl in items]


_n = iter(range(0xb100, 0xb200))


def _req(type_, payload, reply):
    k = next(_n)
    return env_example(type_, "CP", payload, reply, correlation=f"c0ffee00-0000-4000-8000-00000000{k:04x}", mid=f"e1a2b3c4-0000-4000-8000-00000000{k:04x}")


def _res(type_, payload, status="OK"):
    k = next(_n)
    return env_example(type_, "PP", payload, status=status,
                       mid=f"6b0e2a71-0000-4000-8000-00000000{k:04x}", ts="2026-12-01T03:00:01Z")


_more("SearchRequest", [
    ("getBranch", _req("GET_BRANCH", {"branchId": IDS["branch"], "checkInDate": "2027-04-10", "checkOutDate": "2027-04-13"}, "rs.search.response.v1")),
    ("listRooms", _req("LIST_ROOMS", {"branchId": IDS["branch"], "checkInDate": "2027-04-10", "checkOutDate": "2027-04-13", "rooms": 2, "membershipTier": "PREMIUM", "limit": 10}, "rs.search.response.v1")),
    ("getRoom", _req("GET_ROOM", {"roomId": IDS["room"], "checkInDate": "2027-04-10", "checkOutDate": "2027-04-13", "membershipTier": "PREMIUM"}, "rs.search.response.v1")),
])
_more("SearchResponse", [
    ("getBranchResult", _res("GET_BRANCH_RESULT", BRANCH_DETAILS)),
    ("listRoomsResult", _res("LIST_ROOMS_RESULT", {"items": [ROOM], "pageInfo": {"limit": 10, "hasMore": False}})),
    ("getRoomResult", _res("GET_ROOM_RESULT", ROOM_DETAIL)),
])
_more("BookingRequest", [
    ("createQuote", _req("CREATE_QUOTE", QUOTE_REQ, "rs.booking.response.v1")),
    ("getBooking", _req("GET_BOOKING", {"bookingId": IDS["booking"], "customerId": IDS["customer"]}, "rs.booking.response.v1")),
    ("listBookings", _req("LIST_BOOKINGS", {"customerId": IDS["customer"], "status": ["PENDING_APPROVAL", "CONFIRMED", "COMPLETED"], "sort": "CHECK_IN_DESC", "limit": 10}, "rs.booking.response.v1")),
    ("cancelBooking", _req("CANCEL_BOOKING", {"bookingId": IDS["booking"], "customerId": IDS["customer"], "reason": "Change of travel plans"}, "rs.booking.response.v1")),
    ("getEligibility", _req("GET_ELIGIBILITY", {"bookingId": IDS["booking"], "customerId": IDS["customer"]}, "rs.booking.response.v1")),
])
_more("BookingResponse", [
    ("createQuoteResult", _res("CREATE_QUOTE_RESULT", QUOTE)),
    ("getBookingResult", _res("GET_BOOKING_RESULT", SUMMARY)),
    ("listBookingsResult", _res("LIST_BOOKINGS_RESULT", {"items": [CONFIRMED], "pageInfo": {"limit": 10, "hasMore": False}})),
    ("cancelBookingResult", _res("CANCEL_BOOKING_RESULT", CANCELLED)),
    ("getEligibilityResult", _res("GET_ELIGIBILITY_RESULT", ELIG)),
])
_more("BookingStatusEvent", [
    ("cancelledRefundPending", env_example("BOOKING_CANCELLED", "PP",
        {"eventId": "11112222-0000-4000-8000-000000000004", "eventType": "BOOKING_CANCELLED", "occurredAt": "2026-12-03T05:00:00Z",
         "sequence": 3, "booking": CANCELLED, "emailData": EMAIL},
        correlation=IDS["booking"], mid="11112222-0000-4000-8000-0000000000e4", ts="2026-12-03T05:00:00Z")),
    ("refundSucceeded", env_example("RETURN_PAYMENT_UPDATED", "PP",
        {"eventId": "11112222-0000-4000-8000-000000000005", "eventType": "RETURN_PAYMENT_UPDATED", "occurredAt": "2026-12-03T05:00:20Z",
         "sequence": 4, "booking": dict(CANCELLED, payment={"mode": "ESCROW", "originalPaymentReference": "pi_3QAbCdTEST0001", "escrowStatus": "REFUNDED",
                                                            "returnPaymentStatus": "SUCCEEDED", "returnPaymentReference": "re_3QAbCdTEST0001"})},
        correlation=IDS["booking"], mid="11112222-0000-4000-8000-0000000000e5", ts="2026-12-03T05:00:20Z")),
])

_more("BookingStatusEvent", [
    ("escrowReleased", env_example("ESCROW_RELEASE_UPDATED", "PP",
        {"eventId": "11112222-0000-4000-8000-000000000006", "eventType": "ESCROW_RELEASE_UPDATED", "occurredAt": "2026-12-01T09:15:45Z",
         "sequence": 3, "booking": CONFIRMED},
        correlation=IDS["booking"], mid="11112222-0000-4000-8000-0000000000e6", ts="2026-12-01T09:15:45Z")),
    ("completed", env_example("BOOKING_COMPLETED", "PP",
        {"eventId": "11112222-0000-4000-8000-000000000007", "eventType": "BOOKING_COMPLETED", "occurredAt": "2027-04-13T19:00:00Z",
         "sequence": 4, "booking": dict(CONFIRMED, status="COMPLETED", updatedAt="2027-04-13T19:00:00Z")},
        correlation=IDS["booking"], mid="11112222-0000-4000-8000-0000000000e7", ts="2027-04-13T19:00:00Z")),
])
_more("EventFavoriteChanged", [
    ("removed", env_example("FAVORITE_REMOVED", "CP", {"changeType": "FAVORITE_REMOVED", "favoriteId": "fa7e0000-0000-4000-8000-000000000b02",
                                                        "customerId": "7d1e2f30-0000-4000-8000-000000000902", "event": EVENT},
                            correlation="fa7e0000-0000-4000-8000-000000000b02", mid="3e550000-0000-4000-8000-000000000d02", ts="2027-01-05T03:00:00Z")),
    ("datesChanged", env_example("EVENT_DATES_CHANGED", "CP", {"changeType": "EVENT_DATES_CHANGED", "event": dict(EVENT, startDate="2027-04-14", endDate="2027-04-20")},
                                 correlation=IDS["event"], mid="3e550000-0000-4000-8000-000000000d03", ts="2027-01-06T03:00:00Z")),
    ("eventDeleted", env_example("EVENT_DELETED", "CP", {"changeType": "EVENT_DELETED", "event": EVENT},
                                 correlation=IDS["event"], mid="3e550000-0000-4000-8000-000000000d04", ts="2027-01-07T03:00:00Z")),
])

_more("BookingStatusEvent", [
    ("refundAfterTransferReversal", env_example("RETURN_PAYMENT_UPDATED", "PP", {
        "eventId": "11112222-0000-4000-8000-000000000008", "eventType": "RETURN_PAYMENT_UPDATED",
        "occurredAt": "2026-12-03T05:01:00Z", "sequence": 5,
        "booking": dict(CANCELLED, payment={
            "mode": "ESCROW", "orderId": IDS["order"], "originalPaymentReference": "pi_3QAbCdTEST0001",
            "escrowStatus": "REFUNDED", "releaseReference": "tr_1QXyzTEST0001",
            "transferReversalStatus": "SUCCEEDED", "transferReversalReference": "trr_1QXyzTEST0001",
            "returnPaymentStatus": "SUCCEEDED", "returnPaymentReference": "re_3QAbCdTEST0001",
        }, updatedAt="2026-12-03T05:01:00Z"),
    }, correlation=IDS["booking"], mid="11112222-0000-4000-8000-0000000000e8", ts="2026-12-03T05:01:00Z")),
])

TOPICS = [  # key, address, created by, producer->consumer, messages
    ("searchRequest", "rs.search.request.v1", "PP", "CP -> PP", ["SearchRequest"]),
    ("searchResponse", "rs.search.response.v1", "PP", "PP -> CP", ["SearchResponse"]),
    ("bookingRequest", "rs.booking.request.v1", "PP", "CP -> PP", ["BookingRequest"]),
    ("bookingResponse", "rs.booking.response.v1", "PP", "PP -> CP", ["BookingResponse"]),
    ("bookingEvents", "rs.booking.events.v1", "PP", "PP -> CP", ["BookingStatusEvent"]),
    ("ratingStatsRequest", "rs.rating-stats.request.v1", "CP", "PP -> CP", ["RatingStatisticsRequest"]),
    ("ratingStatsResponse", "rs.rating-stats.response.v1", "CP", "CP -> PP", ["RatingStatisticsResponse"]),
    ("membershipRequest", "rs.membership.request.v1", "CP", "PP -> CP", ["MembershipRequest"]),
    ("membershipResponse", "rs.membership.response.v1", "CP", "CP -> PP", ["MembershipResponse"]),
    ("eventFavorite", "rs.event.favorite.v1", "CP", "CP -> PP", ["EventFavoriteChanged"]),
    ("eventNotification", "rs.event.notification.v1", "CP", "PP -> CP", ["RegionalEventNotification"]),
]
channels = {}
for key, addr, creator, flow, msgs in TOPICS:
    channels[key] = {
        "address": addr, "title": addr,
        "description": f"{flow}. Topic created by {creator}. 6 partitions, replication factor 1, retention 7 days. "
                       f"Failed messages go to `{addr}.dlq` after 3 local retries.",
        "messages": {m[0].lower() + m[1:]: {"$ref": f"#/components/messages/{m}"} for m in msgs},
        "bindings": {"kafka": {"topic": addr, "partitions": 6, "replicas": 1,
                               "topicConfiguration": {"retention.ms": 604800000, "cleanup.policy": ["delete"]}, "bindingVersion": "0.5.0"}},
    }


def chmsg(ch):
    return [{"$ref": f"#/channels/{ch}/messages/{k}"} for k in channels[ch]["messages"]]


def aop(action, ch, title, desc, reply=None, group=None):
    o = {"action": action, "channel": {"$ref": f"#/channels/{ch}"}, "title": title, "description": desc, "messages": chmsg(ch)}
    if reply:
        o["reply"] = {"channel": {"$ref": f"#/channels/{reply}"}, "messages": chmsg(reply)}
    if group:
        o["bindings"] = {"kafka": {"groupId": enum([group], "Consumer group"), "bindingVersion": "0.5.0"}}
    return o


operations = {
    "serveSearchRequests": aop("receive", "searchRequest", "Serve search requests", "PP consumes search requests and replies on rs.search.response.v1 with the same correlationId (PP-SEARCH-U02, PP-ROOM-U02).", "searchResponse", "pp-search-service"),
    "serveBookingRequests": aop("receive", "bookingRequest", "Serve booking requests", "PP consumes quote/booking/cancellation requests. Both booking-service instances join the same consumer group, so Kafka fails over to the redundant instance (PP-BOOK-U01).", "bookingResponse", "pp-booking-service"),
    "publishBookingEvents": aop("send", "bookingEvents", "Publish booking status events", "PP publishes every booking transition through a transactional outbox (PP-OP-11)."),
    "requestRatingStatistics": aop("send", "ratingStatsRequest", "Request rating statistics", "PP requests provider statistics on demand and resends on timeout (PP-RATING-U01, U02, INT-U03). Served by CP's Modular Monolith RatingModule; a second monolith instance joins group cp-rating-service for redundancy (CP-RATING-U01).", "ratingStatsResponse"),
    "requestMembership": aop("send", "membershipRequest", "Request membership", "PP verifies Premium membership before applying a discount (Decision D-06). Served by CP's Modular Monolith EventModule (group cp-membership-service).", "membershipResponse"),
    "receiveEventFavorites": aop("receive", "eventFavorite", "Receive event favorite changes", "PP schedules or publishes regional event notifications (Decision D-12).", group="pp-event-service"),
    "publishEventNotifications": aop("send", "eventNotification", "Publish regional event notifications", "PP publishes to the CP-created topic; CP's dedicated consumer (group cp-event-notification-consumer) displays it to eligible Premium customers (PP-EVENT-U01, U02; CP-EVENT-U02)."),
}

async_doc = {
    "asyncapi": "3.0.0",
    "info": {
        "title": "RoomScanner Squad - Kafka Integration (PP Microservices <-> CP Modular Monolith)",
        "version": VERSION,
        "description": (
            "Kafka bindings of the squad API contract at Ultimo (INT-U01 to INT-U03). Provider Portal (PP) runs a Microservices "
            "architecture (BE-U01 to BE-U09), while Customer Portal (CP) runs a Modular Monolith architecture (BE-M01 to BE-M08) "
            "via PartnerIntegrationModule. Operations are described from the Provider Portal's point of view: `receive` operations "
            "are served by PP, `send` operations are produced by PP. The Customer Portal performs the mirror operation on each channel.\n\n"
            "Every message uses the envelope in `common/04-kafka.md` Section 1. Requests carry `replyTo`; responses copy the "
            "request's `correlationId` (INT-U02). A resend keeps the `correlationId`, gets a new `messageId` and increments `attempt` "
            "(INT-U03). Delivery is at-least-once and responders are idempotent."),
    },
    "defaultContentType": "application/json",
    "servers": {
        "squadBroker": {"host": "kafka.{squad}.roomscanner.local:9093", "protocol": "kafka-secure",
                        "description": "Squad Kafka broker on Machine 4 (DEP-U04). SASL_SSL with SCRAM-SHA-512; topic auto-creation disabled.",
                        "variables": {"squad": {"default": "squad", "description": "Squad identifier"}},
                        "security": [{"$ref": "#/components/securitySchemes/scram"}]},
    },
    "channels": channels,
    "operations": operations,
    "components": {
        "messages": A_MSG,
        "schemas": {},
        "correlationIds": {"envelopeCorrelation": {"description": "Request/response correlation (INT-U02)", "location": "$message.payload#/correlationId"}},
        "securitySchemes": {"scram": {"type": "scramSha512", "description": "Per-subsystem principals pp-svc and cp-svc with topic ACLs (04-kafka.md Section 6)."}},
    },
}
prune_schemas(async_doc)


# ---------------------------------------------------------------- write
class Dumper(yaml.SafeDumper):
    pass


def _str(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


Dumper.add_representer(str, _str)
Dumper.ignore_aliases = lambda *a: True

HEADER = "# Generated by tools/generate_specs.py from the shared schema set. Keep it consistent with the markdown contract;\n# change the generator and regenerate rather than editing this file by hand.\n"
out = {
    ROOT / "specs/openapi/provider-portal-partner-api.yaml": pp_doc,
    ROOT / "specs/openapi/customer-portal-partner-api.yaml": cp_doc,
    ROOT / "specs/asyncapi/roomscanner-kafka.yaml": async_doc,
}
for path, doc in out.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER + yaml.dump(doc, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    print("wrote", path.relative_to(ROOT), len(doc["components"]["schemas"]), "schemas")
