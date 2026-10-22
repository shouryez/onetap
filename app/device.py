"""Live phone mode: run a plan's one-tap action on a real Android/Samsung phone over wireless debugging (ADB).

The hackathon catalog's deeplinks are masked placeholders, so each action is mapped to a real Android setting by
its text (deeplink message/description, action name, steps). Only safe, reversible settings are ever changed:
restart, reset, safe mode and clear-data actions just open the relevant screen.
"""
import asyncio
import re
import shutil

from . import config

SAFE_NEVER = re.compile(r"restart|reboot|factory|reset|safe mode|clear (app )?(data|cache|storage)|wipe|delete|uninstall")


class DeviceError(RuntimeError):
    pass


def _adb() -> str:
    p = config.ADB_PATH or shutil.which("adb")
    if not p:
        raise DeviceError("adb not found: set ADB_PATH in .env")
    return p


async def _run(*args: str, serial: str | None = None, timeout: float = 15) -> str:
    cmd = [_adb()] + (["-s", serial] if serial else []) + list(args)
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise DeviceError("adb timed out: is the phone awake and on the same Wi-Fi?")
    return out.decode("utf-8", "replace").strip()


async def _serial() -> str:
    out = await _run("devices")
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            return parts[0]
    raise DeviceError("No phone connected yet: pair one with the Phone button.")


async def status() -> dict:
    try:
        s = await _serial()
    except DeviceError as e:
        return {"connected": False, "reason": str(e)}
    model = await _run("shell", "getprop", "ro.product.model", serial=s)
    brand = await _run("shell", "getprop", "ro.product.brand", serial=s)
    android = await _run("shell", "getprop", "ro.build.version.release", serial=s)
    return {"connected": True, "serial": s, "model": model, "brand": brand.title(), "android": android}


async def pair(host_port: str, code: str) -> dict:
    out = await _run("pair", host_port.strip(), code.strip(), timeout=25)
    if "Successfully paired" not in out:
        raise DeviceError(out[-200:] or "pairing failed")
    # the connect port differs from the pairing port; wireless debugging advertises it over mDNS
    host = host_port.split(":")[0]
    for _ in range(6):
        services = await _run("mdns", "services")
        for line in services.splitlines():
            m = re.search(r"_adb-tls-connect\._tcp\.?\s+(\d+\.\d+\.\d+\.\d+:\d+)", line)
            if m and m.group(1).startswith(host + ":"):
                await _run("connect", m.group(1))
                return await status()
        await asyncio.sleep(1)
    return {"connected": False, "paired": True,
            "reason": "paired - now enter the IP address & port shown on the Wireless debugging screen and tap Connect"}


async def connect(host_port: str) -> dict:
    out = await _run("connect", host_port.strip(), timeout=20)
    if "connected" not in out or "cannot" in out or "failed" in out:
        raise DeviceError(out[-200:] or "connect failed")
    return await status()


