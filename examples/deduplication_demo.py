"""
Demo: Smart Alert Deduplication Feature
Shows how the deduplication system prevents alert fatigue
"""
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from smart_alerts import SmartAlertManager, AlertLevel


def main():
    print("=" * 60)
    print("Smart Alert Deduplication Demo")
    print("=" * 60)
    
    # Configure alert manager with deduplication
    config = {
        "channels": ["console"],
        "enable_deduplication": True,
        "dedup_window_minutes": 1  # Short window for demo purposes
    }
    
    alert_manager = SmartAlertManager(config)
    
    print("\n1. Sending initial alert...")
    alert_manager.send_alert(
        "Price Alert",
        "BTC reached $50,000",
        AlertLevel.INFO
    )
    
    print("\n2. Attempting to send duplicate alert (should be blocked)...")
    alert_manager.send_alert(
        "Price Alert",
        "BTC reached $50,000",
        AlertLevel.INFO
    )
    
    print("\n3. Sending different alert (should go through)...")
    alert_manager.send_alert(
        "Price Alert",
        "ETH reached $3,000",
        AlertLevel.INFO
    )
    
    print("\n4. Sending CRITICAL alert (bypasses deduplication)...")
    alert_manager.send_alert(
        "System Error",
        "Trading bot crashed!",
        AlertLevel.CRITICAL
    )
    
    print("\n5. Sending same CRITICAL alert again (still goes through)...")
    alert_manager.send_alert(
        "System Error",
        "Trading bot crashed!",
        AlertLevel.CRITICAL
    )
    
    print("\n6. Manually bypassing deduplication...")
    alert_manager.send_alert(
        "Price Alert",
        "BTC reached $50,000",
        AlertLevel.INFO,
        bypass_dedup=True
    )
    
    print("\n7. Checking deduplication statistics...")
    stats = alert_manager.get_dedup_stats()
    print(f"\nDeduplication Stats:")
    print(f"  - Active fingerprints: {stats['active_fingerprints']}")
    print(f"  - Dedup enabled: {stats['dedup_enabled']}")
    print(f"  - Dedup window: {stats['dedup_window_minutes']} minutes")
    print(f"  - Total alerts sent: {stats['total_alerts_sent']}")
    
    print("\n8. Waiting for dedup window to expire...")
    print("   (Sleeping for 61 seconds...)")
    time.sleep(61)
    
    print("\n9. Sending previously blocked alert (should go through now)...")
    alert_manager.send_alert(
        "Price Alert",
        "BTC reached $50,000",
        AlertLevel.INFO
    )
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

