"""notify.py - scan the vault for nearby dates and raise Windows toasts.

Runs while the app is open (a background thread in server.py calls
scan_and_notify periodically). De-dupes so each item toasts at most once per
day per process. Falls back to a console message if the toast call fails.
"""
from __future__ import annotations

import subprocess
from datetime import date

from . import hub

# in-memory de-dupe: {item_path: "YYYY-MM-DD last toasted"}
_TOASTED: dict[str, str] = {}


def _powershell_toast(title: str, message: str) -> bool:
    """Raise a native Windows toast via WinRT. Returns True on success."""
    safe_title = title.replace("'", "''")
    safe_msg = message.replace("'", "''")
    ps = f"""
$ErrorActionPreference = 'Stop'
try {{
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $texts = $template.GetElementsByTagName('text')
    $texts.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) | Out-Null
    $texts.Item(1).AppendChild($template.CreateTextNode('{safe_msg}')) | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Magpie')
    $notifier.Show($toast)
}} catch {{
    exit 1
}}
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def notify(title: str, message: str):
    if not _powershell_toast(title, message):
        print(f"[notify] {title} - {message}")


def scan_and_notify(window_days=None):
    """Toast each due/soon item once per day. Returns the count toasted."""
    today = date.today().isoformat()
    items = hub.due_soon(window_days)
    count = 0
    for item in items:
        # only toast things due today or overdue, to avoid noise
        if item["days_left"] > 0:
            continue
        key = item["path"]
        if _TOASTED.get(key) == today:
            continue
        _TOASTED[key] = today
        when = "overdue" if item["days_left"] < 0 else "due today"
        notify(f"{item['title']} ({when})", f"{item['category']} · {item['date_kind']} {item['date']}")
        count += 1
    return count


if __name__ == "__main__":
    n = scan_and_notify()
    print(f"Toasted {n} item(s).")
