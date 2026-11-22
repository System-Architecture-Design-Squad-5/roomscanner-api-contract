# 02: Shared Types

Every operation references these types. Field types use JSON Schema names (`string`, `integer`, `number`, `boolean`, `object`, `array`).

## 1. Enumerations

### ProviderCategory (PP-ROOM-S06, PP §2.3)
| Value | Meaning |
|---|---|
| `RESORT` | Resort |
| `HOTEL` | Hotel |
| `MOTEL_HOSTEL` | Motel / Hostel |
| `HOMESTAY` | Homestay |

### RoomType (CP-SEARCH-S01)
| Value | Meaning |
|---|---|
| `BUNK_BED` | Bunk Bed |
| `SINGLE_TWIN_BED` | Single / Twin Bed |
| `DOUBLE_BED` | Double Bed |

### Amenity (unified service list, see Decision D-02)
| Value | Label | Source |
|---|---|---|
| `FREE_WIFI` | Free WiFi | PP-ROOM-S06, CP-SEARCH-S02 |
| `KITCHEN` | Kitchen | PP-ROOM-S06 |
| `WASHING_MACHINE` | Washing Machine | PP-ROOM-S06 |
| `PETS_ALLOWED` | Pets Allowed | PP-ROOM-S06 |
| `PRIVATE_BATHROOM` | Private Bathroom | CP-SEARCH-S02 |
| `AIR_CONDITIONING` | Air-conditioning | CP-SEARCH-S02 |
| `DISABLED_FACILITIES` | Facilities for Disabled Guests | CP-SEARCH-S02 |

### MembershipTier
`STANDARD`, `PREMIUM` (there is no other tier, per PP §2.8)

### MembershipStatus
`ACTIVE`, `EXPIRED`, `NONE`

### BookingStatus (PP is authoritative)
| Value | Meaning | Rooms reserved? |
|---|---|---|
| `PENDING_APPROVAL` | Created and paid (Medium+), waiting for the receptionist. No automatic expiry (PP-BOOK-S02). | yes |
| `CONFIRMED` | Approved by the receptionist | yes |
| `CANCELLED` | Cancelled by the customer or the receptionist | no (released) |
| `COMPLETED` | The stay's check-out date has passed for a confirmed booking (set by a nightly job) | n/a |

### CancelledBy
`CUSTOMER`, `RECEPTIONIST`

### PaymentMode (selected by integration level)
| Value | Level | Description |
|---|---|---|
| `SIMULATED` | Simplex | CP issues a simulated order. PP completes or cancels it (PP-MONEY-S01). |
| `DIRECT` | Medium | Direct customer-to-provider sandbox payment. The return is a separate provider payout (PP-MONEY-M01, M02). |
| `ESCROW` | Ultimo | Authorize → capture (held) → release on approval / refund on cancellation (PP-MONEY-U01) |

### PaymentGateway
`NONE` (simulated), `PAYPAL_SANDBOX`, `STRIPE_SANDBOX`. See Decision D-07.

