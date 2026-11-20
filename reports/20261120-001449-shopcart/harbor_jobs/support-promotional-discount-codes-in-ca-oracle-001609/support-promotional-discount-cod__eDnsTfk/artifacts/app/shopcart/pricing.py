"""Tax and shipping calculation for a cart."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from shopcart.cart import Cart
from shopcart.money import percent_of, to_money


class PricingError(Exception):
    """Raised when pricing operations fail."""


@dataclass(frozen=True)
class DiscountCoupon:
    code: str
    discount_percent: Decimal = Decimal('0')
    fixed_amount: Decimal = Decimal('0')
    min_subtotal: Decimal = Decimal('0')

    def __post_init__(self) -> None:
        object.__setattr__(self, "discount_percent", Decimal(str(self.discount_percent)))
        object.__setattr__(self, "fixed_amount", Decimal(str(self.fixed_amount)))
        object.__setattr__(self, "min_subtotal", Decimal(str(self.min_subtotal)))


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
    discount: Decimal = Decimal('0.00')
    tax: Decimal = Decimal('0.00')
    shipping: Decimal = Decimal('0.00')
    total: Decimal = Decimal('0.00')

    def __post_init__(self) -> None:
        calculated_total = to_money(self.subtotal - self.discount + self.tax + self.shipping)
        if self.total != calculated_total:
            object.__setattr__(self, "total", calculated_total)


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


def compute_totals(
    cart: Cart,
    policy: PricingPolicy | None = None,
    coupon: DiscountCoupon | None = None,
) -> Totals:
    policy = policy or PricingPolicy()
    subtotal = cart.subtotal

    if coupon is not None:
        if subtotal < coupon.min_subtotal:
            raise PricingError(f"cart subtotal {subtotal} does not meet coupon minimum {coupon.min_subtotal}")
        raw_discount = percent_of(subtotal, coupon.discount_percent) + to_money(coupon.fixed_amount)
        discount = min(raw_discount, subtotal)
    else:
        discount = Decimal("0.00")

    if subtotal == Decimal("0.00") or discount == subtotal:
        tax = Decimal("0.00")
    else:
        line_taxes = []
        factor = Decimal("1") - (discount / subtotal)
        for line in cart.lines:
            discounted_line_base = line.line_total * factor
            line_tax = percent_of(discounted_line_base, policy.tax_rate_for(line.product.category))
            line_taxes.append(line_tax)
        tax = to_money(sum(line_taxes))

    shipping = compute_shipping(cart, policy)
    total = to_money(subtotal - discount + tax + shipping)
    return Totals(subtotal=subtotal, discount=discount, tax=tax, shipping=shipping, total=total)
