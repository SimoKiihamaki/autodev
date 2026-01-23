"""Interactive features for support-mode monitoring.

Provides keyboard shortcuts, desktop notifications, and enhanced user experience
during continuous monitoring loops.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum

from .config_file import NotificationConfig
from .command import run_cmd

logger = logging.getLogger(__name__)


class NotificationLevel(str, Enum):
    """Notification urgency levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


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

        # Escape strings for AppleScript to prevent injection
        # Backslashes and double quotes must be escaped with backslash
        def _escape_applescript(s: str) -> str:
            return s.replace("\\", "\\\\").replace('"', '\\"')

        safe_title = _escape_applescript(title)
        safe_message = _escape_applescript(message)
        safe_sound = _escape_applescript(sound)

        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{safe_message}" with title "{safe_title}" sound name "{safe_sound}"',
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
    import os

    # Try toast.exe first (part of Windows 10+ SDK)
    try:
        result = subprocess.run(
            ["toast", "-t", title, "-m", message],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            return
    except (OSError, subprocess.SubprocessError):
        # toast.exe not available, try PowerShell fallback
        pass

    # Fallback to PowerShell BurntToast notification
    # Pass title/message via environment variables to prevent injection
    try:
        ps_script = """
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
        $template = @"
        <toast><visual><binding template='ToastGeneric'><text>$env:SUPPORT_MODE_TITLE</text><text>$env:SUPPORT_MODE_MESSAGE</text></binding></visual></toast>
        "@
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($template)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('support-mode')
        $notifier.Show($toast)
        """
        env = {
            **os.environ,
            "SUPPORT_MODE_TITLE": title,
            "SUPPORT_MODE_MESSAGE": message,
        }
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=False,
            capture_output=True,
            env=env,
        )
    except (OSError, subprocess.SubprocessError):
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
    timeout_s = 10
    try:
        if config.webhook_format == "json":
            import json

            payload = json.dumps(
                {"title": title, "message": message, "level": level.value}
            )
            run_cmd(
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
                timeout=timeout_s,
            )
        else:  # text format
            run_cmd(
                ["curl", "-X", "POST", "-d", f"{title}: {message}", config.webhook_url],
                check=False,
                timeout=timeout_s,
            )
    except (OSError, subprocess.SubprocessError, ImportError):
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

    def is_enabled(self) -> bool:
        """Check if key handling is enabled."""
        return self._enabled and self._can_use_nonblocking()

    def _can_use_nonblocking(self) -> bool:
        """Check if platform supports non-blocking key input."""
        # Non-blocking input requires terminal support
        return self._is_terminal()

    def _is_terminal(self) -> bool:
        """Check if running in an interactive terminal."""
        return sys.stdin.isatty()

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
        """Poll for key on Unix-like systems.

        Switches TTY to raw mode to enable single-key detection without
        waiting for Enter, then restores original settings.
        """
        import select
        import termios

        try:
            old_settings = termios.tcgetattr(sys.stdin)
        except (OSError, termios.error):
            # Not a TTY or termios not available
            return None

        try:
            # Set raw mode (cbreak) - disable line buffering
            new_settings = termios.tcgetattr(sys.stdin)
            new_settings[3] = new_settings[3] & ~termios.ICANON
            # Also disable echo so the key isn't displayed
            new_settings[3] = new_settings[3] & ~termios.ECHO
            new_settings[6][termios.VMIN] = 0  # Non-blocking read
            new_settings[6][termios.VTIME] = 0  # No inter-character timer
            termios.tcsetattr(sys.stdin, termios.TCSANOW, new_settings)

            # Check if data is available
            readable, _, _ = select.select([sys.stdin], [], [], timeout_ms / 1000)
            if readable:
                try:
                    return sys.stdin.read(1)
                except OSError:
                    return None
            return None
        finally:
            # Always restore original TTY settings
            try:
                termios.tcsetattr(sys.stdin, termios.TCSANOW, old_settings)
            except (OSError, termios.error):
                pass  # Best effort restore

    def _poll_windows(self) -> str | None:
        """Poll for key on Windows.

        Extended keys (arrows, function keys) return a prefix byte (0x00 or 0xe0)
        followed by the actual key code. These are ignored as only single-letter
        shortcuts are supported.
        """
        try:
            import msvcrt

            if msvcrt.kbhit():
                ch = msvcrt.getch()
                # Extended keys (arrows, function keys) start with 0x00 or 0xe0
                # Consume and ignore the following key code byte
                if ch in (b"\x00", b"\xe0"):
                    msvcrt.getch()  # Consume the extended key code
                    return None
                # Regular ASCII key - safe to decode
                return ch.decode("utf-8")
        except (ImportError, UnicodeDecodeError, OSError):
            # msvcrt not available or decode error from unexpected input
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
            if platform.system() == "Windows":
                import msvcrt

                ch = msvcrt.getch()
                # Extended keys (arrows, function keys) start with 0x00 or 0xe0
                if ch in (b"\x00", b"\xe0"):
                    msvcrt.getch()  # Consume the extended key code
                    # For extended keys, wait for a regular key
                    ch = msvcrt.getch()
                return ch.decode("utf-8").lower()
            else:
                import termios

                # Save and set raw mode for wait_for_key
                old_settings = None
                try:
                    old_settings = termios.tcgetattr(sys.stdin)
                    new_settings = termios.tcgetattr(sys.stdin)
                    new_settings[3] = new_settings[3] & ~termios.ICANON
                    new_settings[3] = new_settings[3] & ~termios.ECHO
                    new_settings[6][
                        termios.VMIN
                    ] = 1  # Blocking read until at least 1 char
                    new_settings[6][termios.VTIME] = 0
                    termios.tcsetattr(sys.stdin, termios.TCSANOW, new_settings)

                    ch = sys.stdin.read(1).lower()
                    return ch
                finally:
                    # Always restore original settings
                    if old_settings is not None:
                        try:
                            termios.tcsetattr(sys.stdin, termios.TCSANOW, old_settings)
                        except (OSError, termios.error):
                            # Best effort restore - terminal may be in bad state
                            pass
        except (OSError, ImportError, UnicodeDecodeError):
            return ""

    def disable(self) -> None:
        """Disable key handling."""
        self._enabled = False

    def enable(self) -> None:
        """Enable key handling."""
        self._enabled = True
