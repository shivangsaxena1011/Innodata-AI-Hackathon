"""Product catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from shopcart.money import to_money


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price: Decimal
    category: str
    tags: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.sku:
            raise ValueError("sku must not be empty")
        price = to_money(self.price)
        if price < 0:
            raise ValueError("price must not be negative")
        object.__setattr__(self, "price", price)


class Catalog:
    """An in-memory product catalog indexed by SKU."""

    def __init__(self) -> None:
        self._products: dict[str, Product] = {}

    def add(self, product: Product) -> None:
        if product.sku in self._products:
            raise ValueError(f"duplicate sku: {product.sku}")
        self._products[product.sku] = product

    def get(self, sku: str) -> Product:
        try:
            return self._products[sku]
        except KeyError:
            raise KeyError(f"unknown sku: {sku}") from None

    def by_category(self, category: str) -> list[Product]:
        return sorted(
            (p for p in self._products.values() if p.category == category), key=lambda p: p.sku
        )

    def search(self, text: str) -> list[Product]:
        needle = text.lower()
        return sorted(
            (p for p in self._products.values() if needle in p.name.lower()), key=lambda p: p.sku
        )

    def __len__(self) -> int:
        return len(self._products)

    def __contains__(self, sku: object) -> bool:
        return sku in self._products
