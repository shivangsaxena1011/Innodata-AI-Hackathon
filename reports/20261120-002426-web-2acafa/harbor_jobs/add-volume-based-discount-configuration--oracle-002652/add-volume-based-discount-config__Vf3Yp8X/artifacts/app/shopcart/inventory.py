"""Stock levels and reservations."""

from __future__ import annotations


class InventoryError(Exception):
    """Raised when stock is insufficient or a reservation is invalid."""


class Inventory:
    def __init__(self) -> None:
        self._on_hand: dict[str, int] = {}
        self._reserved: dict[str, int] = {}

    def restock(self, sku: str, quantity: int) -> None:
        if quantity <= 0:
            raise InventoryError("restock quantity must be positive")
        self._on_hand[sku] = self._on_hand.get(sku, 0) + quantity

    def available(self, sku: str) -> int:
        return self._on_hand.get(sku, 0) - self._reserved.get(sku, 0)

    def reserve(self, sku: str, quantity: int) -> None:
        if quantity <= 0:
            raise InventoryError("reservation quantity must be positive")
        if self.available(sku) < quantity:
            raise InventoryError(f"insufficient stock for {sku}")
        self._reserved[sku] = self._reserved.get(sku, 0) + quantity

    def release(self, sku: str, quantity: int) -> None:
        held = self._reserved.get(sku, 0)
        if quantity <= 0 or quantity > held:
            raise InventoryError(f"cannot release {quantity} of {sku}")
        self._reserved[sku] = held - quantity

    def commit(self, sku: str, quantity: int) -> None:
        """Convert a reservation into a shipment, reducing on-hand stock."""
        self.release(sku, quantity)
        self._on_hand[sku] -= quantity
