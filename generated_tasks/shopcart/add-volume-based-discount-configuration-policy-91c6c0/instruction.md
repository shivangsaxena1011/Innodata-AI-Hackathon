# Add volume-based discount configuration policy

Introduce a VolumeDiscountPolicy class that extends the existing pricing logic to allow bulk discounts. This policy will support multiple quantity tiers and apply the highest applicable discount to line items, rounding results to the nearest cent.

## Background
Wholesale customers frequently purchase items in bulk and expect price breaks based on volume. The current system calculates subtotal as a simple sum of (price * quantity), which makes it impossible to offer incentives for larger orders.

## Requirements
1. Create a new class VolumeDiscountPolicy that inherits from PricingPolicy in shopcart/pricing.py.
2. Implement an add_tier(min_quantity: int, discount_percent: Decimal | int | str) method to register discount thresholds.
3. The policy must apply the highest applicable discount tier for a given line item quantity. For example, if tiers exist for 5 and 10 units, a quantity of 12 should receive the 10% discount.
4. Update compute_tax to use the discounted line item totals when calculating taxes.
5. Update compute_totals to respect the new VolumeDiscountPolicy if provided as the policy argument.
6. All discounted amounts must be rounded to the nearest cent using the existing shopcart.money.to_money utility.
7. Discount calculation must use the logic: discounted_total = to_money(original_total * (1 - discount_percent / 100)).

## Acceptance criteria
- **AC1**: Given a VolumeDiscountPolicy with a tier (10 units, 10% discount), a cart with 10 units of a $10.00 item results in a subtotal of $90.00.
- **AC2**: Given a VolumeDiscountPolicy with tiers (5 units, 5%) and (10 units, 10%), a cart with 12 units of a $10.00 item results in a subtotal of $108.00 (10% off $120.00).
- **AC3**: Given a VolumeDiscountPolicy with a tier (10 units, 10%), a cart with 9 units of a $10.00 item results in a subtotal of $90.00 (no discount applied).
- **AC4**: Tax is calculated based on the discounted price. If a $100.00 line item is discounted to $90.00 and the tax rate is 10%, the tax is $9.00.
- **AC5**: Free shipping thresholds are evaluated against the discounted subtotal.

## Interface contract
Implement exactly these public names; automated checks use them.

- `shopcart.pricing` → **class** `class VolumeDiscountPolicy(PricingPolicy):`  
  A pricing policy that maintains a list of volume-based discount tiers and applies them to cart line items.
- `shopcart.pricing` → **method** `def add_tier(self, min_quantity: int, discount_percent: Decimal | int | str) -> None:`  
  Adds a discount tier. Higher min_quantity values overwrite or take precedence over lower ones when both are met.
- `shopcart.pricing` → **method** `def calculate_discounted_line_total(self, line: LineItem) -> Decimal:`  
  Returns the discounted total for a line item based on its quantity and the applicable tiers, rounded to money.

## Edge cases
- Quantity exactly matching a threshold applies that threshold's discount.
- Multiple tiers with the same threshold: the last one added should be used.
- Tiers added in non-sequential order (e.g., 10 added before 5) must still correctly apply the highest met threshold.
- Empty tier list results in standard pricing (0% discount).
- A tier with 0% discount behaves as no discount.

## Error handling
- add_tier should raise ValueError if min_quantity is less than 1.
- add_tier should raise ValueError if discount_percent is negative or greater than 100.

## Interaction with existing behaviour
- The compute_totals function in shopcart/pricing.py must be updated to use the discount logic if the passed policy is an instance of VolumeDiscountPolicy.
- Tax calculations in compute_tax must use the discounted line total rather than line.line_total if a discount applies.

## Constraints
- Do not modify shopcart/cart.py; the pricing logic must reside within the pricing module to keep the Cart model clean.
- No new third-party dependencies.
- Ensure compatibility with existing PricingPolicy usage in Order.place.
- Do not modify or delete existing tests.
- Do not add new third-party dependencies.
- Keep all existing behaviour working.

## Out of scope
- Discounts targeting specific product SKUs or categories.
- Coupons or fixed-amount discounts.
- Persistent storage for policies.

## Environment
The repository (python) is in the current working directory. You may run the existing test suite to check your work.
