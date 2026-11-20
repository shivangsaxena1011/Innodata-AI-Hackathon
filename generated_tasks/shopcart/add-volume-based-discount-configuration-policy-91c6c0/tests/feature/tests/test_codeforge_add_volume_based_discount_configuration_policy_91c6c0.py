import pytest
from decimal import Decimal
from shopcart.catalog import Catalog, Product
from shopcart.cart import Cart
from shopcart.pricing import VolumeDiscountPolicy, compute_totals, compute_tax
from shopcart.money import to_money

def setup_cart_and_policy():
    catalog = Catalog()
    product = Product("SKU-1", "Test Item", Decimal("10.00"), "misc")
    catalog.add(product)
    cart = Cart(catalog)
    policy = VolumeDiscountPolicy()
    return cart, policy, product

def test_ac1_exact_tier_match():
    """Given a VolumeDiscountPolicy with a tier (10 units, 10% discount), 10 units of a $10.00 item results in a subtotal of $90.00."""
    cart, policy, _ = setup_cart_and_policy()
    policy.add_tier(10, 10)
    cart.add_item("SKU-1", 10)
    
    totals = compute_totals(cart, policy)
    # 10 * 10 = 100. 100 * (1 - 0.10) = 90.00
    assert totals.subtotal == Decimal("90.00")

def test_ac2_highest_applicable_tier():
    """Given tiers (5 units, 5%) and (10 units, 10%), a cart with 12 units of a $10.00 item results in a subtotal of $108.00."""
    cart, policy, _ = setup_cart_and_policy()
    policy.add_tier(5, 5)
    policy.add_tier(10, 10)
    cart.add_item("SKU-1", 12)
    
    totals = compute_totals(cart, policy)
    # 12 * 10 = 120. 120 * (1 - 0.10) = 108.00
    assert totals.subtotal == Decimal("108.00")

def test_ac3_below_tier_no_discount():
    """Given a VolumeDiscountPolicy with a tier (10 units, 10%), a cart with 9 units of a $10.00 item results in a subtotal of $90.00 (no discount applied)."""
    cart, policy, _ = setup_cart_and_policy()
    policy.add_tier(10, 10)
    cart.add_item("SKU-1", 9)
    
    totals = compute_totals(cart, policy)
    # 9 * 10 = 90.00
    assert totals.subtotal == Decimal("90.00")

def test_ac4_tax_calculated_on_discounted_price():
    """Tax is calculated based on the discounted price. If a $100.00 line item is discounted to $90.00 and the tax rate is 10%, the tax is $9.00."""
    catalog = Catalog()
    product = Product("SKU-100", "Big Item", Decimal("100.00"), "misc")
    catalog.add(product)
    cart = Cart(catalog)
    cart.add_item("SKU-100", 1)
    
    policy = VolumeDiscountPolicy(default_tax_rate=Decimal("10"))
    policy.add_tier(1, 10)
    
    tax = compute_tax(cart, policy)
    # Discounted total = 90.00. 10% of 90.00 = 9.00
    assert tax == Decimal("9.00")

def test_ac5_shipping_on_discounted_subtotal():
    """Free shipping thresholds are evaluated against the discounted subtotal."""
    # Threshold 50.00. 5 units * 10.00 = 50.00. 10% discount = 45.00.
    # 45.00 < 50.00, so shipping is applied.
    cart, policy, _ = setup_cart_and_policy()
    policy.add_tier(5, 10)
    cart.add_item("SKU-1", 5)
    
    totals = compute_totals(cart, policy)
    assert totals.subtotal == Decimal("45.00")
    assert totals.shipping == Decimal("5.99")

def test_shipping_at_threshold_boundary():
    """Ensure shipping is free exactly at the threshold with discount."""
    # Product price 10.00, quantity 10 = 100.00. 50% discount = 50.00.
    # Free shipping threshold is 50.00. GtE 50.00 should be free.
    cart, policy, _ = setup_cart_and_policy()
    policy.add_tier(10, 50)
    cart.add_item("SKU-1", 10)
    
    totals = compute_totals(cart, policy)
    assert totals.subtotal == Decimal("50.00")
    assert totals.shipping == Decimal("0.00")

def test_discount_rounding_half_up():
    """Discounted amounts must be rounded to nearest cent."""
    # 1 item of $10.00, discount 12.51%. 
    # 10.00 * (1 - 0.1251) = 8.749. Rounding half-up to cents = 8.75.
    catalog = Catalog()
    catalog.add(Product("SKU-1", "Test", Decimal("10.00"), "misc"))
    cart = Cart(catalog)
    cart.add_item("SKU-1", 1)
    policy = VolumeDiscountPolicy()
    policy.add_tier(1, "12.51")
    
    assert policy.calculate_discounted_line_total(cart.lines[0]) == Decimal("8.75")

def test_empty_subtotal_with_volume_policy():
    """Ensure compute_totals does not initialize subtotal/tax at 1.00 when cart is empty."""
    catalog = Catalog()
    cart = Cart(catalog)
    policy = VolumeDiscountPolicy()
    totals = compute_totals(cart, policy)
    assert totals.subtotal == Decimal("0.00")
    assert totals.tax == Decimal("0.00")

def test_edge_case_duplicate_threshold_last_wins():
    """Multiple tiers with the same threshold: the last one added should be used."""
    cart, policy, _ = setup_cart_and_policy()
    policy.add_tier(5, 10)
    policy.add_tier(5, 20)
    cart.add_item("SKU-1", 5)
    
    # 50.00 * 0.8 = 40.00
    assert policy.calculate_discounted_line_total(cart.lines[0]) == Decimal("40.00")

def test_edge_case_non_sequential_tiers():
    """Tiers added in non-sequential order must still apply highest met threshold."""
    cart, policy, _ = setup_cart_and_policy()
    policy.add_tier(10, 20)
    policy.add_tier(5, 10)
    cart.add_item("SKU-1", 12)
    
    # 12 * 10 = 120. 120 * 0.8 = 96.00
    assert policy.calculate_discounted_line_total(cart.lines[0]) == Decimal("96.00")

def test_error_invalid_min_quantity():
    policy = VolumeDiscountPolicy()
    with pytest.raises(ValueError):
        policy.add_tier(0, 10)

def test_error_invalid_discount_percent():
    policy = VolumeDiscountPolicy()
    with pytest.raises(ValueError):
        policy.add_tier(1, -1)
    with pytest.raises(ValueError):
        policy.add_tier(1, 100.01)

def test_exact_100_percent_discount_allowed():
    """Discount of exactly 100% is valid."""
    policy = VolumeDiscountPolicy()
    policy.add_tier(1, 100)
    catalog = Catalog()
    catalog.add(Product("SKU-1", "Test", Decimal("10.00"), "misc"))
    cart = Cart(catalog)
    cart.add_item("SKU-1", 1)
    assert policy.calculate_discounted_line_total(cart.lines[0]) == Decimal("0.00")