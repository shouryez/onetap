"""Live phone mode: run a plan's one-tap action on a real Android/Samsung phone over wireless debugging (ADB).

The hackathon catalog's deeplinks are masked placeholders, so each action is mapped to a real Android setting by
its text (deeplink message/description, action name, steps). Only safe, reversible settings are ever changed:
restart, reset, safe mode and clear-data actions just open the relevant screen.
"""
import asyncio
import re
import shutil

from . import config

SAFE_NEVER = re.compile(r"\b(restart|reboot|factory|reset|safe mode|clear (app )?(data|cache|storage)|wipe|delete|uninstall)")


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
# Samsung renames settings between One UI versions, so each toggle lists the keys it may use; only keys that exist on
# the connected phone are written, and every change is read back before it is reported as done.
def T(label, pat, screen, keys=(), discover=None, on=(), off=(), verify=None, cuts_link=None):
    return {"label": label, "pat": pat, "screen": screen, "keys": list(keys), "discover": discover,
            "on": list(on), "off": list(off), "verify": verify, "cuts_link": cuts_link}


BATTERY = "android.intent.action.POWER_USAGE_SUMMARY"
DISPLAY = "android.settings.DISPLAY_SETTINGS"
TOGGLES = [
    T("Adaptive battery", r"adaptive battery", BATTERY,
      keys=[("global", "adaptive_battery_management_enabled", "1", "0")], discover=r"adaptive_battery"),
    T("Battery protection", r"battery protect|protect battery|charging limit|limit (the )?charg|85 ?%", BATTERY,
      keys=[("global", "protect_battery", "1", "0")], discover=r"protect_?batt|batt\w*_?protect"),
    T("Fast charging", r"fast charg", BATTERY,
      keys=[("system", "adaptive_fast_charging", "1", "0"), ("system", "super_fast_charging", "1", "0")],
      discover=r"fast_charg"),
    T("Power saving", r"power sav|battery saver|low power", "android.settings.BATTERY_SAVER_SETTINGS",
      keys=[("global", "low_power", "1", "0")]),
    T("Adaptive brightness", r"adaptive brightness|auto(matic)? brightness", DISPLAY,
      keys=[("system", "screen_brightness_mode", "1", "0")]),
    T("Screen brightness", r"brightness", DISPLAY,
      on=["settings put system screen_brightness_mode 0", "settings put system screen_brightness 200"],
      off=["settings put system screen_brightness_mode 0", "settings put system screen_brightness 40"],
      verify=("system", "screen_brightness_mode", "0", "0")),
    T("Eye comfort shield", r"eye comfort|blue light|night light|night display", DISPLAY,
      keys=[("system", "blue_light_filter", "1", "0"), ("secure", "night_display_activated", "1", "0")],
      discover=r"^blue_light_filter$"),
    T("Dark mode", r"dark mode|dark theme|night mode", DISPLAY,
      on=["cmd uimode night yes"], off=["cmd uimode night no"], verify=("secure", "ui_night_mode", "2", "1")),
    T("Motion smoothness", r"motion smoothness|refresh rate|120 ?hz", DISPLAY,
      keys=[("secure", "refresh_rate_mode", "1", "0")]),
    T("Screen timeout", r"screen time ?out|screen off|sleep after", DISPLAY,
      keys=[("system", "screen_off_timeout", "120000", "30000")]),
    T("Font size", r"font size|text size|font scale|larger text", DISPLAY,
      keys=[("system", "font_scale", "1.15", "1.0")]),
    T("Auto rotate", r"auto.?rotat|screen rotation", DISPLAY, keys=[("system", "accelerometer_rotation", "1", "0")]),
    T("Touch sensitivity", r"touch sensitivity|screen protector", DISPLAY,
      keys=[("system", "auto_adjust_touch", "1", "0")], discover=r"touch_sensitiv|auto_adjust_touch"),
    T("Accidental touch protection", r"accidental touch|pocket", DISPLAY, discover=r"accidental|block_.*touch"),
    T("Always On Display", r"always on display|\baod\b", "android.settings.LOCK_SCREEN_SETTINGS",
      keys=[("system", "aod_mode", "1", "0")]),
    T("Swipe gestures", r"swipe gesture|gesture navigation|navigation gesture|navigation bar|swipe navigation", DISPLAY,
      keys=[("global", "navigation_bar_gesture_while_hidden", "1", "0")]),
    T("Touch vibration", r"haptic|touch vibration|vibration feedback", "android.settings.SOUND_SETTINGS",
      keys=[("system", "haptic_feedback_enabled", "1", "0")]),
    T("Wi-Fi", r"wi-?fi", "android.settings.WIFI_SETTINGS", on=["svc wifi enable"], off=["svc wifi disable"],
      verify=("global", "wifi_on", "1", "0"), cuts_link="off"),
    T("Airplane mode", r"airplane|flight mode", "android.settings.AIRPLANE_MODE_SETTINGS",
      on=["cmd connectivity airplane-mode enable"], off=["cmd connectivity airplane-mode disable"],
      verify=("global", "airplane_mode_on", "1", "0"), cuts_link="on"),
    T("Bluetooth", r"bluetooth", "android.settings.BLUETOOTH_SETTINGS", on=["svc bluetooth enable"],
      off=["svc bluetooth disable"], verify=("global", "bluetooth_on", "1", "0")),
    T("NFC", r"\bnfc\b", "android.settings.NFC_SETTINGS", on=["svc nfc enable"], off=["svc nfc disable"]),
    T("Mobile data", r"mobile data", "android.settings.DATA_ROAMING_SETTINGS", on=["svc data enable"],
      off=["svc data disable"], verify=("global", "mobile_data", "1", "0")),
    T("Data saver", r"data saver", "android.settings.DATA_USAGE_SETTINGS",
      on=["cmd netpolicy set restrict-background true"], off=["cmd netpolicy set restrict-background false"]),
    T("Do not disturb", r"do not disturb|\bdnd\b", "android.settings.ZEN_MODE_SETTINGS",
      on=["cmd notification set_dnd on"], off=["cmd notification set_dnd off"]),
    T("Location", r"location|gps", "android.settings.LOCATION_SOURCE_SETTINGS",
      on=["cmd location set-location-enabled true"], off=["cmd location set-location-enabled false"]),
]
# open-only screens (no change)
SCREENS = [
    (r"battery usage|battery", "Battery", BATTERY),
    (r"software update|system update|firmware", "Software update", "android.settings.SYSTEM_UPDATE_SETTINGS"),
    (r"storage", "Storage", "android.settings.INTERNAL_STORAGE_SETTINGS"),
    (r"network", "Connections", "android.settings.WIRELESS_SETTINGS"),
    (r"date|time zone|clock", "Date and time", "android.settings.DATE_SETTINGS"),
    (r"accessibility|magnif|talkback|click", "Accessibility", "android.settings.ACCESSIBILITY_SETTINGS"),
    (r"sound|volume|vibrat|ringtone", "Sound", "android.settings.SOUND_SETTINGS"),
    (r"lock screen|security|biometric|fingerprint", "Security", "android.settings.SECURITY_SETTINGS"),
    (r"app|application|permission", "Apps", "android.settings.APPLICATION_SETTINGS"),
    (r"display|screen|flicker", "Display", DISPLAY),
]


