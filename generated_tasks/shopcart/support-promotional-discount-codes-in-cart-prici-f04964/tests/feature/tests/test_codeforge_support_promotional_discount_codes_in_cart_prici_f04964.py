from decimal import Decimal
import pytest

from shopcart.cart import Cart
from shopcart.catalog import Catalog, Product
from shopcart.pricing import (
    DiscountCoupon,
    PricingError,
    PricingPolicy,
    Totals,
    compute_totals,
)

def _make_catalog() -> Catalog:
    cat = Catalog()
    cat.add(Product("BOOK-1", "Python Tricks", Decimal("24.50"), "books"))
    cat.add(Product("BOOK-2", "Fluent Patterns", Decimal("39.00"), "books"))
    cat.add(Product("FOOD-1", "Coffee Beans", Decimal("12.00"), "grocery"))
    cat.add(Product("TECH-1", "USB-C Cable", Decimal("9.99"), "electronics"))
    return cat

def test_ac1_min_subtotal_below_threshold_raises_pricing_error():
    catalog = _make_catalog()
    cart = Cart(catalog)
    cart.add_item("BOOK-1", 1)  # subtotal = 24.50
    coupon = DiscountCoupon("SAVE10", fixed_amount=Decimal("5.00"), min_subtotal=Decimal("50.00"))

    expected_msg = "cart subtotal 24.50 does not meet coupon minimum 50.00"
    with pytest.raises(PricingError) as excinfo:
        compute_totals(cart, coupon=coupon)
    assert str(excinfo.value) == expected_msg

def test_ac1_min_subtotal_exact_match_succeeds():
    catalog = _make_catalog()
    cart = Cart(catalog)
    cart.add_item("BOOK-1", 2)  # subtotal = 49.00
    cart.add_item("FOOD-1", 1)  # subtotal = 61.00
    coupon = DiscountCoupon("MIN61", fixed_amount=Decimal("10.00"), min_subtotal=Decimal("61.00"))
    totals = compute_totals(cart, coupon=coupon)
    assert totals.discount == Decimal("10.00")

def test_ac2_valid_percentage_coupon():
    catalog = _make_catalog()
    cart = Cart(catalog)
    cart.add_item("BOOK-2", 2)  # subtotal = 78.00
    policy = PricingPolicy(default_tax_rate=Decimal("10"), flat_shipping=Decimal("5.99"), free_shipping_threshold=Decimal("100.00"))
    coupon = DiscountCoupon("PERCENT15", discount_percent=Decimal("15"))
    totals = compute_totals(cart, policy, coupon=coupon)
    assert totals.subtotal == Decimal("78.00")
    assert totals.discount == Decimal("11.70") # 15% of 78
    assert totals.tax == Decimal("6.63") # 10% of (78 - 11.70)
    assert totals.shipping == Decimal("5.99")
    assert totals.total == Decimal("78.92")

def test_ac3_clamped_discount_exceeding_subtotal():
    catalog = _make_catalog()
    cart = Cart(catalog)
    cart.add_item("FOOD-1", 1)  # subtotal = 12.00
    policy = PricingPolicy(flat_shipping=Decimal("5.99"), free_shipping_threshold=Decimal("50.00"))
    coupon = DiscountCoupon("HUGE", fixed_amount=Decimal("20.00"))
    totals = compute_totals(cart, policy, coupon=coupon)
    assert totals.discount == Decimal("12.00")
    assert totals.tax == Decimal("0.00")
    assert totals.shipping == Decimal("5.99")
    assert totals.total == Decimal("5.99")

def test_ac4_totals_equation_and_ordering():
    catalog = _make_catalog()
    cart = Cart(catalog)
    cart.add_item("BOOK-1", 1)
    policy = PricingPolicy(default_tax_rate=Decimal("10"))
    coupon = DiscountCoupon("C", discount_percent=Decimal("10"))
    totals = compute_totals(cart, policy, coupon=coupon)
    # Check positional order
    assert totals.subtotal == Decimal("24.50")
    assert totals.discount == Decimal("2.45")
    assert totals.tax == Decimal("2.21") # (24.50-2.45)*0.1
    assert totals.shipping == Decimal("5.99")
    assert totals.total == Decimal("30.25") # 24.50 - 2.45 + 2.21 + 5.99

def test_ac5_coupon_none_preserves_behavior():
    catalog = _make_catalog()
    cart = Cart(catalog)
    cart.add_item("BOOK-1", 2) # 49.00
    policy = PricingPolicy(default_tax_rate=Decimal("8"), flat_shipping=Decimal("5.99"))
    totals = compute_totals(cart, policy, coupon=None)
    assert totals.discount == Decimal("0.00")
    assert totals.subtotal == Decimal("49.00")
    assert totals.tax == Decimal("3.92")
    assert totals.total == Decimal("58.91")

def test_requirement_7_shipping_on_original_subtotal():
    catalog = _make_catalog()
    cart = Cart(catalog)
    cart.add_item("BOOK-2", 2) # subtotal = 78.00
    # Free shipping threshold is 50.00. Original subtotal (78) qualifies.
    # Discount is 40.00, making discounted subtotal (38) less than threshold.
    # shipping MUST still be 0.00.
    policy = PricingPolicy(free_shipping_threshold=Decimal("50.00"), flat_shipping=Decimal("10.00"))
    coupon = DiscountCoupon("BIG", fixed_amount=Decimal("40.00"))
    totals = compute_totals(cart, policy, coupon=coupon)
    assert totals.subtotal == Decimal("78.00")
    assert totals.shipping == Decimal("0.00")

def test_requirement_2_dataclass_coercion():
    # Using float and string to check if __post_init__ or field conversion handles it
    coupon = DiscountCoupon(code="FLOAT", discount_percent=10.5, fixed_amount="5.00", min_subtotal=20)
    assert isinstance(coupon.discount_percent, Decimal)
    assert isinstance(coupon.fixed_amount, Decimal)
    assert isinstance(coupon.min_subtotal, Decimal)
    assert coupon.discount_percent == Decimal("10.5")
    assert coupon.fixed_amount == Decimal("5.00")
    assert coupon.min_subtotal == Decimal("20")

def test_edge_case_proportional_tax_rounding():
    catalog = _make_catalog()
    cart = Cart(catalog)
    cart.add_item("BOOK-1", 1) # 24.50
    cart.add_item("TECH-1", 1) # 9.99
    # Subtotal = 34.49
    policy = PricingPolicy(category_tax_rates={"books": Decimal("10"), "electronics": Decimal("20")})
    coupon = DiscountCoupon("FIXED", fixed_amount=Decimal("10.00"))
    # factor = 1 - 10/34.49 = 24.49/34.49
    # Book Base: 24.50 * (24.49/34.49) = 17.39649... -> Tax @ 10% = 1.739... -> 1.74
    # Tech Base: 9.99 * (24.49/34.49) = 7.09350... -> Tax @ 20% = 1.418... -> 1.42
    # Total Tax = 1.74 + 1.42 = 3.16
    totals = compute_totals(cart, policy, coupon=coupon)
    assert totals.tax == Decimal("3.16")

def test_totals_immutability_and_validation():
    # Ensure Totals validation/re-quantization of total works as specified in Requirement 3
    # Requirement says total must equal to_money(subtotal - discount + tax + shipping)
    t = Totals(subtotal=Decimal("10.00"), discount=Decimal("2.00"), tax=Decimal("0.80"), shipping=Decimal("5.00"), total=Decimal("0"))
    assert t.total == Decimal("13.80")