# Add inventory valuation and stock report aggregation

Implement a reporting mechanism to calculate total inventory metrics including quantities on-hand, reserved, and available, alongside a monetary valuation derived from the product catalog prices.

## Background
Operations managers require a high-level view of inventory assets to manage working capital and logistics. Currently, the system only allows checking individual SKU availability, making it impossible to see the total value of stock held in the warehouse.

## Requirements
1. Define a dataclass `InventoryReport` in `shopcart.inventory` with the following fields: `total_on_hand` (int), `total_reserved` (int), `total_available` (int), `total_valuation` (Decimal), and `sku_breakdown` (dict[str, dict[str, int | Decimal]]).
2. Implement `generate_inventory_report(inventory: Inventory, catalog: Catalog) -> InventoryReport` in `shopcart.inventory`.
3. The `sku_breakdown` dictionary must be keyed by SKU string. Each value must be a dictionary with keys: 'on_hand' (int), 'reserved' (int), 'available' (int), and 'valuation' (Decimal).
4. Calculate individual SKU valuation as `on_hand * product.price`. If a SKU exists in inventory but is missing from the catalog, the price must default to `Decimal('0.00')`.
5. Aggregate totals: `total_on_hand` is the sum of all on-hand quantities; `total_reserved` is the sum of all reserved quantities; `total_available` is the sum of all available quantities (`on_hand - reserved`).
6. The `total_valuation` must be the sum of all SKU valuations, rounded to two decimal places using the `CENT` constant and `to_money` utility from `shopcart.money`.
7. The report must include every SKU that has either an `on_hand` or a `reserved` balance in the inventory object.

## Acceptance criteria
- **AC1**: `generate_inventory_report` returns an `InventoryReport` containing correct global sums for on-hand, reserved, and available stock.
- **AC2**: The `sku_breakdown` map includes entries for every SKU in inventory with accurate per-SKU metrics.
- **AC3**: SKUs present in `inventory` but missing in `catalog` result in a valuation of `0.00` for that SKU and do not raise `KeyError`.
- **AC4**: An empty inventory (no restocked or reserved items) returns a report with all numeric totals at 0 and an empty `sku_breakdown`.
- **AC5**: The `total_valuation` is correctly quantized to two decimal places using the `CENT` standard defined in the project.

## Interface contract
Implement exactly these public names; automated checks use them.

- `shopcart.inventory` → **class** `@dataclass
class InventoryReport:
    total_on_hand: int
    total_reserved: int
    total_available: int
    total_valuation: Decimal
    sku_breakdown: dict[str, dict[str, int | Decimal]]`  
  A data transfer object representing the state and value of the entire inventory.
- `shopcart.inventory` → **function** `def generate_inventory_report(inventory: Inventory, catalog: Catalog) -> InventoryReport`  
  Iterates through the inventory's internal state to produce an aggregated report cross-referenced with catalog prices.

## Edge cases
- A SKU has higher reserved than on-hand (theoretically possible if commit is called incorrectly, though internal API prevents this): available should show as negative if logic allows, or 0 if strictly following `available()` implementation.
- Catalog is empty while inventory is populated: all valuations should be 0.00.
- SKU price is changed in catalog: the report reflects the latest price from the catalog at the time of generation.

## Error handling
- Use `catalog.get(sku)` and catch `KeyError` to handle missing products by defaulting price to 0.00.
- Ensure the `Inventory` private members `_on_hand` and `_reserved` are accessed safely to avoid missing keys when one dict has a SKU the other doesn't.

## Interaction with existing behaviour
- Reads from `Inventory._on_hand` and `Inventory._reserved` to gather keys and quantities.
- Calls `Catalog.get(sku)` to retrieve product prices for valuation.

## Constraints
- Do not add any third-party dependencies.
- Must use `shopcart.money.to_money` for all Decimal rounding to maintain consistency.
- Do not modify the existing `Inventory` methods' public signatures.
- The implementation must reside in `shopcart/inventory.py`.
- Do not modify or delete existing tests.
- Do not add new third-party dependencies.
- Keep all existing behaviour working.

## Out of scope
- Filtering the report by category or tags.
- Persisting the report to a database or file.
- History tracking of inventory valuation over time.

## Environment
The repository (python) is in the current working directory. You may run the existing test suite to check your work.