### PaymentState (payer-side state reported by CP in the booking request)
| Value | Used with |
|---|---|
| `SIMULATED_ISSUED` | SIMULATED |
| `CAPTURED` | DIRECT |
| `CAPTURED_HELD` | ESCROW (captured into the platform's escrow balance, not yet released) |

### ReturnPaymentStatus (beneficiary-side outcome, PP-MONEY-M03)
| Value | Meaning |
|---|---|
| `NOT_REQUIRED` | Nothing to return (e.g. simulated order, or not yet paid) |
| `PENDING` | Payout or refund submitted, not yet final |
| `SUCCEEDED` | Money returned to the customer |
| `FAILED` | Gateway rejected the return. `failureCause` is filled. |

### EscrowReleaseStatus (Ultimo)
`HELD`, `RELEASE_PENDING`, `RELEASED`, `RELEASE_FAILED`, `REFUNDED`

### TransferReversalStatus (Ultimo)
`NOT_REQUIRED`, `PENDING`, `SUCCEEDED`, `FAILED`. Recovery of a released provider transfer is separate from the refund to the customer. After a successful reversal, funds are `HELD` while the refund is pending; a failed reversal leaves them `RELEASED`. See PP-05.

### DiscountType
| Value | Meaning |
|---|---|
| `PERCENTAGE` | `value` is a percentage, 1-100 |
| `FIXED_PER_NIGHT` | `value` is minor units off each room-night |

### StarGroup (rating preset options, CP-RATING-M02)
`ONE_TO_TWO`, `THREE`, `FOUR_TO_FIVE`

### RatingSubcategory
`SERVICE`, `FRIENDLINESS`, `ROOM`

## 2. Objects

### Money
| Field | Type | Required | Notes |
|---|---|---|---|
| amountMinor | integer | yes | Amount in minor units (cents). ≥ 0. |
| currency | string | yes | ISO-4217. The squad uses `USD` everywhere (matches the USD 100 Premium and USD 200 PMS prices). |

```json
{ "amountMinor": 9000, "currency": "USD" }
```

### Location
| Field | Type | Required | Notes |
|---|---|---|---|
| addressLine | string | yes | Public property address (branch), not a private account address |
| city | string | yes | Must be in the squad's sub-region (PP-ROOM-S01) |
| country | string | yes | ISO alpha-2 |
| timeZone | string | yes | IANA name, e.g. `Asia/Ho_Chi_Minh` |
| latitude / longitude | number | no | |

### RatingSummary (sourced from CP, cached by PP; PP never computes it)
| Field | Type | Required | Notes |
|---|---|---|---|
| overallAverage | number | no | 1.0-5.0, one decimal. Omitted when `totalReviews = 0`. |
| totalReviews | integer | yes | |
| source | string | yes | Always `"CP"` |
| asOf | string | yes | Timestamp of the CP statistics the value came from |

### ProviderSearchResult
The unit of a search result is a **branch** (one property at one address) of a provider, because one provider can operate branches in several cities (Decision D-04).

| Field | Type | Required | Notes |
|---|---|---|---|
| providerId | string | yes | |
| providerName | string | yes | Company name of the accommodation provider |
| branchId | string | yes | |
| branchName | string | yes | Property name shown to customers (e.g. "Sheraton Saigon") |
| category | ProviderCategory | yes | |
| logoUrl | string | yes | Resized logo (PP-PROFILE-M01) |
| location | Location | yes | |
| roomTypesOffered | RoomType[] | yes | Only types with active listings |
| amenities | Amenity[] | yes | Union of the amenities across active rooms |
| availableRoomCount | integer | yes | Sum of available quantity for the requested dates (0 if none) |
| lowestPricePerNight | Money | yes | Lowest base price across matching rooms |
| ratingSummary | RatingSummary | yes | |
| matchedFields | string[] | no | Medium FTS: which fields matched, e.g. `["providerName","category"]` |
| relevanceScore | number | no | Medium FTS rank, 0-1 |

### RoomSummary
| Field | Type | Required | Notes |
|---|---|---|---|
| roomId | string | yes | |
| branchId | string | yes | |
| name | string | yes | e.g. "Deluxe Double, City View" |
| roomType | RoomType | yes | |
| maxOccupancy | integer | yes | Guests per room |
| totalQuantity | integer | yes | Rooms of this listing |
| availableQuantity | integer | yes | For the requested dates (Decision D-05) |
| pricePerNight | Money | yes | Base price |
| premiumPricePerNight | Money | no | Present when a discount policy is assigned. Display only; the binding price comes from PP-OP-05. |
| amenities | Amenity[] | yes | |
| thumbnailUrl | string | yes | First image |
| imageUrls | string[] | yes | All images (PP-ROOM-S05) |

### RoomDetail
Everything in `RoomSummary`, plus:

| Field | Type | Required | Notes |
|---|---|---|---|
| description | string | yes | ≤ 2,000 characters |
| sizeSqm | number | no | |
| bedCount | integer | yes | |
| discountPolicy | DiscountPolicySummary | no | Present when a policy is assigned |
| provider | ProviderSearchResult | yes | Parent branch/provider summary |
| checkInTime / checkOutTime | string | yes | `HH:mm` local time |

### DiscountPolicySummary
| Field | Type | Required | Notes |
|---|---|---|---|
| discountPackageId | string | yes | |
| name | string | yes | e.g. "Premium Summer 15%" |
| type | DiscountType | yes | |
| value | integer | yes | Percentage (1-100) or minor units per night |
| eligibleTier | MembershipTier | yes | Always `PREMIUM` |
| active | boolean | yes | `false` once the program is cancelled |

### AppliedDiscount (snapshot stored on the booking)
| Field | Type | Required | Notes |
|---|---|---|---|
| discountPackageId | string | yes | |
| name | string | yes | |
| type | DiscountType | yes | |
| value | integer | yes | |
| amount | Money | yes | Total discount for the whole booking |

### PriceBreakdown
| Field | Type | Required | Notes |
|---|---|---|---|
| nights | integer | yes | checkOut − checkIn |
| quantity | integer | yes | Rooms |
| unitPricePerNight | Money | yes | Base price |
| subtotal | Money | yes | unit × nights × quantity |
| discount | AppliedDiscount | no | |
| total | Money | yes | subtotal − discount. **The exact amount CP must charge.** |

### CustomerSnapshot (sent by CP at booking time; only the fields PP needs)
| Field | Type | Required | Notes |
|---|---|---|---|
| customerId | string | yes | CP's application user ID |
| email | string | yes | Shown to the receptionist; used for PayPal payout (Medium) |
| phone | string | yes | E.164 |
| countryOfResidence | string | yes | ISO alpha-2 |

> Passport number and birthday are **not** shared (data minimisation, BE-M05).

### MembershipSnapshot
| Field | Type | Required | Notes |
|---|---|---|---|
| tier | MembershipTier | yes | |
| status | MembershipStatus | yes | |
| validUntil | string | no | UTC timestamp, present when `PREMIUM` |

### PaymentInfo (sent by CP with CreateBooking)
| Field | Type | Required | Notes |
|---|---|---|---|
| mode | PaymentMode | yes | |
| gateway | PaymentGateway | yes | |
| orderId | string | yes | CP order ID (payer-side) |
| paymentReference | string | yes (DIRECT/ESCROW) | PayPal capture ID, or Stripe PaymentIntent ID |
| chargeReference | string | ESCROW only | Stripe Charge ID (needed for the transfer `source_transaction` and for refunds) |
| state | PaymentState | yes | |
| amount | Money | yes | Must equal `quote.priceBreakdown.total` |
| paidAt | string | yes (DIRECT/ESCROW) | UTC timestamp |

The schemas enforce the payment-mode combinations: SIMULATED uses gateway `NONE` and state `SIMULATED_ISSUED` with no real-payment references/time; DIRECT uses `PAYPAL_SANDBOX` and `CAPTURED`, requiring payment reference and paid time; ESCROW uses `STRIPE_SANDBOX` and `CAPTURED_HELD`, requiring payment reference, charge reference and paid time. Empty references are invalid. Monetary equality, gateway ownership and metadata binding are backend validations in PP-03.

### BookingSummary
| Field | Type | Required | Notes |
|---|---|---|---|
| bookingId | string | yes | PP booking reference |
| bookingCode | string | yes | Short human code, e.g. `RS-VN-24F7Q` |
| status | BookingStatus | yes | |
| customerId | string | yes | |
| providerId / branchId / roomId | string | yes | |
| providerName / branchName / roomName | string | yes | |
| checkInDate / checkOutDate | string | yes | |
| quantity / adults / children | integer | yes | |
| priceBreakdown | PriceBreakdown | yes | |
| payment | BookingPaymentStatus | yes | |
| cancellation | CancellationInfo | no | Present when `CANCELLED` |
| createdAt / updatedAt | string | yes | |

### BookingPaymentStatus
| Field | Type | Required | Notes |
|---|---|---|---|
| mode | PaymentMode | yes | |
| orderId | string (uuid) | no | Original CP order ID retained for reconciliation |
| originalPaymentReference | string | DIRECT/ESCROW | Preserved after cancellation (PP-MONEY-M03) |
| escrowStatus | EscrowReleaseStatus | ESCROW | |
| releaseReference | string | no | Stripe Transfer ID once released |
| transferReversalStatus | TransferReversalStatus | when reversal is attempted | Separate transfer recovery outcome; absent means not required |
| transferReversalReference | string | on successful reversal | Stripe TransferReversal ID (`trr_...`), retained after refund |
| transferReversalFailureCause | string | on failed reversal | Gateway cause of transfer recovery failure; kept distinct from the customer refund cause |
| returnPaymentStatus | ReturnPaymentStatus | yes | |
| returnPaymentReference | string | no | PayPal payout batch/item ID, or Stripe Refund ID. Kept separate from the original. |
| failureCause | string | no | Gateway's failure reason when available |

### CancellationInfo
| Field | Type | Required | Notes |
|---|---|---|---|
| cancelledBy | CancelledBy | yes | |
| reason | string | no | ≤ 500 characters |
| cancelledAt | string | yes | |
