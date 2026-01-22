"""Interactive features for support-mode monitoring.

Provides keyboard shortcuts, desktop notifications, and enhanced user experience
during continuous monitoring loops.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class NotificationLevel(str, Enum):
    """Notification urgency levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class NotificationConfig:
    """Configuration for desktop notifications."""

    enabled: bool = True
    use_webhook: bool = False
    webhook_url: str = ""
    webhook_format: str = "json"  # json or text


def send_notification(
    title: str,
    message: str,
    level: NotificationLevel = NotificationLevel.INFO,
    config: NotificationConfig | None = None,
) -> None:
    """Send a desktop notification.

    Args:
        title: Notification title.
        message: Notification message body.
        level: Notification urgency level.
        config: Notification configuration.
    """
    config = config or NotificationConfig()
    if not config.enabled:
        return

    # Try desktop notification tools based on platform
    system = platform.system()

    if system == "Darwin":  # macOS
        _notify_macos(title, message, level)
    elif system == "Linux":
        _notify_linux(title, message, level)
    elif system == "Windows":
        _notify_windows(title, message)

    # Send webhook if configured
    if config.use_webhook and config.webhook_url:
        _send_webhook(title, message, level, config)


def _notify_macos(title: str, message: str, level: NotificationLevel) -> None:
    """Send notification on macOS using osascript."""
    try:
        # Map level to sound name
        sounds = {
            NotificationLevel.INFO: "Glass",
            NotificationLevel.WARNING: "Basso",
            NotificationLevel.ERROR: "Sosumi",
        }
        sound = sounds.get(level, "Glass")

        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}" sound name "{sound}"',
            ],
            check=False,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("Could not send macOS notification")


def _notify_linux(title: str, message: str, level: NotificationLevel) -> None:
    """Send notification on Linux using notify-send."""
    try:
        # Map level to urgency
        urgency = {
            NotificationLevel.INFO: "low",
            NotificationLevel.WARNING: "normal",
            NotificationLevel.ERROR: "critical",
        }.get(level, "low")

        subprocess.run(
            [
                "notify-send",
                "-u",
                urgency,
                "-i",
                "utilities-terminal",
                title,
                message,
            ],
            check=False,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        logger.debug("Could not send Linux notification")


def _notify_windows(title: str, message: str) -> None:
    """Send notification on Windows using toast.exe or PowerShell."""
    # Try toast.exe first (part of Windows 10+ SDK)
    try:
        subprocess.run(
            ["toast", "-t", title, "-m", message],
            check=False,
            capture_output=True,
            shell=True,
        )
        return
    except (OSError, subprocess.SubprocessError):
        pass

    # Fallback to PowerShell BurntToast notification
    try:
        ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
        $template = @"
        <toast><visual><binding template='ToastGeneric'><text>{title}</text><text>{message}</text></binding></visual></toast>
        "@
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('support-mode')
        $notifier.Show($toast)
        """
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=False,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessProcess):
        logger.debug("Could not send Windows notification")


def _send_webhook(
    title: str,
    message: str,
    level: NotificationLevel,
    config: NotificationConfig,
) -> None:
    """Send notification via webhook.

    Args:
        title: Notification title.
        message: Notification message.
        level: Notification urgency level.
        config: Notification configuration with webhook settings.
    """
    try:
        if config.webhook_format == "json":
            import json

            payload = json.dumps(
                {"title": title, "message": message, "level": level.value}
            )
            subprocess.run(
                [
                    "curl",
                    "-X",
                    "POST",
                    "-H",
                    "Content-Type: application/json",
                    "-d",
                    payload,
                    config.webhook_url,
                ],
                check=False,
                capture_output=True,
            )
        else:  # text format
            subprocess.run(
                ["curl", "-X", "POST", "-d", f"{title}: {message}", config.webhook_url],
                check=False,
                capture_output=True,
            )
    except (OSError, subprocess.SubprocessProcess, ImportError):
        logger.warning("Could not send webhook notification")


@dataclass
class KeyEvent:
    """A key press event during monitoring."""

    key: str
    timestamp: float


class KeyHandler:
    """Handle keyboard shortcuts during monitoring loop.

    Supports single-key shortcuts for common actions:
    - s: Show summary
    - t: Show tracker status
    - c: Show recent commits
    - q: Quit
    - r: Refresh immediately
    """

    def __init__(self) -> None:
        """Initialize key handler."""
        self._enabled = True
        self._last_key_check = 0.0
        self._pending_key: str | None = None

    def is_enabled(self) -> bool:
        """Check if key handling is enabled."""
        return self._enabled and self._can_use_nonblocking()

    def _can_use_nonblocking(self) -> bool:
        """Check if platform supports non-blocking key input."""
        # Non-blocking input requires terminal support
        return self._is_terminal()

    def _is_terminal(self) -> bool:
        """Check if running in an interactive terminal."""
        return sys.stdin.isatty() if "sys" in globals() else False

    def poll_key(self, timeout_ms: int = 100) -> str | None:
        """Poll for a single keypress without blocking.

        Args:
            timeout_ms: Milliseconds to wait for input.

        Returns:
            Pressed key character or None if no key pressed.
        """
        if not self.is_enabled():
            return None

        # On Unix, use select with sys.stdin
        # On Windows, use msvcrt
        try:
            if platform.system() == "Windows":
                return self._poll_windows()
            else:
                return self._poll_unix(timeout_ms)
        except (OSError, ImportError):
            return None

    def _poll_unix(self, timeout_ms: int) -> str | None:
        """Poll for key on Unix-like systems."""
        import select
        import sys

        # Check if data is available
        readable, _, _ = select.select([sys.stdin], [], [], timeout_ms / 1000)
        if readable:
            return sys.stdin.read(1)
        return None

    def _poll_windows(self) -> str | None:
        """Poll for key on Windows."""
        try:
            import msvcrt

            if msvcrt.kbhit():
                return msvcrt.getch().decode("utf-8")
        except ImportError:
            pass
        return None

    def wait_for_key(self, prompt: str = "Press a key...") -> str:
        """Wait for a keypress from user.

        Args:
            prompt: Prompt to display.

        Returns:
            Pressed key character.
        """
        print(prompt, flush=True, end=" ")
        try:
            import sys

            if platform.system() == "Windows":
                import msvcrt

                return msvcrt.getch().decode("utf-8").lower()
            else:
                return sys.stdin.read(1).lower()
        except (OSError, ImportError):
            return ""

    def disable(self) -> None:
        """Disable key handling."""
        self._enabled = False

    def enable(self) -> None:
        """Enable key handling."""
        self._enabled = True


# Import sys at module level for poll_unix
import sys
