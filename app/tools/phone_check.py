#!/usr/bin/env python3
"""One command for the phone checks M1 owes (plan 1.1, 1.3, 1.7 and 2.7; detector/FREEZE_CHECKLIST.md).

Plug in ONE Android phone with USB debugging on, keep it unlocked with the screen on, then from the repo root:

    python app/tools/phone_check.py --build

On the phone it:
  1. runs M2's 36 test vectors inside the app, straight into the detector and through the app's own pipeline;
  2. captures the Key Attestation chain for M4 (the "Export attestation chain" button, without tapping);
  3. checks that a fresh install opens onboarding without crashing;
  4. revokes the phone, contacts and usage permissions and checks the app keeps running with the right banners.

It prints table rows to paste into app/e2e_log.md (the 36/36 row is what detector/tools/freeze_preflight.py counts) and
saves them, with the attestation JSON for M4, under app/build/phone_check/. Nothing is uploaded anywhere.
Step 3 clears the app's data (like a fresh install), so onboarding shows again afterwards.

Options:
  --build             build the debug app and its test APK first (needs JDK 21 and the Android SDK)
  --base-url URL      with --build: the server the app talks to (default http://10.0.2.2:8000/, emulator only)
  --local-server      adb reverse tcp:8000, for a server on this computer (build with --base-url http://localhost:8000/)
  --serial SERIAL     which device, when more than one is connected
  --allow-emulator    run on an emulator anyway (rows then say "Emulator" and do not count for the freeze)
  --adb PATH          adb to use (default: ANDROID_HOME, local.properties, then PATH)
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP_ID = "com.satark.app"
RUNNER = "com.satark.app.test/androidx.test.runner.AndroidJUnitRunner"
APK = ROOT / "app/build/outputs/apk/debug/app-debug.apk"
TEST_APK = ROOT / "app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
OUT = ROOT / "app/build/phone_check"
E2E_LOG = ROOT / "app/e2e_log.md"
REVOKED = ("READ_PHONE_STATE", "READ_CALL_LOG", "READ_CONTACTS")


def die(msg: str) -> None:
    print(f"\nSTOPPED: {msg}")
    sys.exit(2)


def find_adb(explicit: str | None) -> str:
    if explicit:
        return explicit
    exe = "adb.exe" if os.name == "nt" else "adb"
    sdks = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT")]
    props = ROOT / "local.properties"
    if props.is_file():
        for line in props.read_text(encoding="utf-8").splitlines():
            if line.startswith("sdk.dir="):
                sdks.append(line.split("=", 1)[1].replace("\\:", ":").replace("\\\\", "\\"))
    for sdk in filter(None, sdks):
        p = pathlib.Path(sdk) / "platform-tools" / exe
        if p.is_file():
            return str(p)
    found = shutil.which("adb")
    if not found:
        die("adb not found. Install the Android SDK platform-tools, or pass --adb PATH.")
    return found


class Adb:
    def __init__(self, path: str, serial: str | None = None):
        self.path, self.serial = path, serial

    def run(self, *args: str, timeout: int = 900) -> tuple[int, str]:
        cmd = [self.path] + (["-s", self.serial] if self.serial else []) + list(args)
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, p.stdout + p.stderr

    def out(self, *args: str, timeout: int = 900) -> str:
        return self.run(*args, timeout=timeout)[1]

    def shell(self, *args: str, timeout: int = 900) -> str:
        return self.out("shell", *args, timeout=timeout)

    def prop(self, name: str) -> str:
        return self.shell("getprop", name).strip()


def pick_device(adb: Adb, serial: str | None) -> str:
    lines = adb.out("devices").splitlines()[1:]
    ready = [l.split("\t")[0] for l in lines if l.endswith("\tdevice")]
    if any(l.endswith("\tunauthorized") for l in lines):
        print("A device is connected but not authorised: unlock it and accept the 'Allow USB debugging' prompt.")
    if serial:
        if serial not in ready:
            die(f"device {serial} is not connected and ready (connected: {ready or 'none'})")
        return serial
    if not ready:
        die("no device. Plug in the phone, turn on Developer options > USB debugging, and accept the prompt.")
    if len(ready) > 1:
        die(f"several devices connected ({', '.join(ready)}); pick one with --serial")
    return ready[0]


def device_label(adb: Adb, serial: str) -> tuple[str, bool]:
    model, maker = adb.prop("ro.product.model"), adb.prop("ro.product.manufacturer")
    hardware = adb.prop("ro.hardware").lower()
    emulator = (adb.prop("ro.kernel.qemu") == "1" or adb.prop("ro.boot.qemu") == "1" or hardware in ("goldfish", "ranchu")
                or "sdk_gphone" in model.lower() or "emulator" in model.lower())
    kind = "Emulator" if emulator else "Physical"
    label = (f"{kind}: {maker} {model}, Android {adb.prop('ro.build.version.release')} "
             f"(API {adb.prop('ro.build.version.sdk')}, serial ending {serial[-4:]})")
    return label, emulator


def gradle(base_url: str | None) -> None:
    gw = ROOT / ("gradlew.bat" if os.name == "nt" else "gradlew")
    cmd = [str(gw), ":app:assembleDebug", ":app:assembleDebugAndroidTest"]
    if base_url:
        cmd.append(f"-PsatarkBaseUrl={base_url}")
    print("Building:", " ".join(cmd[1:]))
    if subprocess.run(cmd, cwd=ROOT).returncode != 0:
        die("the Gradle build failed (see above). It needs JDK 21 and the Android SDK.")


def instrument(adb: Adb, test_class: str) -> str:
    return adb.shell("am", "instrument", "-w", "-r", "-e", "class", test_class, RUNNER)


def instrumentation_ok(output: str) -> bool:
    return "OK (" in output and "FAILURES!!!" not in output and "INSTRUMENTATION_FAILED" not in output


def screen_texts(adb: Adb) -> list[str]:
    adb.shell("uiautomator", "dump", "/sdcard/satark_ui.xml")
    xml = adb.out("exec-out", "cat", "/sdcard/satark_ui.xml")
    adb.shell("rm", "-f", "/sdcard/satark_ui.xml")
    return [html.unescape(t) for t in re.findall(r'text="([^"]*)"', xml) if t]


def accept_consent(adb: Adb) -> None:
    """A fresh install now opens on the "Before we start" consent screen; tap "I agree" to reach the setup screen."""
    adb.shell("uiautomator", "dump", "/sdcard/satark_ui.xml")
    xml = adb.out("exec-out", "cat", "/sdcard/satark_ui.xml")
    adb.shell("rm", "-f", "/sdcard/satark_ui.xml")
    m = re.search(r'text="I agree"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    if m:
        x1, y1, x2, y2 = map(int, m.groups())
        adb.shell("input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
        time.sleep(3)


def app_alive(adb: Adb) -> bool:
    return bool(adb.shell("pidof", APP_ID).strip())


def app_crashed(adb: Adb) -> bool:
    return f"Process: {APP_ID}" in adb.out("logcat", "-d", "-b", "crash")


def launch(adb: Adb, wait_s: int) -> None:
    adb.shell("input", "keyevent", "KEYCODE_WAKEUP")
    adb.shell("am", "start", "-W", "-n", f"{APP_ID}/.ui.MainActivity")
    time.sleep(wait_s)


def check_vectors(adb: Adb) -> tuple[bool, str]:
    adb.out("logcat", "-c")
    out = instrument(adb, "com.satark.app.VectorsOnDeviceTest")
    lines = [l.split("Satark.vectors:", 1)[-1].strip() for l in adb.out("logcat", "-d", "-s", "Satark.vectors:I").splitlines()
             if "Satark.vectors" in l]
    both = any("DETECTOR" in l and "36/36" in l for l in lines) and any("APP_PIPELINE" in l and "36/36" in l for l in lines)
    ok = instrumentation_ok(out) and both
    return ok, "; ".join(lines) if lines else out.strip()[-1500:]


def check_attestation(adb: Adb, slug: str, physical: bool) -> tuple[bool, str, pathlib.Path | None]:
    out = instrument(adb, "com.satark.app.AttestationExportOnDeviceTest")
    m = re.search(r"INSTRUMENTATION_STATUS: attestation_b64=(\S+)", out)
    if not instrumentation_ok(out) or not m:
        return False, out.strip()[-1500:], None
    data = json.loads(base64.b64decode(m.group(1)).decode("utf-8"))
    path = OUT / f"attestation_{slug}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    level = data.get("key_security_level", "unknown")
    note = (f"key level {level}, {len(data.get('attestation_chain', []))} certificates, "
            f"challenge from {data.get('challenge_source')}, signing cert {', '.join(data.get('app', {}).get('signing_cert_sha256', []))}")
    if physical and level not in ("TEE", "StrongBox"):
        note += ". WARNING: a real phone should give TEE or StrongBox; M4's server rejects software-only keys"
    return True, note, path


def check_fresh_install(adb: Adb) -> tuple[bool, str]:
    adb.shell("pm", "clear", APP_ID)
    adb.out("logcat", "-b", "crash", "-c")
    launch(adb, 8)
    accept_consent(adb)
    texts = screen_texts(adb)
    ok = any("Set up Satark" in t for t in texts) and app_alive(adb) and not app_crashed(adb)
    return ok, "onboarding shown" if ok else f"screen: {texts[:8]}, alive={app_alive(adb)}, crashed={app_crashed(adb)}"


def check_permissions_revoked(adb: Adb) -> tuple[bool, str]:
    for p in REVOKED:
        adb.shell("pm", "revoke", APP_ID, f"android.permission.{p}")
    adb.shell("appops", "set", APP_ID, "GET_USAGE_STATS", "deny")
    adb.shell("am", "force-stop", APP_ID)
    adb.out("logcat", "-b", "crash", "-c")
    launch(adb, 10)
    accept_consent(adb)
    # The banner sits below the permission cards; on a small screen it is off the first page, so scroll and look again.
    seen: list[str] = []
    for _ in range(5):
        seen += screen_texts(adb)
        texts = " | ".join(seen)
        banners = "Call signal is off" in texts and "Usage signal is off" in texts
        if banners:
            break
        adb.shell("input", "swipe", "500", "1500", "500", "700", "300")
        time.sleep(1)
    ok = banners and app_alive(adb) and not app_crashed(adb)
    return ok, ("banners for call and usage shown, app running" if ok
                else f"banners={banners}, alive={app_alive(adb)}, crashed={app_crashed(adb)}; screen: {texts[:300]}")


def next_row_number() -> int:
    nums = [int(m.group(1)) for m in re.finditer(r"^\|\s*(\d+)\s*\|", E2E_LOG.read_text(encoding="utf-8"), re.M)] if E2E_LOG.is_file() else []
    return max(nums, default=0) + 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--base-url")
    ap.add_argument("--local-server", action="store_true")
    ap.add_argument("--serial")
    ap.add_argument("--allow-emulator", action="store_true")
    ap.add_argument("--adb")
    a = ap.parse_args()

    adb = Adb(find_adb(a.adb))
    adb.serial = pick_device(adb, a.serial)
    label, emulator = device_label(adb, adb.serial)
    print(f"Device: {label}")
    if emulator and not a.allow_emulator:
        die("this is an emulator. The freeze needs physical phones; use --allow-emulator only for a dry run.")
    if a.build:
        gradle(a.base_url)
    for f in (APK, TEST_APK):
        if not f.is_file():
            die(f"{f.relative_to(ROOT)} is missing; run with --build (or ./gradlew :app:assembleDebug :app:assembleDebugAndroidTest)")
    if a.local_server:
        print("adb reverse tcp:8000 tcp:8000:", adb.out("reverse", "tcp:8000", "tcp:8000").strip() or "ok")

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^A-Za-z0-9]+", "_", label.split(",")[0].split(": ", 1)[1]).strip("_") + "_" + stamp

    print("Installing the app and its test APK...")
    for f in (APK, TEST_APK):
        code, text = adb.run("install", "-r", "-t", str(f))
        if code != 0 or "Success" not in text:
            die(f"install of {f.name} failed:\n{text.strip()}")

    results = []
    print("1/4 M2's 36 test vectors on the device (about a minute)...")
    ok, note = check_vectors(adb)
    results.append(("App pipeline + detector (instrumented)", "36/36" if ok else "FAILED", ok, note))
    print("2/4 Key Attestation chain for M4...")
    ok, note, att = check_attestation(adb, slug, physical=not emulator)
    results.append(("Attestation chain exported for M4", "Pass" if ok else "FAILED", ok, note))
    print("3/4 Fresh install opens onboarding...")
    ok, note = check_fresh_install(adb)
    results.append(("Fresh install: onboarding opens, no crash", "Pass" if ok else "FAILED", ok, note))
    print("4/4 Permissions revoked: banners, no crash...")
    ok, note = check_permissions_revoked(adb)
    results.append(("Phone, contacts, usage access revoked: banners, no crash", "Pass" if ok else "FAILED", ok, note))

    n = next_row_number()
    rows = [f"| {n + i} | {label} | {what} | {result} |" for i, (what, result, _, _) in enumerate(results)]
    report = [f"# Phone check {stamp}", "", f"Device: {label}", "",
              "Rows for app/e2e_log.md (paste under \"Detector in the app\"; the 36/36 row is what the freeze counts):", "",
              "| # | Where | Path | Result |", "|---|---|---|---|", *rows, "", "Details:", ""]
    report += [f"- {what}: {'PASS' if ok else 'FAIL'}. {note}" for what, _, ok, note in results]
    if att:
        report += ["", f"Attestation JSON for M4: {att}"]
    out_md = OUT / f"phone_check_{slug}.md"
    out_md.write_text("\n".join(report) + "\n", encoding="utf-8")

    print("\n" + "\n".join(report))
    print(f"\nSaved: {out_md}")
    if emulator:
        print("Note: emulator run. These rows say Emulator and do not count towards the detector freeze.")
    return 0 if all(ok for _, _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
