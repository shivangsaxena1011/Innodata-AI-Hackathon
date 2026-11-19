import pytest

from shopcart import Cart, Inventory, InventoryError, Order, OrderError, OrderStatus


def test_place_reserves_stock(cart: Cart, inventory: Inventory):
    cart.add_item("BOOK-1", 3)
    order = Order.place(cart, inventory)
    assert order.status is OrderStatus.PENDING
    assert inventory.available("BOOK-1") == 17


def test_place_empty_cart_fails(cart: Cart, inventory: Inventory):
    with pytest.raises(OrderError):
        Order.place(cart, inventory)


def test_failed_reservation_rolls_back(cart: Cart, inventory: Inventory):
    cart.add_item("BOOK-1", 5)
    cart.add_item("TECH-1", 25)
    with pytest.raises(InventoryError):
        Order.place(cart, inventory)
    assert inventory.available("BOOK-1") == 20


def test_pay_ship_flow(cart: Cart, inventory: Inventory):
    cart.add_item("FOOD-1", 2)
    order = Order.place(cart, inventory)
    order.pay(order.totals.total)
    order.ship(inventory)
    assert order.history == [OrderStatus.PENDING, OrderStatus.PAID, OrderStatus.SHIPPED]
    assert inventory.available("FOOD-1") == 18


def test_wrong_payment_amount(cart: Cart, inventory: Inventory):
    cart.add_item("FOOD-1")
    order = Order.place(cart, inventory)
    with pytest.raises(OrderError):
        order.pay(order.totals.total + 1)


def test_cancel_releases_stock(cart: Cart, inventory: Inventory):
    cart.add_item("TECH-1", 4)
    order = Order.place(cart, inventory)
    order.cancel(inventory)
    assert inventory.available("TECH-1") == 20
    with pytest.raises(OrderError):
        order.ship(inventory)
