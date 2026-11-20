from decimal import Decimal

import pytest

from shopcart import Catalog, Product


def test_product_price_is_rounded():
    assert Product("X", "x", Decimal("1.005"), "misc").price == Decimal("1.01")


def test_negative_price_rejected():
    with pytest.raises(ValueError):
        Product("X", "x", Decimal("-1"), "misc")


def test_duplicate_sku_rejected(catalog: Catalog):
    with pytest.raises(ValueError):
        catalog.add(Product("BOOK-1", "Dup", Decimal("1"), "books"))


def test_lookup_and_category(catalog: Catalog):
    assert catalog.get("FOOD-1").name == "Coffee Beans"
    assert [p.sku for p in catalog.by_category("books")] == ["BOOK-1", "BOOK-2"]
    assert len(catalog) == 4 and "TECH-1" in catalog


def test_unknown_sku(catalog: Catalog):
    with pytest.raises(KeyError):
        catalog.get("NOPE")


def test_search_is_case_insensitive(catalog: Catalog):
    assert [p.sku for p in catalog.search("PYTHON")] == ["BOOK-1"]