# ----------------------------------------------------------------------------- action -> real Android setting
# (pattern, label, commands-when-on, commands-when-off, Settings screen to show)
S = "settings put"
RULES = [
    (r"adaptive brightness|auto(matic)? brightness", "Adaptive brightness",
     [f"{S} system screen_brightness_mode 1"], [f"{S} system screen_brightness_mode 0"], "DISPLAY_SETTINGS"),
    (r"brightness", "Screen brightness",
     [f"{S} system screen_brightness_mode 0", f"{S} system screen_brightness 200"],
     [f"{S} system screen_brightness_mode 0", f"{S} system screen_brightness 40"], "DISPLAY_SETTINGS"),
    (r"dark mode|dark theme|night mode", "Dark mode", ["cmd uimode night yes"], ["cmd uimode night no"],
     "DISPLAY_SETTINGS"),
    (r"screen time ?out|screen off|sleep after", "Screen timeout",
     [f"{S} system screen_off_timeout 120000"], [f"{S} system screen_off_timeout 30000"], "DISPLAY_SETTINGS"),
    (r"font size|text size|font scale|larger text", "Font size",
     [f"{S} system font_scale 1.15"], [f"{S} system font_scale 1.0"], "DISPLAY_SETTINGS"),
    (r"auto.?rotat|screen rotation", "Auto rotate",
     [f"{S} system accelerometer_rotation 1"], [f"{S} system accelerometer_rotation 0"], "DISPLAY_SETTINGS"),
    (r"touch sensitivity|screen protector", "Touch sensitivity",
     [f"{S} system auto_adjust_touch 1"], [f"{S} system auto_adjust_touch 0"], "DISPLAY_SETTINGS"),
    (r"power sav|battery saver|low power", "Power saving",
     [f"{S} global low_power 1"], [f"{S} global low_power 0"], "BATTERY_SAVER_SETTINGS"),
    (r"airplane|flight mode", "Airplane mode",
     ["cmd connectivity airplane-mode enable"], ["cmd connectivity airplane-mode disable"], "AIRPLANE_MODE_SETTINGS"),
    (r"bluetooth", "Bluetooth", ["svc bluetooth enable"], ["svc bluetooth disable"], "BLUETOOTH_SETTINGS"),
    (r"mobile data", "Mobile data", ["svc data enable"], ["svc data disable"], "DATA_ROAMING_SETTINGS"),
    (r"do not disturb|\bdnd\b", "Do not disturb", ["cmd notification set_dnd on"], ["cmd notification set_dnd off"],
     "ZEN_MODE_SETTINGS"),
    (r"location|gps", "Location", ["cmd location set-location-enabled true"],
     ["cmd location set-location-enabled false"], "LOCATION_SOURCE_SETTINGS"),
]
# open-only screens (no change)
SCREENS = [
    (r"battery usage|battery", "Battery", "android.intent.action.POWER_USAGE_SUMMARY"),
    (r"software update|system update|firmware", "Software update", "android.settings.SYSTEM_UPDATE_SETTINGS"),
    (r"storage", "Storage", "android.settings.INTERNAL_STORAGE_SETTINGS"),
    (r"wi-?fi|network", "Wi-Fi", "android.settings.WIFI_SETTINGS"),
    (r"date|time zone|clock", "Date and time", "android.settings.DATE_SETTINGS"),
    (r"accessibility|magnif|talkback|click", "Accessibility", "android.settings.ACCESSIBILITY_SETTINGS"),
    (r"sound|volume|vibrat|ringtone", "Sound", "android.settings.SOUND_SETTINGS"),
    (r"lock screen|security|biometric|fingerprint", "Security", "android.settings.SECURITY_SETTINGS"),
    (r"app|application|permission", "Apps", "android.settings.APPLICATION_SETTINGS"),
    (r"display|screen|refresh|motion|flicker|navigation bar|gesture", "Display", "android.settings.DISPLAY_SETTINGS"),
]


def plan_for(text: str, direction: str) -> dict:
    """-> {"label", "change": [shell cmds], "screen": intent action}. direction: "on" | "off" | "open"."""
    t = text.lower()
    if not SAFE_NEVER.search(t):
        for pat, label, on, off, screen in RULES:
            if re.search(pat, t):
                cmds = off if direction == "off" else on
                return {"label": label, "state": "off" if direction == "off" else "on", "change": cmds,
                        "screen": "android.settings." + screen}
    for pat, label, action in SCREENS:
        if re.search(pat, t):
            return {"label": label, "change": [], "screen": action}
    return {"label": "Settings", "change": [], "screen": "android.settings.SETTINGS"}


def _direction(original_type: str, text: str) -> str:
    if original_type == "offURL" or re.search(r"\b(disable|turn off|toggle off|switch off)\b", text, re.I):
        return "off"
    if original_type in ("onURL", "updateURL") or re.search(r"\b(enable|turn on|toggle on|switch on|increase)\b", text, re.I):
        return "on"
    return "open"


async def apply(action: dict) -> dict:
    """action: {actionName, steps, deeplink: {message, description, originalType}}"""
    dl = action.get("deeplink") or {}
    text = " ".join([dl.get("message", ""), dl.get("description", ""), action.get("actionName", ""),
                     " ".join(action.get("steps") or [])])
    plan = plan_for(text, _direction(dl.get("originalType", ""), text))
    s = await _serial()
    await _run("shell", "input", "keyevent", "KEYCODE_WAKEUP", serial=s)
    for c in plan["change"]:
        out = await _run("shell", *c.split(), serial=s)
        if re.search(r"exception|error|unknown|not found", out, re.I):
            plan.setdefault("warnings", []).append(f"{c}: {out[:120]}")
    await _run("shell", "am", "start", "-a", plan["screen"], serial=s)
    plan["changed"] = bool(plan["change"]) and not plan.get("warnings")
    return plan
