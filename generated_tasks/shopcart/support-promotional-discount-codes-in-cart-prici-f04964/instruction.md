# Support promotional discount codes in cart pricing

Introduce promotional coupon support to the pricing calculation module by defining `PricingError` and `DiscountCoupon`, adding a `discount` field to `Totals`, and updating `compute_totals` to validate coupons, apply clamped percentage and fixed discounts, and compute tax on the discounted subtotal proportionally distributed across cart line items.

## Background
Marketing and sales promotions require applying coupon codes at checkout to reduce cart totals through fixed dollar savings or percentage discounts. Cart calculations must adjust taxable line bases and order totals without allowing invalid coupons or negative totals.

## Requirements
1. Define exception `PricingError(Exception)` in `shopcart.pricing`.
2. Define dataclass `DiscountCoupon` in `shopcart.pricing` with fields: `code: str`, `discount_percent: Decimal = Decimal('0')`, `fixed_amount: Decimal = Decimal('0')`, and `min_subtotal: Decimal = Decimal('0')`. Convert any numeric inputs or default representations for monetary and percent fields such that calculations use `Decimal`.
3. Update `Totals` dataclass in `shopcart.pricing` to have fields `subtotal: Decimal`, `discount: Decimal`, `tax: Decimal`, `shipping: Decimal`, and `total: Decimal` in that exact positional order. If instantiated without `discount` positionally or if backwards compatibility is considered, `discount` must default to `Decimal('0.00')` (e.g., `discount: Decimal = Decimal('0.00')`), and `total` must equal `to_money(subtotal - discount + tax + shipping)`.
4. Update `compute_totals(cart: Cart, policy: PricingPolicy | None = None, coupon: DiscountCoupon | None = None) -> Totals` in `shopcart.pricing` to accept an optional `coupon` parameter defaulting to `None`.
5. If `coupon` is provided and `cart.subtotal` is strictly less than `coupon.min_subtotal`, raise `PricingError` with the message `f'cart subtotal {cart.subtotal} does not meet coupon minimum {coupon.min_subtotal}'`.
6. When a valid `coupon` is provided, calculate the raw discount amount as `percent_of(cart.subtotal, coupon.discount_percent) + to_money(coupon.fixed_amount)`. Clamp the final `discount` to `cart.subtotal` if the calculated raw discount exceeds `cart.subtotal`. If no coupon is provided, `discount` is `Decimal('0.00')`.
7. Shipping qualification (`cart.subtotal >= policy.free_shipping_threshold`) remains evaluated on original `cart.subtotal` as currently implemented in `compute_shipping(cart, policy)`.
8. Tax calculation with discounts: if `cart.subtotal` is `Decimal('0.00')` or `discount == cart.subtotal`, total tax is `Decimal('0.00')`. Otherwise, apportion the total discount across lines in proportion to each line's share of `cart.subtotal`: for each line, discounted line base is `line.line_total * (Decimal('1') - discount / cart.subtotal)`. Tax for the line is `percent_of(discounted_line_base, policy.tax_rate_for(line.product.category))`. Total tax is `to_money(sum(line_taxes))`.
9. When `coupon` is `None`, preserve existing pricing and tax calculation behavior where `discount` is `Decimal('0.00')`.

## Acceptance criteria
- **AC1**: Calling `compute_totals(cart, coupon=coupon)` where `cart.subtotal < coupon.min_subtotal` raises `PricingError`.
- **AC2**: Calling `compute_totals(cart, coupon=coupon)` with a valid percentage coupon calculates `discount = percent_of(cart.subtotal, coupon.discount_percent)` and reflects this in `Totals.discount`.
- **AC3**: A fixed amount discount or combined discount that exceeds `cart.subtotal` clamps `Totals.discount` to `cart.subtotal`, results in `Totals.tax == Decimal('0.00')`, and leaves `Totals.total == Totals.shipping`.
- **AC4**: For any cart and valid coupon (or no coupon), `Totals.total` precisely equals `to_money(Totals.subtotal - Totals.discount + Totals.tax + Totals.shipping)`.
- **AC5**: When `coupon` is `None`, calling `compute_totals(cart, policy)` produces `Totals` with `discount == Decimal('0.00')` and unchanged `subtotal`, `tax`, `shipping`, and `total`.

## Interface contract
Implement exactly these public names; automated checks use them.

- `shopcart.pricing` → **exception** `class PricingError(Exception)`  
  Raised when pricing operations fail, such as when a coupon does not meet the minimum subtotal requirement.
- `shopcart.pricing` → **class** `@dataclass(frozen=True)
class DiscountCoupon:
    code: str
    discount_percent: Decimal = Decimal('0')
    fixed_amount: Decimal = Decimal('0')
    min_subtotal: Decimal = Decimal('0')`  
  Represents a promotional discount coupon containing code, percentage discount, fixed dollar savings, and a minimum required subtotal threshold.
- `shopcart.pricing` → **class** `@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    discount: Decimal = Decimal('0.00')
    tax: Decimal = Decimal('0.00')
    shipping: Decimal = Decimal('0.00')
    total: Decimal = Decimal('0.00')`  
  Immutable value object holding the calculated monetary breakdown of a cart.
- `shopcart.pricing` → **function** `def compute_totals(cart: Cart, policy: PricingPolicy | None = None, coupon: DiscountCoupon | None = None) -> Totals`  
  Calculates subtotal, discount, tax, shipping, and total for a given cart, policy, and optional promotional coupon.

## Edge cases
- Subtotal exactly equals `min_subtotal`: coupon is valid and applied without raising `PricingError`.
- Empty cart with coupon: if `min_subtotal > Decimal('0')`, raises `PricingError`; if `min_subtotal == Decimal('0')`, discount is `Decimal('0.00')` and tax is `Decimal('0.00')`.
- Coupon with both `discount_percent` and `fixed_amount`: discount is the sum of `percent_of(cart.subtotal, coupon.discount_percent)` and `to_money(coupon.fixed_amount)`, clamped to `cart.subtotal`.
- Multiple items with different category tax rates: each line's tax is computed after scaling the line's total by `(1 - discount / cart.subtotal)`.

## Error handling
- Raise `PricingError` when `cart.subtotal < coupon.min_subtotal`.
- Maintain standard `CartError` or `ValueError` behavior for existing methods unchanged.

## Interaction with existing behaviour
- Order creation via `Order.place(cart, inventory, policy)` calls `compute_totals(cart, policy)` without a coupon, which must continue to function seamlessly with `Totals`' updated attributes.
- Order payment validation checks `amount == order.totals.total`, which now reflects `subtotal - discount + tax + shipping`.

## Constraints
- No new third-party dependencies.
- Do not modify existing tests.
- All monetary amounts in `Totals` must be quantized using `shopcart.money.to_money`.
- Do not modify or delete existing tests.
- Do not add new third-party dependencies.
- Keep all existing behaviour working.

## Out of scope
- Passing coupons to `Order.place` (only `compute_totals` needs the `coupon` argument).
- Persisting coupons to a database or external registry.
- Per-category or SKU-restricted coupons.
- Coupon usage counts or expiration dates.

## Environment
The repository (python) is in the current working directory. You may run the existing test suite to check your work.
