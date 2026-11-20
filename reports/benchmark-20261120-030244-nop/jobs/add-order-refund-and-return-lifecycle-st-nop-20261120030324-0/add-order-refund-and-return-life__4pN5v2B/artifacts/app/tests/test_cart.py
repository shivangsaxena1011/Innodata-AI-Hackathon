from decimal import Decimal

import pytest

from shopcart import Cart, CartError
from shopcart.cart import MAX_QUANTITY_PER_LINE


def test_add_and_subtotal(cart: Cart):
    cart.add_item("BOOK-1", 2)
    cart.add_item("FOOD-1")
    assert cart.subtotal == Decimal("61.00")
    assert cart.total_items == 3


def test_adding_same_sku_merges_lines(cart: Cart):
    cart.add_item("TECH-1", 1)
    cart.add_item("TECH-1", 2)
    assert len(cart.lines) == 1 and cart.lines[0].quantity == 3


def test_quantity_must_be_positive(cart: Cart):
    with pytest.raises(CartError):
        cart.add_item("BOOK-1", 0)


def test_quantity_limit(cart: Cart):
    cart.add_item("BOOK-1", MAX_QUANTITY_PER_LINE)
    with pytest.raises(CartError):
        cart.add_item("BOOK-1", 1)


def test_update_and_remove(cart: Cart):
    cart.add_item("BOOK-2", 2)
    cart.update_quantity("BOOK-2", 5)
    assert cart.total_items == 5
    cart.update_quantity("BOOK-2", 0)
    assert cart.is_empty()
    with pytest.raises(CartError):
        cart.remove_item("BOOK-2")


def test_lines_sorted_by_sku(cart: Cart):
    cart.add_item("TECH-1")
    cart.add_item("BOOK-1")
    assert [line.product.sku for line in cart.lines] == ["BOOK-1", "TECH-1"]
