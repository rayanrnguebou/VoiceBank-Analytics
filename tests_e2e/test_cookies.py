"""Bandeau des cookies : premier passage, refus aussi simple que l'acceptation, choix conservé, réglage depuis le pied
de page, détail dans la politique de confidentialité."""
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

with sync_playwright() as p:
    b = lancer(p)
    ctx = b.sans_consentement(viewport={"width": 390, "height": 844}, is_mobile=True)   # premier passage, téléphone
    page = ctx.new_page()
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))

    page.goto(URL)
    bandeau = page.get_by_role("dialog", name="Ta vie privée, tes choix")
    expect(bandeau).to_be_visible(timeout=20000)
    for nom in ("Tout refuser", "Personnaliser", "Tout accepter"):
        expect(bandeau.get_by_role("button", name=nom)).to_be_visible()
    page.screenshot(path="cookies_bandeau.png")
    deborde = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not deborde, "débordement horizontal sur mobile"
    print("1. premier passage : bandeau avec « Tout refuser », « Personnaliser », « Tout accepter »")

    bandeau.get_by_role("button", name="Tout refuser").click()
    expect(bandeau).to_be_hidden()
    page.reload()
    expect(page.get_by_role("button", name="Organisation")).to_be_visible(timeout=20000)
    expect(page.get_by_role("dialog", name="Ta vie privée, tes choix")).to_have_count(0)
    choix = page.evaluate("JSON.parse(localStorage.getItem('voicebank_consentement'))")
    assert choix["erreurs"] is False, choix
    print("2. refus mémorisé : le bandeau ne revient pas, aucun rapport d'erreurs")

    page.get_by_role("button", name="Gérer les cookies").click()
    gestion = page.get_by_role("dialog", name="Gérer les cookies")
    expect(gestion.get_by_text("Strictement nécessaires")).to_be_visible()
    gestion.get_by_text("Rapports d'erreurs anonymes", exact=True).click()
    expect(gestion.get_by_role("switch")).to_be_checked()
    page.screenshot(path="cookies_gestion.png")
    gestion.get_by_role("button", name="Enregistrer mes choix").click()
    expect(gestion).to_be_hidden()
    assert page.evaluate("JSON.parse(localStorage.getItem('voicebank_consentement')).erreurs") is True
    print("3. « Gérer les cookies » en bas de page : accord modifiable à tout moment")

    page.goto(URL + "/confidentialite/#cookies")
    expect(page.locator("#cookies")).to_contain_text("Cookies et stockage")
    expect(page.get_by_text("Seulement avec votre accord")).to_be_visible()
    print("4. politique de confidentialité : tableau détaillé des cookies et du stockage")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
