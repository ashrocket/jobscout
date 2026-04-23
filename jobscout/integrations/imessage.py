import subprocess
from jobscout.config import get_imessage_phone


def send_imessage(text: str, phone: str = "") -> bool:
    if not phone:
        phone = get_imessage_phone()
    if not phone:
        return False
    escaped = text.replace('"', '\\"')
    script = (
        f'tell application "Messages" to send "{escaped}" '
        f'to buddy "{phone}" of service "iMessage"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True, timeout=10)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
