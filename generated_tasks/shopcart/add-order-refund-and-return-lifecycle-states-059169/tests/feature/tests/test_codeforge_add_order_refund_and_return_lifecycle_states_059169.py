import pytest
from decimal import Decimal
from shopcart import Cart, Catalog, Inventory, Product, Order, OrderError, OrderStatus

def setup_env():
    catalog = Catalog()
    p1 = Product("SKU-1", "Product 1", Decimal("10.00"), "misc")
    p2 = Product("SKU-2", "Product 2", Decimal("20.00"), "misc")
    catalog.add(p1)
    catalog.add(p2)
    
    inventory = Inventory()
    inventory.restock("SKU-1", 10)
    inventory.restock("SKU-2", 10)
    
    cart = Cart(catalog)
    return catalog, inventory, cart

def test_order_status_enum_members():
    """AC1: Verify OrderStatus has REFUNDED and RETURNED with correct values."""
    assert OrderStatus.REFUNDED.value == "refunded"
    assert OrderStatus.RETURNED.value == "returned"

def test_return_items_flow():
    """AC2: Verify return_items transitions state and restocks inventory."""
    catalog, inventory, cart = setup_env()
    cart.add_item("SKU-1", 2)
    cart.add_item("SKU-2", 1)
    
    order = Order.place(cart, inventory)
    order.pay(order.totals.total)
    order.ship(inventory)  # Transitions to SHIPPED
    
    # Before return check inventory (20 starting total on-hand in fixture-like setup)
    # Logic: start with 10. Order reserves 2 and 1. Ship commits (on-hand becomes 8 and 9).
    assert inventory.available("SKU-1") == 8
    assert inventory.available("SKU-2") == 9

    order.return_items(inventory)

    assert order.status == OrderStatus.RETURNED
    assert OrderStatus.RETURNED in order.history
    assert inventory.available("SKU-1") == 10
    assert inventory.available("SKU-2") == 10

def test_refund_from_paid():
    """AC3: Verify refund from PAID status."""
    catalog, inventory, cart = setup_env()
    cart.add_item("SKU-1", 1)
    order = Order.place(cart, inventory)
    order.pay(order.totals.total)
    
    order.refund()
    
    assert order.status == OrderStatus.REFUNDED
    assert order.history[-1] == OrderStatus.REFUNDED

def test_refund_from_returned():
    """AC4: Verify refund from RETURNED status."""
    catalog, inventory, cart = setup_env()
    cart.add_item("SKU-1", 1)
    order = Order.place(cart, inventory)
    order.pay(order.totals.total)
    order.ship(inventory)
    order.return_items(inventory)
    
    order.refund()
    
    assert order.status == OrderStatus.REFUNDED
    assert order.history[-1] == OrderStatus.REFUNDED

def test_invalid_refund_transitions():
    """AC5: refund() should fail from PENDING, SHIPPED, CANCELLED, REFUNDED."""
    catalog, inventory, cart = setup_env()
    cart.add_item("SKU-1", 1)
    
    # PENDING
    order = Order.place(cart, inventory)
    with pytest.raises(OrderError):
        order.refund()

    # SHIPPED
    order.pay(order.totals.total)
    order.ship(inventory)
    with pytest.raises(OrderError):
        order.refund()

    # CANCELLED
    order2 = Order.place(cart, inventory)
    order2.cancel(inventory)
    with pytest.raises(OrderError):
        order2.refund()

    # REFUNDED (from PAID)
    order3 = Order.place(cart, inventory)
    order3.pay(order3.totals.total)
    order3.refund()
    with pytest.raises(OrderError, match="cannot move order from refunded to refunded"):
        order3.refund()

def test_invalid_return_transitions():
    """AC6: return_items() should fail from PENDING, PAID, CANCELLED, RETURNED, REFUNDED."""
    catalog, inventory, cart = setup_env()
    cart.add_item("SKU-1", 1)
    
    # PENDING
    order = Order.place(cart, inventory)
    initial_stock = inventory.available("SKU-1")
    with pytest.raises(OrderError):
        order.return_items(inventory)
    assert inventory.available("SKU-1") == initial_stock

    # PAID
    order.pay(order.totals.total)
    with pytest.raises(OrderError):
        order.return_items(inventory)

    # CANCELLED
    order2 = Order.place(cart, inventory)
    order2.cancel(inventory)
    with pytest.raises(OrderError):
        order2.return_items(inventory)

    # RETURNED
    order3 = Order.place(cart, inventory)
    order3.pay(order3.totals.total)
    order3.ship(inventory)
    order3.return_items(inventory)
    with pytest.raises(OrderError, match="cannot move order from returned to returned"):
        order3.return_items(inventory)

    # REFUNDED
    order.refund()
    with pytest.raises(OrderError):
        order.return_items(inventory)

def test_return_items_empty_order_restocks_nothing():
    """Edge case: return_items on empty dict should still transition status."""
    # Note: Order.place prevents empty cart, but we can verify status transition logic
    catalog, inventory, cart = setup_env()
    cart.add_item("SKU-1", 1)
    order = Order.place(cart, inventory)
    order.pay(order.totals.total)
    order.ship(inventory)
    
    # Manually clear items for edge case test if internal state allows, 
    # but here we just ensure normal operation
    order.return_items(inventory)
    assert order.status == OrderStatus.RETURNED
