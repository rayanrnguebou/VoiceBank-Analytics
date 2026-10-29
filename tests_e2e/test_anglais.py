"""Version anglaise : sélecteur de langue, interface, erreurs et analyses de l'API en anglais, retour au français."""
import re

from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ADMIN, MDP = "direction@cooperative.cm", "Baobab-Douala-2026"

with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non');"
                         "localStorage.setItem('voicebank_demarrage_direction@cooperative.cm','non')")
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))

    # 1. Accueil : français par défaut, passage à l'anglais par le sélecteur
    page.goto(URL)
    page.evaluate("localStorage.removeItem('voicebank_langue')"); page.reload()
    expect(page.get_by_text("Interroge tes données bancaires")).to_be_visible(timeout=20000)
    page.get_by_label("Langue").select_option("en")
    expect(page.get_by_text("Query your banking data")).to_be_visible(timeout=20000)
    expect(page.locator("html")).to_have_attribute("lang", "en")
    page.get_by_role("button", name=re.compile("^Organisation")).click()
    page.get_by_label("Username or email").fill(ADMIN); page.get_by_label("Password").fill("wrong-password-1")
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("alert")).to_have_text("Incorrect credentials.", timeout=15000)
    print("1. accueil en anglais, erreur de l'API traduite")

    # 2. Application en anglais
    page.get_by_label("Password").fill(MDP)
    page.get_by_role("button", name="Sign in").click()
    expect(page.get_by_role("button", name="Sign out")).to_be_visible(timeout=20000)
    expect(nav("Voice assistant")).to_be_visible()
    q = page.get_by_placeholder(re.compile("Ask your question"))
    q.fill("Clients by city"); q.press("Enter")
    expect(page.get_by_text(re.compile(r"^\d+ results\. Top: "))).to_be_visible(timeout=30000)
    nav("Fraud alerts").click()
    expect(page.get_by_role("heading", name="Unusual transactions")).to_be_visible(timeout=60000)
    expect(page.get_by_text(re.compile("times the usual amount")).first).to_be_visible()
    nav("Model fact sheet").click()
    expect(page.get_by_text("Unusual transaction detection")).to_be_visible(timeout=60000)
    nav("Dashboard").click()
    expect(page.get_by_text("Clients by city")).to_be_visible(timeout=60000)
    nav("Members").click()
    expect(page.get_by_role("heading", name="Invite a member")).to_be_visible(timeout=20000)
    page.screenshot(path="anglais_membres.png", full_page=True)
    textes = page.locator("main").inner_text()
    for mot in ("Inviter", "Membres (", "Désactiver"):
        assert mot not in textes, mot
    print("2. assistant, alertes, fiche des modèles, tableau de bord et membres en anglais")

    # 3. Retour au français (session conservée)
    page.get_by_label("Language").select_option("fr")
    expect(nav("Assistant vocal")).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible()
    print("3. retour au français sans se reconnecter")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
