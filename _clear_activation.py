"""Clear cached activation state so the paywall dialog appears on next launch."""
import sys
from PySide6.QtCore import QSettings
from scribe_dictation.licensing import ORGANIZATION, APP_NAME, SETTING_LICENSE_KEY, SETTING_LICENSE_SIGNATURE

settings = QSettings(ORGANIZATION, APP_NAME)
settings.remove(SETTING_LICENSE_KEY)
settings.remove(SETTING_LICENSE_SIGNATURE)
settings.remove("license_cache_v2")
print("Cached activation cleared — dialog should show on next launch.")
sys.exit(0)