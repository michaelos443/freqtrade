# Smart Alert System 🔔

An intelligent notification system for trading bots that sends alerts via multiple channels.

## Features

- **Multiple Channels**: Console, Telegram, Email, Discord
- **Alert Levels**: INFO, WARNING, CRITICAL, SUCCESS
- **Configurable Thresholds**: Set custom profit/loss thresholds
- **Alert History**: Track all sent alerts
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

## Example Use Cases

- Large profit/loss notifications
- Unusual market movements
- Strategy trigger alerts
- System health warnings
- Daily/weekly summaries

