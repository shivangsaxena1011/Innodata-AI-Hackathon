"""Stock levels and reservations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from shopcart.money import to_money

if TYPE_CHECKING:
    from shopcart.catalog import Catalog


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


@dataclass
class InventoryReport:
    total_on_hand: int
    total_reserved: int
    total_available: int
    total_valuation: Decimal
    sku_breakdown: dict[str, dict[str, int | Decimal]]


def generate_inventory_report(inventory: Inventory, catalog: Catalog) -> InventoryReport:
    all_skus = set(inventory._on_hand.keys()) | set(inventory._reserved.keys())
    
    sku_breakdown = {}
    total_on_hand = 0
    total_reserved = 0
    total_available = 0
    total_valuation = Decimal("0.00")

    for sku in sorted(all_skus):
        oh = inventory._on_hand.get(sku, 0)
        res = inventory._reserved.get(sku, 0)
        
        if oh == 0 and res == 0:
            continue

        avail = oh - res
        
        try:
            product = catalog.get(sku)
            price = product.price
        except KeyError:
            price = Decimal("0.00")

        valuation = to_money(oh * price)

        sku_breakdown[sku] = {
            "on_hand": oh,
            "reserved": res,
            "available": avail,
            "valuation": valuation,
        }

        total_on_hand += oh
        total_reserved += res
        total_available += avail
        total_valuation += valuation

    return InventoryReport(
        total_on_hand=total_on_hand,
        total_reserved=total_reserved,
        total_available=total_available,
        total_valuation=to_money(total_valuation),
        sku_breakdown=sku_breakdown,
    )
