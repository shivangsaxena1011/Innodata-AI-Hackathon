"""Tax and shipping calculation for a cart."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from shopcart.cart import Cart, LineItem
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


class VolumeDiscountPolicy(PricingPolicy):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tiers: dict[int, Decimal] = {}

    def add_tier(self, min_quantity: int, discount_percent: Decimal | int | str) -> None:
        if min_quantity < 1:
            raise ValueError("min_quantity must be at least 1")
        percent = Decimal(discount_percent)
        if percent < 0 or percent > 100:
            raise ValueError("discount_percent must be between 0 and 100")
        self._tiers[min_quantity] = percent

    def calculate_discounted_line_total(self, line: LineItem) -> Decimal:
        applicable_discount = Decimal("0")
        # Sort tiers to find the highest threshold met by the quantity
        for min_qty in sorted(self._tiers.keys()):
            if line.quantity >= min_qty:
                applicable_discount = self._tiers[min_qty]
        
        original_total = line.line_total
        if applicable_discount == 0:
            return original_total
            
        multiplier = (Decimal("100") - applicable_discount) / Decimal("100")
        return to_money(original_total * multiplier)


@dataclass(frozen=True)
class Totals:
    subtotal: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal


def compute_tax(cart: Cart, policy: PricingPolicy) -> Decimal:
    tax = Decimal("0")
    for line in cart.lines:
        line_total = line.line_total
        if isinstance(policy, VolumeDiscountPolicy):
            line_total = policy.calculate_discounted_line_total(line)
        tax += percent_of(line_total, policy.tax_rate_for(line.product.category))
    return to_money(tax)


def compute_shipping(cart: Cart, policy: PricingPolicy) -> Decimal:
    if cart.is_empty():
        return Decimal("0.00")

    subtotal = cart.subtotal
    if isinstance(policy, VolumeDiscountPolicy):
        subtotal = sum(
            (policy.calculate_discounted_line_total(line) for line in cart.lines),
            Decimal("0"),
        )

    if subtotal >= policy.free_shipping_threshold:
        return Decimal("0.00")
    return to_money(policy.flat_shipping)


def compute_totals(cart: Cart, policy: PricingPolicy | None = None) -> Totals:
    policy = policy or PricingPolicy()
    if isinstance(policy, VolumeDiscountPolicy):
        subtotal = to_money(
            sum(
                (policy.calculate_discounted_line_total(line) for line in cart.lines),
                Decimal("0"),
            )
        )
    else:
        subtotal = cart.subtotal

    tax = compute_tax(cart, policy)
    shipping = compute_shipping(cart, policy)
    return Totals(subtotal, tax, shipping, to_money(subtotal + tax + shipping))
