"""
Main Freqtrade worker class.
"""

import logging
from time import perf_counter, sleep, time
import traceback
from collections.abc import Callable
from os import getpid
from typing import Any, Optional, Dict

import sdnotify

from freqtrade import __version__
from freqtrade.configuration import Configuration
from freqtrade.constants import PROCESS_THROTTLE_SECS, RETRY_TIMEOUT, Config
from freqtrade.enums import RPCMessageType, State
from freqtrade.exceptions import OperationalException, TemporaryError
from freqtrade.exchange import timeframe_to_next_date
from freqtrade.freqtradebot import FreqtradeBot


logger = logging.getLogger(__name__)


class Worker:
    """
    Freqtradebot worker class for managing bot operations, including state transitions,
    systemd notifications, and periodic heartbeats.

    This class is responsible for initializing the bot, running the main loop, and
    handling state transitions between different states of the bot. It also provides
    systemd notifications and periodic heartbeats to ensure proper operation.
    """

    def __init__(self, args: Dict[str, Any], config: Config | None = None) -> None:
        """
        Initializes the Worker instance with the provided arguments and configuration.
        """
        logger.info(f"Starting worker {__version__}")
        self._args = args
        self._config = config
        self._initialize(False)
        self._heartbeat_msg: float = 0

        # Tell systemd that we completed initialization phase
        self._notify("READY=1")

    def _load_configuration(self) -> Config:
        return Configuration(self._args, None).get_config()

    def _initialize(self, reconfig: bool) -> None:
        """
        Initializes bot components and configurations. Can be called for reconfiguration.

        If reconfig is True or the current config is None, the method will reload
        the configuration.

        :param reconfig: whether to reload the configuration or not
        """
        if reconfig or self._config is None:
            # Load configuration
            self._config = self._load_configuration()

        # Initialize the bot with the loaded configuration
        self.freqtrade = FreqtradeBot(self._config)
        internals_config = self._config.get("internals")
        if internals_config is None:
            internals_config = {}
        process_throttle_secs = internals_config.get("process_throttle_secs")
        
        self._heartbeat_interval = internals_config.get("heartbeat_interval", 60)
        self._throttle_secs = process_throttle_secs if process_throttle_secs else PROCESS_THROTTLE_SECS
        # Initialize systemd notifier if enabled in the configuration
        self._sd_notify = (
            sdnotify.SystemdNotifier()
            if self._config.get("internals", {}).get("sd_notify", False)
            else None
        )

    def _notify(self, message: str) -> None:
        """
        sends a message to systemd using sdnotify if enabled.

        :param message: message to send to systemd
        """
        if self._sd_notify:
            logger.debug(f"sd_notify: {message}")
            self._sd_notify.notify(message)

    def run(self) -> None:
        state = None
        while True:
            state = self._worker(old_state=state)
            if state == State.RELOAD_CONFIG:
                self._reconfigure()

    def _handle_state_transition(self, state: State) -> None:
        if state == State.RUNNING:
            self.freqtrade.startup()
        elif state == State.STOPPED:
            self.freqtrade.check_for_open_trades()

    def _worker(self, old_state: State | None) -> State:
        """
        The main routine that runs each throttling iteration and handles the states.
        :param old_state: the previous service state from the previous call
        :return: current service state
        """
        state = self.freqtrade.state

        # Log state transition
        if state != old_state:
            if old_state != State.RELOAD_CONFIG:
                self.freqtrade.notify_status(f"{state.name.lower()}")

            logger.info(
                f"Changing state{f' from {old_state.name}' if old_state else ''} to: {state.name}"
            )
            self._handle_state_transition(state)

            # Reset heartbeat timestamp to log the heartbeat message at
            # first throttling iteration when the state changes
            self._heartbeat_msg = 0

        if state == State.STOPPED:
            # Ping systemd watchdog before sleeping in the stopped state
            self._notify("WATCHDOG=1\nSTATUS=State: STOPPED.")

            self._throttle(func=self._process_stopped, throttle_secs=self._throttle_secs)

        elif state == State.RUNNING:
            # Ping systemd watchdog before throttling
            self._notify("WATCHDOG=1\nSTATUS=State: RUNNING.")

            # Use an offset of 1s to ensure a new candle has been issued
            self._throttle(
                func=self._process_running,
                throttle_secs=self._throttle_secs,
                timeframe=self._config["timeframe"] if self._config else None,
                timeframe_offset=1,
            )

        if self._heartbeat_interval:
            current_time = perf_counter()
            if (current_time - self._heartbeat_msg) > self._heartbeat_interval:
                version = __version__
                self._log_heartbeat(now, version, state)

        return state

    def _log_heartbeat(self, now: float, version: str, state: State) -> None:
        strategy_version = self.freqtrade.strategy.version()
        if strategy_version is not None:
            version += ", strategy_version: " + strategy_version
        logger.info(f"Bot heartbeat. PID={getpid()}, version='{version}', state='{state.name}'")
        self._heartbeat_msg = now

    def _throttle(
        self,
        func: Callable[..., Any],
        throttle_secs: float,
        timeframe: str | None = None,
        timeframe_offset: float = 1.0,
        *args,
        **kwargs,
    ) -> Any:
        """
        Throttles the given callable that it
        takes at least `min_secs` to finish execution.
        :param func: Any callable
        :param throttle_secs: throttling iteration execution time limit in seconds
        :param timeframe: ensure iteration is executed at the beginning of the next candle.
        :param timeframe_offset: offset in seconds to apply to the next candle time.
        :return: Any (result of execution of func)
        """
        last_throttle_start_time = perf_counter()
        logger.debug("========================================")
        result = func(*args, **kwargs)
        time_passed = perf_counter() - last_throttle_start_time
        sleep_duration = throttle_secs - time_passed
        if timeframe:
            next_tf = timeframe_to_next_date(timeframe)
            # Maximum throttling should be until new candle arrives
            # Offset is added to ensure a new candle has been issued.
            next_tft = next_tf.timestamp() - time()
            next_tf_with_offset = next_tft + timeframe_offset
            if next_tft < sleep_duration and sleep_duration < next_tf_with_offset:
                # Avoid hitting a new loop between the new candle and the candle with offset
                sleep_duration = next_tf_with_offset
            sleep_duration = min(sleep_duration, next_tf_with_offset)
        if sleep_duration < 0:
            sleep_duration = 0
        # next_iter = datetime.now(timezone.utc) + timedelta(seconds=sleep_duration)

        logger.debug(
            f"Throttling with '{func.__name__}()': sleep for {sleep_duration:.2f} s, "
            f"last iteration took {time_passed:.2f} s."
            #  f"next: {next_iter}"
        )
        self._sleep(sleep_duration)
        return result

    @staticmethod
    def _sleep(sleep_duration: float) -> None:
        """Local sleep method - to improve testability"""
        sleep(sleep_duration)

    def _process_stopped(self) -> None:
        self.freqtrade.process_stopped()

    def _process_running(self) -> None:
        try:
            self.freqtrade.process()
        except TemporaryError as error:
            logger.exception(
                f"TemporaryError encountered: {error}, retrying in {RETRY_TIMEOUT} seconds..."
            )
            self._sleep(RETRY_TIMEOUT)
        except OperationalException:
            tb = traceback.format_exc()
            hint = "Issue `/start` if you think it is safe to restart."

            self.freqtrade.notify_status(
                f"*OperationalException:*\n```\n{tb}```\n {hint}", msg_type=RPCMessageType.EXCEPTION
            )

            logger.exception("OperationalException. Stopping trader ...")
            self.freqtrade.state = State.STOPPED

    def _reconfigure(self) -> None:
        """
        Cleans up current freqtradebot instance, reloads the configuration and
        replaces it with the new instance
        """
        # Tell systemd that we initiated reconfiguration
        self._notify("RELOADING=1")

        # Clean up current freqtrade modules
        self.freqtrade.cleanup()

        # Load and validate config and create new instance of the bot
        self._initialize(True)

        self.freqtrade.notify_status("config reloaded")

        # Tell systemd that we completed reconfiguration
        self._notify("READY=1")

    def exit(self) -> None:
        # Send a message to systemd that we are about to exit
        self._notify("STOPPING=1")

        if self.freqtrade:
            self.freqtrade.notify_status("process died")
            self.freqtrade.cleanup()
        self.freqtrade = None        
