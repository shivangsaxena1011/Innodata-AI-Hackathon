# Add order refund and return lifecycle states

Extend the order state machine in `shopcart.orders` to support product returns and order refunds. Add `REFUNDED` and `RETURNED` enum members to `OrderStatus`, update state transition permissions in `ALLOWED_TRANSITIONS`, and add `refund()` and `return_items(inventory)` methods to the `Order` dataclass.

## Background
Currently orders end at `SHIPPED` or `CANCELLED`. Customer support needs to handle post-fulfillment returns and refunds. Returning items must restock inventory on-hand levels, and refunds track financial resolution.

## Requirements
1. Add `REFUNDED = "refunded"` and `RETURNED = "returned"` enum members to `OrderStatus` in `shopcart.orders`.
2. Update `ALLOWED_TRANSITIONS` in `shopcart.orders` to include entries for new statuses and update existing ones:
- `OrderStatus.PAID`: `{OrderStatus.SHIPPED, OrderStatus.CANCELLED, OrderStatus.REFUNDED}`
- `OrderStatus.SHIPPED`: `{OrderStatus.RETURNED}`
- `OrderStatus.RETURNED`: `{OrderStatus.REFUNDED}`
- `OrderStatus.REFUNDED`: `set()`
3. Add `refund(self) -> None` method to `Order` in `shopcart.orders`. It must transition the order status to `OrderStatus.REFUNDED` using `self._transition(OrderStatus.REFUNDED)`. If current status is not `PAID` or `RETURNED`, `_transition` will raise `OrderError`.
4. Add `return_items(self, inventory: Inventory) -> None` method to `Order` in `shopcart.orders`. It must first transition the order status to `OrderStatus.RETURNED` using `self._transition(OrderStatus.RETURNED)`. Then, for each item `(sku, qty)` in `self.items.items()`, call `inventory.restock(sku, qty)`. If the current status is not `SHIPPED`, `_transition` will raise `OrderError` without calling `restock`.

## Acceptance criteria
- **AC1**: `OrderStatus` contains `REFUNDED` with value `'refunded'` and `RETURNED` with value `'returned'`.
- **AC2**: Calling `order.return_items(inventory)` on an order in `SHIPPED` status transitions the order status to `RETURNED`, appends `OrderStatus.RETURNED` to `order.history`, and calls `inventory.restock(sku, qty)` for every SKU in `order.items`.
- **AC3**: Calling `order.refund()` on an order in `PAID` status transitions the order status to `REFUNDED` and appends `OrderStatus.REFUNDED` to `order.history`.
- **AC4**: Calling `order.refund()` on an order in `RETURNED` status transitions the order status to `REFUNDED` and appends `OrderStatus.REFUNDED` to `order.history`.
- **AC5**: Calling `order.refund()` on an order in `PENDING`, `SHIPPED`, `CANCELLED`, or `REFUNDED` status raises `OrderError`.
- **AC6**: Calling `order.return_items(inventory)` on an order in `PENDING`, `PAID`, `CANCELLED`, `RETURNED`, or `REFUNDED` status raises `OrderError` and leaves inventory stock levels untouched.

## Interface contract
Implement exactly these public names; automated checks use them.

- `shopcart.orders` → **enum_member** `OrderStatus.REFUNDED = 'refunded'`  
  Enum value for refunded order status.
- `shopcart.orders` → **enum_member** `OrderStatus.RETURNED = 'returned'`  
  Enum value for returned order status.
- `shopcart.orders` → **method** `def refund(self) -> None`  
  Transitions an order from PAID or RETURNED status to REFUNDED. Raises OrderError for invalid state transitions.
- `shopcart.orders` → **method** `def return_items(self, inventory: Inventory) -> None`  
  Transitions an order from SHIPPED status to RETURNED and calls inventory.restock(sku, quantity) for each SKU in order.items. Raises OrderError for invalid state transitions.

## Edge cases
- Calling `order.return_items(inventory)` on an empty items dict (if possible) transitions status to `RETURNED` without calling restock.
- Attempting to call `refund()` on an order that is already in `REFUNDED` state raises `OrderError`.
- Attempting to call `return_items(inventory)` on an order that is already in `RETURNED` state raises `OrderError`.

## Error handling
- State transitions not explicitly allowed in `ALLOWED_TRANSITIONS` raise `OrderError` with message matching `f"cannot move order from {self.status.value} to {new_status.value}"` via `_transition`.

## Interaction with existing behaviour
- `Order.return_items` calls `inventory.restock(sku, qty)` which increases `inventory._on_hand[sku]` and thus `inventory.available(sku)`.

## Constraints
- Do not add third-party dependencies.
- Do not break existing tests or existing public API signatures.
- Ensure `order.history` records `OrderStatus.RETURNED` and `OrderStatus.REFUNDED` during transitions.
- Do not modify or delete existing tests.
- Do not add new third-party dependencies.
- Keep all existing behaviour working.

## Out of scope
- Partial returns or partial refunds.
- Calculating partial refund amounts or updating `amount_paid` upon refund.

## Environment
The repository (python) is in the current working directory. You may run the existing test suite to check your work.
