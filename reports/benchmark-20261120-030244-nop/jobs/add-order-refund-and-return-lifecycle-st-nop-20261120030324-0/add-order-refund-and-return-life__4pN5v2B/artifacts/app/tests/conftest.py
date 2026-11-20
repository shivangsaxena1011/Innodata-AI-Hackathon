from decimal import Decimal

import pytest

from shopcart import Cart, Catalog, Inventory, Product


@pytest.fixture
def catalog() -> Catalog:
    c = Catalog()
    c.add(Product("BOOK-1", "Python Tricks", Decimal("24.50"), "books"))
    c.add(Product("BOOK-2", "Fluent Patterns", Decimal("39.00"), "books"))
    c.add(Product("FOOD-1", "Coffee Beans", Decimal("12.00"), "grocery"))
    c.add(Product("TECH-1", "USB-C Cable", Decimal("9.99"), "electronics", frozenset({"cable"})))
    return c


@pytest.fixture
def inventory() -> Inventory:
    inv = Inventory()
    for sku in ("BOOK-1", "BOOK-2", "FOOD-1", "TECH-1"):
        inv.restock(sku, 20)
    return inv


@pytest.fixture
def cart(catalog: Catalog) -> Cart:
    return Cart(catalog)
