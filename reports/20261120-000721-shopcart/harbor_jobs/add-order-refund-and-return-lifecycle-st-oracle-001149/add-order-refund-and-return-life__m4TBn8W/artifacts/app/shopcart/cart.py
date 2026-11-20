"""Shopping cart."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from shopcart.catalog import Catalog, Product
from shopcart.money import to_money

MAX_QUANTITY_PER_LINE = 99


class CartError(Exception):
    """Raised for invalid cart operations."""


@dataclass
class LineItem:
    product: Product
    quantity: int

    @property
    def line_total(self) -> Decimal:
        return to_money(self.product.price * self.quantity)


class Cart:
    def __init__(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._lines: dict[str, LineItem] = {}

    @property
    def lines(self) -> list[LineItem]:
        return [self._lines[sku] for sku in sorted(self._lines)]

    def add_item(self, sku: str, quantity: int = 1) -> LineItem:
        if quantity <= 0:
            raise CartError("quantity must be positive")
        product = self._catalog.get(sku)
        line = self._lines.get(sku)
        new_quantity = quantity + (line.quantity if line else 0)
        if new_quantity > MAX_QUANTITY_PER_LINE:
            raise CartError(f"at most {MAX_QUANTITY_PER_LINE} units per item")
        if line:
            line.quantity = new_quantity
        else:
            line = LineItem(product, quantity)
            self._lines[sku] = line
        return line

    def update_quantity(self, sku: str, quantity: int) -> None:
        if sku not in self._lines:
            raise CartError(f"{sku} is not in the cart")
        if quantity < 0 or quantity > MAX_QUANTITY_PER_LINE:
            raise CartError("invalid quantity")
        if quantity == 0:
            del self._lines[sku]
        else:
            self._lines[sku].quantity = quantity

    def remove_item(self, sku: str) -> None:
        if self._lines.pop(sku, None) is None:
            raise CartError(f"{sku} is not in the cart")

    def clear(self) -> None:
        self._lines.clear()

    @property
    def subtotal(self) -> Decimal:
        return to_money(sum((line.line_total for line in self._lines.values()), Decimal("0")))

    @property
    def total_items(self) -> int:
        return sum(line.quantity for line in self._lines.values())

    def is_empty(self) -> bool:
        return not self._lines
