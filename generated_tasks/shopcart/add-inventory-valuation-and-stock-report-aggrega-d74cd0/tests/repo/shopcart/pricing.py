"""Tax and shipping calculation for a cart."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from shopcart.cart import Cart
from shopcart.money import percent_of, to_money


@dataclass(frozen=True)
class PricingPolicy:
    """Tax rates are percentages per product category; `default_tax_rate` covers the rest."""

    default_tax_rate: Decimal = Decimal("8")
    category_tax_rates: dict[str, Decimal] = field(default_factory=dict)
    flat_shipping: Decimal = Decimal("5.99")
    free_shipping_threshold: Decimal = Decimal("50.00")

    def tax_rate_for(self, category: str) -> Decimal:
        return Decimal(self.category_tax_rates.get(category, self.default_tax_rate))


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal


def compute_tax(cart: Cart, policy: PricingPolicy) -> Decimal:
    tax = Decimal("0")
    for line in cart.lines:
        tax += percent_of(line.line_total, policy.tax_rate_for(line.product.category))
    return to_money(tax)


def compute_shipping(cart: Cart, policy: PricingPolicy) -> Decimal:
    if cart.is_empty():
        return Decimal("0.00")
    if cart.subtotal >= policy.free_shipping_threshold:
        return Decimal("0.00")
    return to_money(policy.flat_shipping)


def compute_totals(cart: Cart, policy: PricingPolicy | None = None) -> Totals:
    policy = policy or PricingPolicy()
    subtotal = cart.subtotal
    tax = compute_tax(cart, policy)
    shipping = compute_shipping(cart, policy)
    return Totals(subtotal, tax, shipping, to_money(subtotal + tax + shipping))
