# Add hit_ratio property to CacheInfo

This task extends the `CacheInfo` named tuple to include a calculated `hit_ratio` property. This ratio provides a quick metric of cache efficiency, defined as hits divided by the total number of accesses, rounded to four decimal places.

## Background
Users currently have to manually calculate cache efficiency from the raw `hits` and `misses` provided by `@cached(info=True)`. Automating this calculation directly in the `CacheInfo` object simplifies monitoring and tuning cache configurations.

## Requirements
1. Modify the `CacheInfo` class in `src/cachetools/__init__.py` to include a `hit_ratio` property.
2. The `hit_ratio` must be calculated as `hits / (hits + misses)`.
3. If the total number of accesses (hits + misses) is 0, `hit_ratio` must return `0.0`.
4. The returned `hit_ratio` must be a float rounded to 4 decimal places using the standard `round()` function.
5. Update the type hint for `CacheInfo` in `src/cachetools/__init__.pyi` to reflect the new property.
6. Ensure the addition remains backwards compatible with the `namedtuple` structure of `CacheInfo` (it should still have only 4 fields in its base tuple representation to avoid breaking index-based access, hence implementing it as a property).

## Acceptance criteria
- **AC1**: A newly initialized cache via `@cached(info=True)` returns a `CacheInfo` where `hit_ratio` is `0.0`.
- **AC2**: After 2 hits and 2 misses on a cached function, `cache_info().hit_ratio` returns `0.5`.
- **AC3**: After 1 hit and 2 misses, `cache_info().hit_ratio` returns `0.3333`.
- **AC4**: The `CacheInfo` object can still be unpacked as a 4-tuple: `hits, misses, maxsize, currsize = func.cache_info()`.

## Interface contract
Implement exactly these public names; automated checks use them.

- `cachetools` → **property** `@property def hit_ratio(self) -> float`  
  Returns hits / (hits + misses) rounded to 4 decimal places, or 0.0 if hits + misses is 0.

## Edge cases
- Division by zero when both hits and misses are zero is handled by returning 0.0.
- Rounding handles cases like 1 hit and 2 misses (0.33333...) by truncating/rounding to 0.3333.
- Very large hit/miss counts are handled by Python's standard float division.

## Error handling
- No specific errors are introduced; the calculation is performed on existing integer/float attributes.

## Interaction with existing behaviour
- The change affects all wrappers using `_InfoMixin`, `_LockedInfoMixin`, and `_ConditionInfoMixin` because they all instantiate `CacheInfo` via `CacheInfo._make_info`.

## Constraints
- No new third-party dependencies.
- Do not modify the `_make_info` class method signature or behavior other than ensuring it returns the updated `CacheInfo` type.
- Maintain the namedtuple structure for the 4 existing fields: hits, misses, maxsize, currsize.
- Do not modify or delete existing tests.
- Do not add new third-party dependencies.
- Keep all existing behaviour working.

## Out of scope
- Adding other metrics like latency or eviction counts.
- Changing the internal storage of hits/misses in the decorators.

## Environment
The repository (python) is in the current working directory. You may run the existing test suite to check your work.
