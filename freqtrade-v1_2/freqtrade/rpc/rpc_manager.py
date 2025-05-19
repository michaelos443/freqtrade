"""
This module contains the RPCManager class to manage RPC communications (Telegram, API, etc)
It handles the initialization and cleanup of all enabled rpc modules.
"""

import logging
from collections import deque
from typing import Any, Dict, List, Optional

from freqtrade.constants import Config
from freqtrade.enums import NO_ECHO_MESSAGES, RPCMessageType
from freqtrade.rpc import RPC, RPCHandler
from freqtrade.rpc.rpc_types import RPCSendMsg


logger = logging.getLogger(__name__)


class RPCManager:
    """
    Class to manage RPC objects (Telegram, Discord, Webhook, API Server) for
    communication. Handles message sending, initialization and cleanup of
    RPC modules.
    """

    def __init__(self, freqtrade: Any) -> None:
        """
        Initializes all enabled rpc modules based on the configuration.

        :param freqtrade: Instance of the freqtrade bot
        """
        self.registered_modules: List[RPCHandler] = []
        self._rpc = RPC(freqtrade)
        config = freqtrade.config

        telegram_config = config.get("telegram", {})
        # Enable telegram
        if telegram_config.get("enabled", False):
            logger.info("Enabling rpc.telegram ...")
            try:
                # Import here to avoid loading the module if not enabled
                from freqtrade.rpc.telegram import Telegram

                self.registered_modules.append(Telegram(self._rpc, config))
            except ImportError:
                logger.exception("RPC module not available. Please install freqtrade[rpc] ...")

        # Enable discord
        if config.get("discord", {}).get("enabled", False):
            logger.info("Enabling rpc.discord ...")
            try:
                # Import here to avoid loading the module if not enabled
                from freqtrade.rpc.discord import Discord

                self.registered_modules.append(Discord(self._rpc, config))
            except ImportError:
                logger.exception("RPC module not available. Please install freqtrade[rpc] ...")

        # Enable Webhook
        if config.get("webhook", {}).get("enabled", False):
            logger.info("Enabling rpc.webhook ...")
            from freqtrade.rpc.webhook import Webhook

            self.registered_modules.append(Webhook(self._rpc, config))

        # Enable local rest api server for cmd line control
        if config.get("api_server", {}).get("enabled", False):
            logger.info("Enabling rpc.api_server")
            from freqtrade.rpc.api_server import ApiServer

            apiserver = ApiServer(config)
            apiserver.add_rpc_handler(self._rpc)
            self.registered_modules.append(apiserver)

    def cleanup(self) -> None:
        """Stop and clean up all registered RPC modules."""
        logger.info("Cleaning up rpc modules ...")
        while self.registered_modules:
            mod = self.registered_modules.pop()
            logger.info("Cleaning up rpc.%s ...", mod.name)
            if hasattr(mod, "cleanup"):
                mod.cleanup()
                logger.info("rpc.%s cleaned up.", mod.name)
            else:
                logger.warning("rpc.%s does not implement cleanup method.", mod.name)
            del mod

    def send_msg(self, msg: RPCSendMsg) -> None:
        """
        Send given message to all registered rpc modules.
        A message consists of one or more key value pairs of strings.
        e.g.:
        {
            'status': 'stopping bot'
        }

        :param msg: message to send to rpc modules.
        """
        if not isinstance(msg, dict) or "type" not in msg:
            logger.error("Message is not a valid RPC message. Ignoring.")
            return
        if msg.get("type") not in NO_ECHO_MESSAGES:
            logger.info("Sending rpc message: %s", msg)
        for mod in self.registered_modules:
            logger.debug("Forwarding message to rpc.%s", mod.name)
            try:
                mod.send_msg(msg)
            except NotImplementedError:
                logger.error(f"Message type '{msg['type']}' not implemented by handler {mod.name}.")
            except Exception as e:
                logger.exception("Exception occurred within RPC module %s", mod.name, exc_info=e)

    def process_msg_queue(self, queue: deque) -> None:
        """
        Process all messages in the queue.

        :param queue: deque containing messages to process.
        """
        if not queue:
            return
        if not isinstance(queue, deque):
            logger.error("Queue is not a valid deque. Ignoring.")
            return
        logger.info("Processing %s messages in queue", len(queue))
        while queue:
            msg = queue.popleft()
            if not isinstance(msg, str):
                logger.error("Message is not a valid string. Ignoring.")
                continue
            if msg:
                logger.info("Sending rpc strategy_msg: %s", msg)
                for mod in self.registered_modules:
                    if mod._config.get(mod.name, {}).get("allow_custom_messages", False):
                        try:
                            mod.send_msg(
                                {
                                    "type": RPCMessageType.STRATEGY_MSG,
                                    "msg": msg,
                                }
                            )
                        except Exception as e:
                            logger.exception(
                                "Exception occurred within RPC module %s", mod.name, exc_info=e
                            )
            else:
                logger.warning("Message is empty.")

    def startup_messages(self, config: Config, pairlist, protections) -> None:
        """
        Send startup messages to all registered rpc modules

        :param config: Configuration object.
        :param pairlist: Pairlist object containing trading pairs.
        :param protections: Protections object containing trade protection settings.
        """
        if config["dry_run"]:
            self.send_msg(
                {
                    "type": RPCMessageType.WARNING,
                    "status": "Dry run is enabled. All trades are simulated.",
                }
            )
        stake_currency = config.get("stake_currency")
        stake_amount = config["stake_amount"]
        minimal_roi = config["minimal_roi"]
        stoploss = config["stoploss"]
        trailing_stop = config["trailing_stop"]
        timeframe = config["timeframe"]
        exchange_name = config["exchange"]["name"]
        strategy_name = config.get("strategy", "")
        pos_adjust_enabled = "On" if config["position_adjustment_enable"] else "Off"
        status_msg = (
            f"*Exchange:* `{exchange_name}`\n"
            f"*Stake per trade:* `{stake_amount} {stake_currency}`\n"
            f"*Minimum ROI:* `{minimal_roi}`\n"
            f"*{'Trailing ' if trailing_stop else ''}Stoploss:* `{stoploss}`\n"
            f"*Position adjustment:* `{pos_adjust_enabled}`\n"
            f"*Timeframe:* `{timeframe}`\n"
            f"*Strategy:* `{strategy_name}`"
        )
        self.send_msg(
            {
                "type": RPCMessageType.STARTUP,
                "status": status_msg,
            }
        )
        self.send_msg(
            {
                "type": RPCMessageType.STARTUP,
                "status": f"Searching for {stake_currency} pairs to buy and sell "
                f"based on {pairlist.short_desc()}",
            }
        )
        if len(protections.name_list) > 0:
            prots = "\n".join([p for prot in protections.short_desc() for k, p in prot.items()])
            self.send_msg(
                {"type": RPCMessageType.STARTUP, "status": f"Using Protections: \n{prots}"}
            )
