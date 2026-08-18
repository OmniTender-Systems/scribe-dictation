"""App profiling and smart foreground window detection for Scribe Dictation.

Detects active foreground application on Windows, macOS, and Linux, and resolves
application process names or window titles to context-specific formatting modes
(e.g., IDEs -> code_comment, email clients -> email, chat apps -> clean,
document editors -> meeting_notes/bullets).
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    from PySide6.QtCore import QSettings
except ImportError:
    QSettings = None  # type: ignore

from scribe_dictation.formatters.modes import (
    BUILTIN_MODES,
    CLEAN_MODE,
    CODE_COMMENT_MODE,
    EMAIL_MODE,
    MEETING_NOTES_MODE,
    BULLETS_MODE,
    RAW_MODE,
)

SETTINGS_APP_PROFILES = "app_profiles_config"
SETTINGS_PROFILES_ENABLED = "app_profiles_enabled"
SETTINGS_PROFILES_FALLBACK = "app_profiles_fallback_mode"


@dataclass
class AppProfile:
    """Represents a rule mapping an application or window to a formatting mode."""

    app_identifier: str  # e.g., "code.exe", "outlook.exe", "Slack"
    mode_id: str  # e.g., "code_comment", "email", "clean", "meeting_notes"
    enabled: bool = True
    description: str = ""
    match_type: str = "process"  # "process", "title", "contains", "regex"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppProfile:
        return cls(
            app_identifier=str(data.get("app_identifier", "")).strip(),
            mode_id=str(data.get("mode_id", RAW_MODE.id)).strip(),
            enabled=bool(data.get("enabled", True)),
            description=str(data.get("description", "")).strip(),
            match_type=str(data.get("match_type", "process")).strip(),
        )


# Default built-in application mappings
DEFAULT_APP_PROFILES: List[AppProfile] = [
    # IDEs and Code Editors -> code_comment
    AppProfile("code.exe", CODE_COMMENT_MODE.id, True, "Visual Studio Code", "process"),
    AppProfile("cursor.exe", CODE_COMMENT_MODE.id, True, "Cursor AI Editor", "process"),
    AppProfile("windsurf.exe", CODE_COMMENT_MODE.id, True, "Windsurf IDE", "process"),
    AppProfile("pycharm64.exe", CODE_COMMENT_MODE.id, True, "PyCharm", "process"),
    AppProfile("pycharm.exe", CODE_COMMENT_MODE.id, True, "PyCharm", "process"),
    AppProfile("idea64.exe", CODE_COMMENT_MODE.id, True, "IntelliJ IDEA", "process"),
    AppProfile("idea.exe", CODE_COMMENT_MODE.id, True, "IntelliJ IDEA", "process"),
    AppProfile("devenv.exe", CODE_COMMENT_MODE.id, True, "Visual Studio", "process"),
    AppProfile(
        "sublime_text.exe", CODE_COMMENT_MODE.id, True, "Sublime Text", "process"
    ),
    # Email Clients -> email
    AppProfile("outlook.exe", EMAIL_MODE.id, True, "Microsoft Outlook", "process"),
    AppProfile(
        "thunderbird.exe", EMAIL_MODE.id, True, "Mozilla Thunderbird", "process"
    ),
    AppProfile("mail.exe", EMAIL_MODE.id, True, "Windows Mail / Apple Mail", "process"),
    # Chat & Messaging Apps -> clean
    AppProfile("slack.exe", CLEAN_MODE.id, True, "Slack", "process"),
    AppProfile("discord.exe", CLEAN_MODE.id, True, "Discord", "process"),
    AppProfile("teams.exe", CLEAN_MODE.id, True, "Microsoft Teams", "process"),
    AppProfile("ms-teams.exe", CLEAN_MODE.id, True, "Microsoft Teams (New)", "process"),
    # Document & Notes -> meeting_notes or bullets
    AppProfile("winword.exe", MEETING_NOTES_MODE.id, True, "Microsoft Word", "process"),
    AppProfile("notion.exe", MEETING_NOTES_MODE.id, True, "Notion", "process"),
    AppProfile("obsidian.exe", BULLETS_MODE.id, True, "Obsidian Notes", "process"),
]


# ---------------------------------------------------------------------------
# Foreground Window & Process Detection Engine
# ---------------------------------------------------------------------------


def detect_active_window(
    hwnd: Optional[int] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Detect the active foreground window's process name and window title.

    Args:
        hwnd: Optional window handle. If provided on Windows, inspects this handle
              instead of calling GetForegroundWindow().

    Returns:
        (process_name, window_title), e.g. ("code.exe", "app.py - Visual Studio Code")
        or (None, None) if detection fails or is unsupported.
    """
    if sys.platform == "win32":
        return _detect_active_window_windows(hwnd)
    elif sys.platform == "darwin":
        return _detect_active_window_macos()
    elif sys.platform.startswith("linux"):
        return _detect_active_window_linux()
    return None, None


