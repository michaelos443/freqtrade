"""
IHyperStrategy interface, hyperoptable Parameter class.
This module defines a base class for auto-hyperoptable strategies.
"""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Union, Dict


from freqtrade.constants import Config
from freqtrade.exceptions import OperationalException
from freqtrade.misc import deep_merge_dicts
from freqtrade.optimize.hyperopt_tools import HyperoptTools
from freqtrade.strategy.parameters import BaseParameter


logger = logging.getLogger(__name__)


class HyperStrategyMixin:
    """
    A helper base class which allows HyperOptAuto class to reuse implementations of buy/sell
     strategy logic. It provides functionality to load, manage, and optimize strategy parameters.
    """

    def __init__(self, config: Config, *args: Any, **kwargs: Any) -> None:
        """
        Initialize hyperoptable strategy mixin.

        :param config: Configuration object for the strategy.
        """
        if not isinstance(config, Config):
            raise OperationalException("Invalid config passed to HyperStrategyMixin.")
        
        self.config = config
        self.ft_buy_params: list[BaseParameter] = []
        self.ft_sell_params: list[BaseParameter] = []
        self.ft_protection_params: list[BaseParameter] = []

        # Load parameters from file
        params = self.load_params_from_file().get("params", {})
        self._ft_params_from_file = params
        # Init/loading of parameters is done as part of ft_bot_start().

    def enumerate_parameters(
        self, category: str | None = None
    ) -> Iterator[tuple[str, BaseParameter]]:
        """
        Find all optimizable parameters and return (name, attr) iterator.
        If category is not specified, all parameters are returned.

        :param category: Parameter category. Can be 'buy', 'sell', 'protection', or None.
        :return: Iterator of (name, attr) tuples.
        :raises: OperationalException if category is invalid.
        """
        if category not in ("buy", "sell", "protection", None):
            raise OperationalException(
                'Category must be one of: "buy", "sell", "protection", None.'
            )
        # Select the appropriate parameter list based on category
        params = (
            self.ft_buy_params + self.ft_sell_params + self.ft_protection_params
            if category is None
            else getattr(self, f"ft_{category}_params")
        )

        for param in params:
            if not isinstance(param, BaseParameter):
                logger.warning(f"Invalid parameter type: {param}. Ignoring.")
                continue
            yield param.name, param

    @classmethod
    def detect_all_parameters(cls) -> dict:
        """
        Detect all parameters and return them as a dictionary.

        :return: Dictionary containing parameters under "buy", "sell", "protection", and "count".
        """
        params: dict[str, Any] = {
            "buy": list(detect_parameters(cls, "buy")),
            "sell": list(detect_parameters(cls, "sell")),
            "protection": list(detect_parameters(cls, "protection")),
        }
        params["count"] = len(params["buy"]) + len(params["sell"]) + len(params["protection"])

        return params

    def ft_load_params_from_file(self) -> None:
        """
        Load Parameters from parameter file and update strategy attributes.
        Should/must run before config values are loaded in strategy_resolver.
        """
        if not self._ft_params_from_file:
            logger.info("No parameters loaded from file, skipping.")
            return
        # Set parameters from Hyperopt results file
        params = self._ft_params_from_file
        self.minimal_roi = params.get("roi", getattr(self, "minimal_roi", {}))

        self.stoploss = params.get("stoploss", {}).get(
            "stoploss", getattr(self, "stoploss", -0.1)
        )   
        self.max_open_trades = params.get("max_open_trades", {}).get(
            "max_open_trades", getattr(self, "max_open_trades", -1)
        )
        trailing = params.get("trailing", {})
        self.trailing_stop = trailing.get(
            "trailing_stop", getattr(self, "trailing_stop", False)
        )
        self.trailing_stop_positive = trailing.get(
            "trailing_stop_positive", getattr(self, "trailing_stop_positive", None)
        )
        self.trailing_stop_positive_offset = trailing.get(
            "trailing_stop_positive_offset", getattr(self, "trailing_stop_positive_offset", 0)
        )
        self.trailing_only_offset_is_reached = trailing.get(
            "trailing_only_offset_is_reached",
            getattr(self, "trailing_only_offset_is_reached", 0.0),
        )

    def ft_load_hyper_params(self, hyperopt: bool = False) -> None:
        """
        Load Hyperoptable parameters
        Prevalence:
        * Parameters from parameter file
        * Parameters defined in parameters objects (buy_params, sell_params, ...)
        * Parameter defaults

        :param hyperopt: True if hyperopt is running.
        """
        buy_params = deep_merge_dicts(
            self._ft_params_from_file.get("buy", {}), getattr(self, "buy_params", {})
        )
        sell_params = deep_merge_dicts(
            self._ft_params_from_file.get("sell", {}), getattr(self, "sell_params", {})
        )
        protection_params = deep_merge_dicts(
            self._ft_params_from_file.get("protection", {}), getattr(self, "protection_params", {})
        )

        self._ft_load_params(buy_params, "buy", hyperopt)
        self._ft_load_params(sell_params, "sell", hyperopt)
        self._ft_load_params(protection_params, "protection", hyperopt)

    def load_params_from_file(self) -> dict:
        """
        Load parameters from the strategy's file.

        :return: Dictionary containing parameters.

        :raises: OperationalException if the parameter file is invalid or its
        format is invalid.
        """
        filename_str = getattr(self, "__file__", "")
        if not filename_str:
            logger.info("No filename found, skipping parameter file loading.")
            return {}

        filename = Path(filename_str).with_suffix(".json")

        if not filename.is_file():
            logger.info(f"Parameter file {filename} not found, skipping.")
            return {}

        logger.info(f"Loading parameters from file {filename}")
        try:
            params = HyperoptTools.load_params(filename)
            if params.get("strategy_name") != self.__class__.__name__:
                raise OperationalException("Invalid parameter file provided.")
            return params
        except ValueError as e:
            raise OperationalException("Invalid parameter file format.") from e

    def _ft_load_params(self, params: dict, space: str, hyperopt: bool = False) -> None:
        """
        Set optimizable parameter values from the provided dictionary.

        :param params: Dictionary with new parameter values.
        :param space: Parameter space. Can be 'buy', 'sell' or 'protection'.
        :param hyperopt: True if hyperopt is running.

        :raises: OperationalException if the provided params argument is not a dictionary.
        """
        if not params:
            logger.info(f"No params for {space} found, using default values.")
        else:
            logger.info(f"Attempting to load params for {space} from strategy.")

        if params and not isinstance(params, dict):
            raise OperationalException(f"Invalid params for {space} found, must be a dictionary.")

        param_container: list[BaseParameter] = getattr(self, f"ft_{space}_params")

        for attr_name, attr in detect_parameters(self, space):
            if not isinstance(attr, BaseParameter):
                logger.warning(f"Invalid parameter type: {attr}. Ignoring.")
                continue
            attr.name = attr_name
            attr.in_space = hyperopt and HyperoptTools.has_space(self.config, space)
            if not attr.category:
                attr.category = space

            param_container.append(attr)

            if params and attr_name in params:
                if attr.load:
                    attr.value = params[attr_name]
                    logger.info(f"Strategy Parameter: {attr_name} = {attr.value}")
                else:
                    logger.warning(
                        f'Parameter "{attr_name}" exists, but is disabled. '
                        f'Default value "{attr.value}" used.'
                    )
            else:
                logger.info(f"Strategy Parameter(default): {attr_name} = {attr.value}")

    def get_no_optimize_params(self) -> dict[str, dict]:
        """
        Returns a dictionary with a list of Parameters that are not part of the
        current optimize job

        :return: Dictionary of parameters that should not be optimized.
        """
        params: dict[str, dict] = {
            "buy": {},
            "sell": {},
            "protection": {},
        }
        for name, p in self.enumerate_parameters():
            if p.category and (not p.optimize or not p.in_space):
                params[p.category][name] = p.value
        return params


def detect_parameters(
    obj: Union[type[HyperStrategyMixin], HyperStrategyMixin], category: str
) -> Iterator[tuple[str, BaseParameter]]:
    """
    Detect all parameters for a given category in the provided object.
    :param obj: Strategy object or class
    :param category: category - usually `'buy', 'sell', 'protection',...

    :return: Iterator of (name, attr) tuples.

    :raises: OperationalException if a parameter name is inconclusive or the category
    doesn't match.
    """
    for attr_name in dir(obj):
        if not attr_name.startswith("__"):  # Ignore internals, not strictly necessary.
            attr = getattr(obj, attr_name)
            if not isinstance(attr, BaseParameter):
                continue
            if (
                attr_name.startswith(category + "_")
                and attr.category is not None
                and attr.category != category
            ):
                raise OperationalException(
                    f"Inconclusive parameter name {attr_name}, category: {attr.category}."
                )

            if category == attr.category or (
                attr_name.startswith(category + "_") and attr.category is None
            ):
                yield attr_name, attr
