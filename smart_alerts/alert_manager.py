"""
Smart Alert System for Trading Bot
Sends intelligent notifications via multiple channels
"""
from enum import Enum
from typing import Dict, List, Optional
from datetime import datetime
import json


class AlertLevel(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SUCCESS = "success"


class AlertChannel(Enum):
    """Available notification channels"""
    TELEGRAM = "telegram"
    EMAIL = "email"
    DISCORD = "discord"
    CONSOLE = "console"


class Alert:
    """Represents a trading alert"""
    
    def __init__(
        self,
        title: str,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
        metadata: Optional[Dict] = None
    ):
        self.title = title
        self.message = message
        self.level = level
        self.metadata = metadata or {}
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict:
        """Convert alert to dictionary"""
        return {
            "title": self.title,
            "message": self.message,
            "level": self.level.value,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }


class SmartAlertManager:
    """Manages and routes alerts to appropriate channels"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.enabled_channels = self._load_channels()
        self.alert_history: List[Alert] = []
        self.alert_rules = self._load_rules()
    
    def _load_channels(self) -> List[AlertChannel]:
        """Load enabled notification channels from config"""
        channels = self.config.get("channels", ["console"])
        return [AlertChannel(ch) for ch in channels if ch in [c.value for c in AlertChannel]]
    
    def _load_rules(self) -> Dict:
        """Load alert rules and thresholds"""
        return {
            "profit_threshold": self.config.get("profit_threshold", 5.0),
            "loss_threshold": self.config.get("loss_threshold", -3.0),
            "volume_spike_threshold": self.config.get("volume_spike", 2.0),
            "max_alerts_per_hour": self.config.get("max_alerts_per_hour", 10)
        }
    
    def send_alert(
        self,
        title: str,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
        metadata: Optional[Dict] = None,
        channels: Optional[List[AlertChannel]] = None
    ) -> bool:
        """Send an alert through specified channels"""
        alert = Alert(title, message, level, metadata)
        self.alert_history.append(alert)
        
        # Use specified channels or default to all enabled
        target_channels = channels or self.enabled_channels
        
        success = True
        for channel in target_channels:
            try:
                self._send_to_channel(alert, channel)
            except Exception as e:
                print(f"Failed to send alert to {channel.value}: {e}")
                success = False
        
        return success
    
    def _send_to_channel(self, alert: Alert, channel: AlertChannel):
        """Route alert to specific channel"""
        if channel == AlertChannel.CONSOLE:
            self._send_console(alert)
        elif channel == AlertChannel.TELEGRAM:
            self._send_telegram(alert)
        elif channel == AlertChannel.EMAIL:
            self._send_email(alert)
        elif channel == AlertChannel.DISCORD:
            self._send_discord(alert)
    
    def _send_console(self, alert: Alert):
        """Print alert to console"""
        icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨", "success": "✅"}
        print(f"\n{icon.get(alert.level.value, '📢')} [{alert.level.value.upper()}] {alert.title}")
        print(f"   {alert.message}")
        print(f"   Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        if alert.metadata:
            print(f"   Details: {json.dumps(alert.metadata, indent=2)}")
    
    def _send_telegram(self, alert: Alert):
        """Send alert via Telegram (placeholder)"""
        # TODO: Implement Telegram bot integration
        print(f"[Telegram] Would send: {alert.title}")
    
    def _send_email(self, alert: Alert):
        """Send alert via Email (placeholder)"""
        # TODO: Implement email integration
        print(f"[Email] Would send: {alert.title}")
    
    def _send_discord(self, alert: Alert):
        """Send alert via Discord webhook (placeholder)"""
        # TODO: Implement Discord webhook
        print(f"[Discord] Would send: {alert.title}")
    
    def get_recent_alerts(self, limit: int = 10) -> List[Dict]:
        """Get recent alerts"""
        return [alert.to_dict() for alert in self.alert_history[-limit:]]

