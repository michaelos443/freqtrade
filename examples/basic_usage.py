"""
Basic usage example for Smart Alert System
"""
from smart_alerts import SmartAlertManager, AlertLevel, AlertChannel


def main():
    """Demonstrate basic alert functionality"""
    
    # Initialize with console output only
    config = {
        "channels": ["console"],
        "profit_threshold": 5.0,
        "loss_threshold": -3.0
    }
    
    alert_manager = SmartAlertManager(config)
    
    # Example 1: Success alert for profitable trade
    alert_manager.send_alert(
        title="Profitable Trade Closed",
        message="BTC/USDT long position closed with 7.5% profit",
        level=AlertLevel.SUCCESS,
        metadata={
            "pair": "BTC/USDT",
            "profit_percent": 7.5,
            "entry_price": 42000,
            "exit_price": 45150
        }
    )
    
    # Example 2: Warning for approaching stop loss
    alert_manager.send_alert(
        title="Stop Loss Warning",
        message="ETH/USDT position approaching stop loss level",
        level=AlertLevel.WARNING,
        metadata={
            "pair": "ETH/USDT",
            "current_loss": -2.8,
            "stop_loss": -3.0
        }
    )
    
    # Example 3: Critical alert for large loss
    alert_manager.send_alert(
        title="Large Loss Detected",
        message="Position closed with significant loss!",
        level=AlertLevel.CRITICAL,
        metadata={
            "pair": "SOL/USDT",
            "loss_percent": -5.2,
            "amount_lost": 250.50
        }
    )
    
    # Example 4: Info alert for market update
    alert_manager.send_alert(
        title="Market Update",
        message="High volume detected on BTC/USDT",
        level=AlertLevel.INFO,
        metadata={
            "pair": "BTC/USDT",
            "volume_increase": "150%"
        }
    )
    
    # Get recent alerts
    print("\n" + "="*50)
    print("Recent Alerts Summary:")
    print("="*50)
    recent = alert_manager.get_recent_alerts(limit=5)
    for i, alert in enumerate(recent, 1):
        print(f"{i}. {alert['title']} - {alert['level']}")


if __name__ == "__main__":
    main()

