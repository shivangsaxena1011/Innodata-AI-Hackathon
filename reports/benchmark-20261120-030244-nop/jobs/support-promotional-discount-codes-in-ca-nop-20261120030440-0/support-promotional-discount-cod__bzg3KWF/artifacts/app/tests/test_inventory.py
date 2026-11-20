import pytest

from shopcart import Inventory, InventoryError


def test_restock_and_reserve():
    inv = Inventory()
    inv.restock("A", 5)
    inv.reserve("A", 3)
    assert inv.available("A") == 2


def test_over_reserve_fails():
    inv = Inventory()
    inv.restock("A", 1)
    with pytest.raises(InventoryError):
        inv.reserve("A", 2)


def test_release_more_than_held_fails():
    inv = Inventory()
    inv.restock("A", 3)
    inv.reserve("A", 1)
    with pytest.raises(InventoryError):
        inv.release("A", 2)


def test_commit_reduces_on_hand():
    inv = Inventory()
    inv.restock("A", 4)
    inv.reserve("A", 4)
    inv.commit("A", 4)
    assert inv.available("A") == 0


def test_restock_requires_positive_quantity():
    with pytest.raises(InventoryError):
        Inventory().restock("A", 0)
