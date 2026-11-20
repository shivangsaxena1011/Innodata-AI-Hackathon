from decimal import Decimal

from shopcart import Cart, PricingPolicy, compute_totals


def test_default_tax_and_flat_shipping(cart: Cart):
    cart.add_item("FOOD-1", 2)  # 24.00
    totals = compute_totals(cart)
    assert totals.subtotal == Decimal("24.00")
    assert totals.tax == Decimal("1.92")
    assert totals.shipping == Decimal("5.99")
    assert totals.total == Decimal("31.91")


def test_free_shipping_at_threshold(cart: Cart):
    cart.add_item("BOOK-1", 2)  # 49.00
    cart.add_item("TECH-1")  # 58.99
    assert compute_totals(cart).shipping == Decimal("0.00")


def test_category_tax_rates(cart: Cart):
    policy = PricingPolicy(category_tax_rates={"books": Decimal("0"), "grocery": Decimal("5")})
    cart.add_item("BOOK-1")
    cart.add_item("FOOD-1")
    assert compute_totals(cart, policy).tax == Decimal("0.60")


def test_empty_cart_totals(cart: Cart):
    totals = compute_totals(cart)
    assert totals.total == Decimal("0.00") and totals.shipping == Decimal("0.00")