def match(text: str) -> tuple[dict | None, tuple[str, str]]:
    """-> (toggle or None, (label, screen intent)). Unsafe actions never match a toggle."""
    t = text.lower()
    if not SAFE_NEVER.search(t):
        for tg in TOGGLES:
            if re.search(tg["pat"], t):
                return tg, (tg["label"], tg["screen"])
    for pat, label, action in SCREENS:
        if re.search(pat, t):
            return None, (label, action)
    return None, ("Settings", "android.settings.SETTINGS")


def _direction(original_type: str, text: str) -> str:
    if original_type == "offURL" or re.search(r"\b(disable|turn off|toggle off|switch off)\b", text, re.I):
        return "off"
    return "on"


async def _get(s: str, ns: str, key: str) -> str:
    return (await _run("shell", "settings", "get", ns, key, serial=s)).strip()


async def _keys_on_phone(s: str, tg: dict) -> list[tuple[str, str, str, str]]:
    found = [k for k in tg["keys"] if await _get(s, k[0], k[1]) not in ("null", "")]
    if found or not tg["discover"]:
        return found
    for ns in ("system", "global", "secure"):           # unknown One UI naming: look the key up on the phone
        for line in (await _run("shell", "settings", "list", ns, serial=s)).splitlines():
            key, _, val = line.partition("=")
            if re.search(tg["discover"], key, re.I) and val.strip() in ("0", "1"):
                found.append((ns, key, "1", "0"))
    return found


async def _set_keys(s: str, tg: dict, state: str, out: dict):
    keys = await _keys_on_phone(s, tg)
    for ns, key, on, off in keys:
        await _run("shell", "settings", "put", ns, key, on if state == "on" else off, serial=s)
    out["keys"] = [f"{ns}/{key}" for ns, key, *_ in keys]
    if not keys:
        out["note"] = f"this phone has no {out['label']} setting"
        return
    out["changed"] = all([await _get(s, ns, key) == (on if state == "on" else off) for ns, key, on, off in keys])


async def _run_cmds(s: str, tg: dict, state: str, out: dict):
    for c in (tg["on"] if state == "on" else tg["off"]):
        r = await _run("shell", *c.split(), serial=s)
        if re.search(r"exception|error|unknown|not found|usage:", r, re.I):
            out["note"] = r[:160]
            return
    if not tg["verify"]:
        out["changed"] = True
        return
    ns, key, on, off = tg["verify"]
    want = on if state == "on" else off
    for _ in range(6):                                  # radios take a moment to switch
        if await _get(s, ns, key) == want:
            out["changed"] = True
            return
        await asyncio.sleep(0.5)


async def apply(action: dict) -> dict:
    """action: {actionName, steps, deeplink: {message, description, originalType}}"""
    dl = action.get("deeplink") or {}
    text = " ".join([dl.get("message", ""), dl.get("description", ""), action.get("actionName", ""),
                     " ".join(action.get("steps") or [])])
    tg, (label, screen) = match(text)
    s = await _serial()
    out = {"label": label, "screen": screen, "changed": False}
    await _run("shell", "input", "keyevent", "KEYCODE_WAKEUP", serial=s)
    if tg:
        state = out["state"] = _direction(dl.get("originalType", ""), text)
        if tg["cuts_link"] == state and ":" in s:
            out["note"] = f"not switched: turning {label} {state} would disconnect the phone from this laptop"
        elif tg["keys"] or tg["discover"]:
            await _set_keys(s, tg, state, out)
        else:
            await _run_cmds(s, tg, state, out)
    await _run("shell", "am", "start", "-a", screen, serial=s)
    return out
