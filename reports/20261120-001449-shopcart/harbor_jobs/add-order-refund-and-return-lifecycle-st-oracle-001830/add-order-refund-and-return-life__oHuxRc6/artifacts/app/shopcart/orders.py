"""Order lifecycle."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from shopcart.cart import Cart
from shopcart.inventory import Inventory
from shopcart.pricing import PricingPolicy, Totals, compute_totals

_ids = itertools.count(1)


class OrderError(Exception):
    """Raised for invalid order transitions."""


class OrderStatus(Enum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    RETURNED = "returned"


ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.SHIPPED, OrderStatus.CANCELLED, OrderStatus.REFUNDED},
    OrderStatus.SHIPPED: {OrderStatus.RETURNED},
    OrderStatus.RETURNED: {OrderStatus.REFUNDED},
    OrderStatus.REFUNDED: set(),
    OrderStatus.CANCELLED: set(),
}


@dataclass
class Order:
    order_id: int
    items: dict[str, int]
    totals: Totals
    status: OrderStatus = OrderStatus.PENDING
    history: list[OrderStatus] = field(default_factory=list)
    amount_paid: Decimal = Decimal("0.00")

    @classmethod
    def place(cls, cart: Cart, inventory: Inventory, policy: PricingPolicy | None = None) -> Order:
        if cart.is_empty():
            raise OrderError("cannot place an order for an empty cart")
        reserved: list[tuple[str, int]] = []
        try:
            for line in cart.lines:
                inventory.reserve(line.product.sku, line.quantity)
                reserved.append((line.product.sku, line.quantity))
        except Exception:
            for sku, qty in reserved:
                inventory.release(sku, qty)
            raise
        items = {line.product.sku: line.quantity for line in cart.lines}
        order = cls(next(_ids), items, compute_totals(cart, policy))
        order.history.append(OrderStatus.PENDING)
        return order

    def _transition(self, new_status: OrderStatus) -> None:
        if new_status not in ALLOWED_TRANSITIONS[self.status]:
            raise OrderError(f"cannot move order from {self.status.value} to {new_status.value}")
        self.status = new_status
        self.history.append(new_status)

    def pay(self, amount: Decimal) -> None:
        if Decimal(amount) != self.totals.total:
            raise OrderError("payment must equal the order total")
        self._transition(OrderStatus.PAID)
        self.amount_paid = Decimal(amount)

    def ship(self, inventory: Inventory) -> None:
        self._transition(OrderStatus.SHIPPED)
        for sku, qty in self.items.items():
            inventory.commit(sku, qty)

    def cancel(self, inventory: Inventory) -> None:
        self._transition(OrderStatus.CANCELLED)
        for sku, qty in self.items.items():
            inventory.release(sku, qty)

    def refund(self) -> None:
        self._transition(OrderStatus.REFUNDED)

    def return_items(self, inventory: Inventory) -> None:
        self._transition(OrderStatus.RETURNED)
        for sku, qty in self.items.items():
            inventory.restock(sku, qty)
