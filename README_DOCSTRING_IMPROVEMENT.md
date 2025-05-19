# Docstring Improvement for get_valid_price Function

This document describes the improvements made to the `get_valid_price` function docstring in `freqtrade-v1_2/freqtrade/freqtradebot.py`.

## Summary of Changes

The docstring was enhanced with:

1. **Comprehensive description** of function purpose and behavior
2. **Detailed parameter documentation** with types and descriptions  
3. **Clear explanation** of return value and constraints
4. **Configuration dependency** documentation (`custom_price_max_distance_ratio`)
5. **Practical examples** showing different scenarios
6. **Fallback behavior** documentation for invalid inputs

## Impact

This improvement makes the function much easier to understand and use for developers working with custom price validation in the freqtrade bot.

## Function Location

File: `freqtrade-v1_2/freqtrade/freqtradebot.py`
Function: `get_valid_price`
Line: ~2738

## Before and After

### Before
```python
def get_valid_price(self, custom_price: Optional[float], proposed_price: float) -> float:
    """
    Return the valid price.
    Check if the custom price is of the good type if not return proposed_price
    :return: valid price for the order
    """
```

### After
```python
def get_valid_price(self, custom_price: Optional[float], proposed_price: float) -> float:
    """
    Validate and constrain a custom price within acceptable bounds.
    
    This function ensures that custom prices returned by strategy callbacks
    (custom_entry_price, custom_exit_price) are within a reasonable distance
    from the market-proposed price to prevent extreme price deviations that
    could result in unfilled orders.
    
    Args:
        custom_price: Custom price from strategy callback. Can be None, string,
                     int, or float. If None or invalid, falls back to proposed_price.
        proposed_price: Market-based price proposed by the exchange (always float).
    
    Returns:
        float: Valid price constrained within the configured distance ratio
               from the proposed price.
    
    Note:
        The maximum allowed distance is controlled by the configuration parameter
        'custom_price_max_distance_ratio' (default: 0.02 = 2%).
        
        The returned price will be:
        - At least: proposed_price * (1 - custom_price_max_distance_ratio)
        - At most: proposed_price * (1 + custom_price_max_distance_ratio)
    
    Examples:
        >>> # With default 2% distance ratio and proposed_price=100
        >>> bot.get_valid_price(98.5, 100)   # Returns 98.5 (within 2%)
        >>> bot.get_valid_price(95.0, 100)   # Returns 98.0 (clamped to min)
        >>> bot.get_valid_price(105.0, 100)  # Returns 102.0 (clamped to max)
        >>> bot.get_valid_price("invalid", 100)  # Returns 100 (fallback)
        >>> bot.get_valid_price(None, 100)   # Returns 100 (fallback)
    """
```
