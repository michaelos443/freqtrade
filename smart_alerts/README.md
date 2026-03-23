# Smart Alert System 🔔

An intelligent notification system for trading bots that sends alerts via multiple channels.

## Features

- **Multiple Channels**: Console, Telegram, Email, Discord
- **Alert Levels**: INFO, WARNING, CRITICAL, SUCCESS
- **Configurable Thresholds**: Set custom profit/loss thresholds
- **Alert History**: Track all sent alerts
- **Smart Deduplication**: Prevent duplicate alerts within configurable time windows
- **Alert Filtering**: Reduce alert fatigue with intelligent filtering
- **Easy Integration**: Simple API for quick setup

## Quick Start

```python
from smart_alerts import SmartAlertManager, AlertLevel

# Initialize the alert manager
config = {
    "channels": ["console"],
    "profit_threshold": 5.0,
    "loss_threshold": -3.0
}

alert_manager = SmartAlertManager(config)

# Send an alert
alert_manager.send_alert(
    title="High Profit Trade",
    message="BTC/USDT trade closed with 7.5% profit!",
    level=AlertLevel.SUCCESS,
    metadata={"pair": "BTC/USDT", "profit": 7.5}
)
```

## Configuration

Copy `config.example.json` to `config.json` and update with your credentials.

## Alert Levels

- **INFO**: General information
- **WARNING**: Important events requiring attention
- **CRITICAL**: Urgent issues requiring immediate action
- **SUCCESS**: Positive outcomes (profitable trades, etc.)

## Supported Channels

- **Console**: Terminal output (always available)
- **Telegram**: Bot notifications (requires bot token)
- **Email**: SMTP email alerts
- **Discord**: Webhook notifications

## Smart Deduplication

The alert system includes intelligent deduplication to prevent alert fatigue:

```python
# Configure deduplication
config = {
    "channels": ["console"],
    "enable_deduplication": True,  # Enable/disable deduplication
    "dedup_window_minutes": 5       # Time window for duplicate detection
}

alert_manager = SmartAlertManager(config)

# This alert will be sent
alert_manager.send_alert("Price Alert", "BTC reached $50,000", AlertLevel.INFO)

# This duplicate will be blocked (within 5 minutes)
alert_manager.send_alert("Price Alert", "BTC reached $50,000", AlertLevel.INFO)

# Critical alerts always bypass deduplication
alert_manager.send_alert("URGENT", "System failure!", AlertLevel.CRITICAL)

# Or manually bypass deduplication
alert_manager.send_alert("Important", "Must send", bypass_dedup=True)

# Get deduplication statistics
stats = alert_manager.get_dedup_stats()
print(stats)  # {'active_fingerprints': 2, 'dedup_enabled': True, ...}
```

## Example Use Cases

- Large profit/loss notifications
- Unusual market movements
- Strategy trigger alerts
- System health warnings
- Daily/weekly summaries

