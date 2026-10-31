"""Captures d'écran pour le manifeste (Play Store, installation) : téléphone et ordinateur, données fictives."""
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403

DEST = Path(__file__).resolve().parents[1] / "voicebank-ui" / "public" / "captures"
DEST.mkdir(exist_ok=True)
INIT = "localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non');"


def connexion(page):
    page.goto(URL)
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill("rayan"); page.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name=re.compile("Se déconnecter|Menu"))).to_be_visible(timeout=20000)


with sync_playwright() as p:
    b = lancer(p)
    for nom, opts in (("telephone", dict(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)),
                      ("ordinateur", dict(viewport={"width": 1440, "height": 900}, device_scale_factor=1))):
        ctx = b.new_context(**opts); ctx.add_init_script(INIT)
        page = ctx.new_page()
        connexion(page)
        if nom == "ordinateur":
            page.get_by_role("navigation").get_by_role("button", name=re.compile("^Assistant vocal")).click()
        page.get_by_role("button", name="Volume transactions par ville", exact=True).click()
        expect(page.get_by_text(re.compile(r"Résultats \(1\)"))).to_be_visible(timeout=30000)
        page.wait_for_timeout(1500)
        page.get_by_text(re.compile(r"Résultats \(1\)")).scroll_into_view_if_needed()
        page.evaluate("window.scrollBy(0, -120)")
        page.screenshot(path=str(DEST / f"{nom}-assistant.png"))
        if nom == "ordinateur":
            page.get_by_role("navigation").get_by_role("button", name=re.compile("^Alertes de fraude")).click()
        else:
            page.get_by_role("button", name=re.compile("Menu|Ouvrir le menu")).first.click()
            page.get_by_role("navigation").get_by_role("button", name=re.compile("^Alertes de fraude")).click()
        page.wait_for_timeout(4000)
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(DEST / f"{nom}-alertes.png"))
        ctx.close()
    b.close()
print("captures :", sorted(x.name for x in DEST.iterdir()))