def _detect_active_window_windows(
    target_hwnd: Optional[int] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Windows-specific foreground window and process name detection using ctypes."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        hwnd = target_hwnd if target_hwnd else user32.GetForegroundWindow()
        if not hwnd or not user32.IsWindow(hwnd):
            return None, None

        # 1. Window Title
        title_length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if title_length > 0:
            title_buf = ctypes.create_unicode_buffer(title_length + 1)
            user32.GetWindowTextW(hwnd, title_buf, title_length + 1)
            title = title_buf.value

        # 2. Process ID
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return None, title or None

        # 3. Process Name
        process_name = None
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_proc = kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if h_proc:
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(
                    h_proc, 0, buf, ctypes.byref(size)
                ):
                    full_path = buf.value
                    process_name = os.path.basename(full_path)
            finally:
                kernel32.CloseHandle(h_proc)

        # Fallback to psutil if available and process_name was not retrieved
        if not process_name:
            try:
                import psutil  # type: ignore

                proc = psutil.Process(pid.value)
                process_name = proc.name()
            except Exception:
                pass

        return process_name, title or None
    except Exception:
        return None, None


def _detect_active_window_macos() -> Tuple[Optional[str], Optional[str]]:
    """macOS-specific active application detection using AppleScript / AppKit."""
    try:
        import subprocess

        script = 'tell application "System Events" to get {name, name of window 1} of (first process whose frontmost is true)'
        res = subprocess.run(
            ["osascript", "-e", script], capture_output=True, text=True, timeout=1.0
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.strip().split(", ")]
            proc_name = parts[0] if parts else None
            title = parts[1] if len(parts) > 1 else None
            return proc_name, title
    except Exception:
        pass
    return None, None


def _detect_active_window_linux() -> Tuple[Optional[str], Optional[str]]:
    """Linux active window detection using xdotool if available."""
    try:
        import subprocess

        res_id = subprocess.run(
            ["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=1.0
        )
        if res_id.returncode == 0 and res_id.stdout.strip():
            win_id = res_id.stdout.strip()
            res_name = subprocess.run(
                ["xdotool", "getwindowname", win_id],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            res_pid = subprocess.run(
                ["xdotool", "getwindowpid", win_id],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            title = res_name.stdout.strip() if res_name.returncode == 0 else None
            proc_name = None
            if res_pid.returncode == 0 and res_pid.stdout.strip():
                pid = res_pid.stdout.strip()
                try:
                    with open(f"/proc/{pid}/comm", "r") as f:
                        proc_name = f.read().strip()
                except Exception:
                    pass
            return proc_name, title
    except Exception:
        pass
    return None, None


# ---------------------------------------------------------------------------
# App Profile Manager
# ---------------------------------------------------------------------------


class AppProfileManager:
    """Manages application-to-formatting-mode profiles and context resolution."""

    def __init__(
        self,
        settings: Optional[Any] = None,
        enabled: bool = True,
        fallback_mode: str = RAW_MODE.id,
    ) -> None:
        self.settings = settings
        self.enabled = enabled
        self.fallback_mode = fallback_mode
        self._profiles: List[AppProfile] = []

        if self.settings is not None:
            self.load_from_settings(self.settings)
        else:
            self.reset_to_defaults()

    @property
    def profiles(self) -> List[AppProfile]:
        return list(self._profiles)

    def reset_to_defaults(self) -> None:
        """Reset profiles to the default built-in profile mappings."""
        self._profiles = [AppProfile(**p.to_dict()) for p in DEFAULT_APP_PROFILES]

    def get_profile(self, app_identifier: str) -> Optional[AppProfile]:
        """Find a profile by exact app identifier (case-insensitive)."""
        target = app_identifier.lower().strip()
        for p in self._profiles:
            if p.app_identifier.lower().strip() == target:
                return p
        return None

    def add_profile(
        self,
        app_identifier: str,
        mode_id: str,
        enabled: bool = True,
        description: str = "",
        match_type: str = "process",
    ) -> AppProfile:
        """Add or update a profile for the specified app identifier."""
        app_identifier = app_identifier.strip()
        mode_id = mode_id.strip().lower()

        # Validate mode
        if mode_id not in BUILTIN_MODES:
            mode_id = RAW_MODE.id

        existing = self.get_profile(app_identifier)
        if existing:
            existing.mode_id = mode_id
            existing.enabled = enabled
            if description:
                existing.description = description
            existing.match_type = match_type
            profile = existing
        else:
            profile = AppProfile(
                app_identifier=app_identifier,
                mode_id=mode_id,
                enabled=enabled,
                description=description,
                match_type=match_type,
            )
            self._profiles.append(profile)

        if self.settings is not None:
            self.save_to_settings(self.settings)
        return profile

    def remove_profile(self, app_identifier: str) -> bool:
        """Remove a profile by identifier. Returns True if removed."""
        target = app_identifier.lower().strip()
        orig_len = len(self._profiles)
        self._profiles = [
            p for p in self._profiles if p.app_identifier.lower().strip() != target
        ]
        removed = len(self._profiles) < orig_len
        if removed and self.settings is not None:
            self.save_to_settings(self.settings)
        return removed

    def set_profile_enabled(self, app_identifier: str, enabled: bool) -> bool:
        """Toggle enabled state for an app profile."""
        prof = self.get_profile(app_identifier)
        if prof:
            prof.enabled = enabled
            if self.settings is not None:
                self.save_to_settings(self.settings)
            return True
        return False

    def set_profile_mode(self, app_identifier: str, mode_id: str) -> bool:
        """Update formatting mode for an app profile."""
        prof = self.get_profile(app_identifier)
        if prof and mode_id in BUILTIN_MODES:
            prof.mode_id = mode_id
            if self.settings is not None:
                self.save_to_settings(self.settings)
            return True
        return False

    def detect_foreground_app(
        self, hwnd: Optional[int] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Helper to detect the active foreground process name and window title."""
        return detect_active_window(hwnd)

    def resolve_mode(
        self,
        process_name: Optional[str] = None,
        window_title: Optional[str] = None,
        hwnd: Optional[int] = None,
    ) -> str:
        """Resolve the appropriate formatting mode ID for the active or given application.

        1. If profiling is disabled, returns self.fallback_mode.
        2. If process_name and window_title are not provided, auto-detects from foreground/hwnd.
        3. Checks enabled profiles in order:
           - Exact process name match (e.g. "code.exe" == "code.exe")
           - Base process name match (e.g. "code" == "code")
           - Window title regex or substring match (if match_type is "title" or "contains")
        4. If no profile matches, returns self.fallback_mode.
        """
        if not self.enabled:
            return self.fallback_mode

        if not process_name and not window_title:
            process_name, window_title = self.detect_foreground_app(hwnd)

        proc_clean = (process_name or "").lower().strip()
        proc_base = proc_clean[:-4] if proc_clean.endswith(".exe") else proc_clean
        title_clean = (window_title or "").lower().strip()

        for prof in self._profiles:
            if not prof.enabled:
                continue

            ident_clean = prof.app_identifier.lower().strip()
            ident_base = (
                ident_clean[:-4] if ident_clean.endswith(".exe") else ident_clean
            )
            match_type = prof.match_type.lower().strip()

            # Process matching
            if match_type in ("process", "app", ""):
                if proc_clean and (
                    proc_clean == ident_clean or proc_base == ident_base
                ):
                    return prof.mode_id
                if title_clean and ident_base and ident_base in title_clean:
                    return prof.mode_id

            # Title or Substring matching
            elif match_type in ("title", "contains"):
                if title_clean and ident_clean in title_clean:
                    return prof.mode_id
                if proc_clean and ident_clean in proc_clean:
                    return prof.mode_id

            # Regex matching
            elif match_type == "regex":
                try:
                    pattern = re.compile(prof.app_identifier, re.IGNORECASE)
                    if proc_clean and pattern.search(proc_clean):
                        return prof.mode_id
                    if title_clean and pattern.search(title_clean):
                        return prof.mode_id
                except Exception:
                    continue

        return self.fallback_mode

    # -----------------------------------------------------------------------
    # Serialization & QSettings Persistence
    # -----------------------------------------------------------------------

    def to_json(self) -> str:
        """Serialize profiles and configuration to a JSON string."""
        data = {
            "enabled": self.enabled,
            "fallback_mode": self.fallback_mode,
            "profiles": [p.to_dict() for p in self._profiles],
        }
        return json.dumps(data, indent=2)

    def from_json(self, json_str: str) -> None:
        """Load profiles and configuration from a JSON string."""
        if not json_str or not json_str.strip():
            self.reset_to_defaults()
            return

        try:
            data = json.loads(json_str)
            if "enabled" in data:
                self.enabled = bool(data["enabled"])
            if "fallback_mode" in data:
                self.fallback_mode = str(data["fallback_mode"])
            raw_profiles = data.get("profiles", [])
            if isinstance(raw_profiles, list) and raw_profiles:
                self._profiles = [AppProfile.from_dict(p) for p in raw_profiles]
            else:
                self.reset_to_defaults()
        except Exception:
            self.reset_to_defaults()

    def save_to_settings(self, settings: Optional[Any] = None) -> None:
        """Save profile configuration to QSettings."""
        s = settings or self.settings
        if s is None:
            return

        s.setValue(SETTINGS_PROFILES_ENABLED, "true" if self.enabled else "false")
        s.setValue(SETTINGS_PROFILES_FALLBACK, self.fallback_mode)
        s.setValue(SETTINGS_APP_PROFILES, self.to_json())

    def load_from_settings(self, settings: Optional[Any] = None) -> None:
        """Load profile configuration from QSettings."""
        s = settings or self.settings
        if s is None:
            self.reset_to_defaults()
            return

        if s.contains(SETTINGS_PROFILES_ENABLED):
            enabled_val = s.value(SETTINGS_PROFILES_ENABLED)
            self.enabled = (
                str(enabled_val).lower() == "true"
                if isinstance(enabled_val, str)
                else bool(enabled_val)
            )
        if s.contains(SETTINGS_PROFILES_FALLBACK):
            self.fallback_mode = str(s.value(SETTINGS_PROFILES_FALLBACK))

        raw_json = s.value(SETTINGS_APP_PROFILES, "")
        if raw_json:
            self.from_json(str(raw_json))
        else:
            self.reset_to_defaults()
