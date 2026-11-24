#!/usr/bin/env python3
"""Erzeugt die Doku-Screenshots aus dem laufenden Demo-Server (tests/demo_server.py)."""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8098"
OUT = sys.argv[2] if len(sys.argv) > 2 else "docs/screenshots"


def wait_live(page, source: str, timeout: float = 40) -> None:
    t0 = time.time()
    while time.time() - t0 < timeout:
        cls = page.get_attribute("#onair", "class") or ""
        kick = page.inner_text("#oaKicker")
        if "live" in cls and source in kick:
            time.sleep(1.2)
            return
        time.sleep(0.2)


with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 1440, "height": 1100}, device_scale_factor=1)
    page = ctx.new_page()
    page.on("dialog", lambda d: d.accept())
    page.goto(BASE)
    time.sleep(2)
    wait_live(page, "FRN")
    page.screenshot(path=f"{OUT}/dashboard-live-frn.png", full_page=True)
    wait_live(page, "DMR")
    page.screenshot(path=f"{OUT}/dashboard-live-dmr.png", full_page=False)
    wait_live(page, "Zello")
    page.screenshot(path=f"{OUT}/dashboard-live-zello.png", full_page=False)
    page.click("button[data-tab=stats]")
    time.sleep(1.5)
    page.screenshot(path=f"{OUT}/statistik.png", full_page=True)
    page.click("button[data-tab=nets]")
    time.sleep(1)
    page.screenshot(path=f"{OUT}/netze.png", full_page=True)
    # Login + Admin
    page.click("#loginBtn")
    page.fill("#lUser", "demo")
    page.fill("#lPass", "demo12345")
    page.click("#lOk")
    time.sleep(1.5)
    page.click("button[data-tab=live]")
    time.sleep(1)
    page.screenshot(path=f"{OUT}/banner-update-passwort.png", clip={"x": 0, "y": 0, "width": 1440, "height": 330})
    wait_live(page, "")
    page.click("#listenBtn")
    page.click("#listenCaret")
    time.sleep(1.5)
    page.screenshot(path=f"{OUT}/dashboard-mithoeren.png", clip={"x": 0, "y": 0, "width": 1440, "height": 560})
    page.click("body", position={"x": 700, "y": 900})
    page.click("#listenBtn")
    page.click("button[data-tab=admin]")
    time.sleep(0.8)
    for sec, name in [("vocoder", "admin-vocoder"), ("routes", "admin-routing"), ("dmr", "admin-dmr"),
                      ("frn", "admin-frn"), ("zello", "admin-zello"), ("ids", "admin-idlisten-avatare"),
                      ("appearance", "admin-aussehen"), ("update", "admin-updates"), ("backup", "admin-backup"), ("system", "admin-system")]:
        page.click(f"#adminNav button[data-s={sec}]")
        time.sleep(0.8)
        page.screenshot(path=f"{OUT}/{name}.png", full_page=True)
    # Vocoder: Klang-Popup und Probehören
    page.click("#adminNav button[data-s=vocoder]")
    time.sleep(0.8)
    page.click("#vocTuneBtn")
    time.sleep(1.2)
    page.screenshot(path=f"{OUT}/admin-vocoder-klang.png", full_page=False)
    page.click("#vpRun")
    page.wait_for_selector("#vpResult audio", timeout=60000)
    time.sleep(0.8)
    page.eval_on_selector("#vpResult", "el => el.scrollIntoView({block: 'end'})")
    time.sleep(0.5)
    page.screenshot(path=f"{OUT}/admin-vocoder-probehoeren.png", full_page=False)
    page.click("#vpClose")
    time.sleep(0.8)
    # FRN: Passwort anfordern -> Status-Popup
    page.click("#adminNav button[data-s=frn]")
    time.sleep(0.8)
    page.click("#frnPwBtn")
    time.sleep(2)
    page.screenshot(path=f"{OUT}/admin-frn-passwort-anfordern.png", full_page=False)
    page.click("#spOk")
    # Englisch (N8 Kit: DE | EN in der Kopfzeile)
    page.click("button[data-tab=live]")
    page.click(".n8-lang button[data-l=en]")
    time.sleep(1.5)
    page.screenshot(path=f"{OUT}/dashboard-englisch.png", clip={"x": 0, "y": 0, "width": 1440, "height": 560})
    page.click(".n8-lang button[data-l=de]")
    # Mobil
    m = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True)
    mp = m.new_page()
    mp.goto(BASE)
    time.sleep(2)
    wait_live(mp, "")
    mp.screenshot(path=f"{OUT}/mobil.png", full_page=False)
    b.close()
print("fertig")
