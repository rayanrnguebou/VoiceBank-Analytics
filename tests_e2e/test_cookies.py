"""Bandeau des cookies : premier passage, refus aussi simple que l'acceptation, choix conservé, réglage depuis le pied
de page, détail dans la politique de confidentialité. Présentation des applications : film puis carte finale."""
import re

from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

with sync_playwright() as p:
    b = lancer(p)
    ctx = b.sans_consentement(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                              user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
                                         "Chrome/140.0 Mobile Safari/537.36")   # premier passage, téléphone
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
    # Après les cookies : présentation des applications (visiteur sans compte), une fois par ouverture
    pres = page.get_by_role("dialog", name="VoiceBank, aussi dans ta poche")
    expect(pres).to_be_visible(timeout=10000)
    # D'abord le film, muet avec sous-titres (les navigateurs bloquent le son automatique)
    expect(pres.get_by_role("button", name="Activer le son")).to_be_visible()
    expect(pres.get_by_text("Bienvenue sur VoiceBank, la banque qui comprend ta voix.")).to_be_visible()
    page.wait_for_timeout(2200); page.screenshot(path="film_1_accueil.png")
    expect(pres.get_by_text(re.compile("Pose tes questions à la voix"))).to_be_visible(timeout=8000)
    page.wait_for_timeout(4000); page.screenshot(path="film_2_voix.png")
    pres.get_by_role("button", name="Passer la vidéo").click()
    expect(pres.get_by_role("button", name="Installer l'application")).to_be_visible()      # téléphone Android simulé
    expect(pres.get_by_role("button", name="Revoir la vidéo")).to_be_visible()
    page.wait_for_timeout(700)
    page.screenshot(path="presentation_telephone.png")
    pres.get_by_role("button", name="Continuer sur le site").click()
    expect(pres).to_be_hidden()
    print("1 bis. présentation « aussi dans ta poche » après les cookies, fermée par « Continuer sur le site »")
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

    # Nouvelle ouverture sur ordinateur : la présentation revient ; après une connexion, plus jamais
    ordi = b.sans_consentement(viewport={"width": 1366, "height": 860})
    o = ordi.new_page()
    o.add_init_script("localStorage.setItem('voicebank_consentement', JSON.stringify({version: 1, erreurs: false, date: new Date().toISOString()}))")
    o.goto(URL)
    pres_o = o.get_by_role("dialog", name="VoiceBank, aussi dans ta poche")
    expect(pres_o).to_be_visible(timeout=20000)
    # Le film enchaîne seul ses scènes (environ 25 s) : on en capture quelques-unes, puis la carte finale
    expect(pres_o.get_by_text("VoiceBank repère les opérations suspectes et t'alerte aussitôt.")).to_be_visible(timeout=15000)
    o.wait_for_timeout(3600); o.screenshot(path="film_3_fraude.png")
    expect(pres_o.get_by_text(re.compile("choisis simplement le bon nombre"))).to_be_visible(timeout=8000)
    o.wait_for_timeout(3300); o.screenshot(path="film_4_approbation.png")
    expect(pres_o.get_by_text(re.compile("De Douala à Paris"))).to_be_visible(timeout=8000)
    o.wait_for_timeout(3500); o.screenshot(path="film_5_monde.png")
    expect(pres_o.get_by_role("button", name="Installer sur cet ordinateur")).to_be_visible(timeout=10000)
    o.wait_for_timeout(900)
    o.screenshot(path="presentation_ordinateur.png")
    o.keyboard.press("Escape")
    expect(pres_o).to_be_hidden()
    o.get_by_role("button", name="Organisation").click()
    o.get_by_label("Identifiant ou e-mail").fill("rayan"); o.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    o.get_by_role("button", name="Se connecter").click()
    expect(o.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    o.get_by_role("button", name="Se déconnecter").click()
    nouvel_onglet = ordi.new_page(); nouvel_onglet.goto(URL)
    expect(nouvel_onglet.get_by_role("button", name="Organisation")).to_be_visible(timeout=20000)
    nouvel_onglet.wait_for_timeout(1500)
    expect(nouvel_onglet.get_by_role("dialog", name="VoiceBank, aussi dans ta poche")).to_have_count(0)
    print("5. sur ordinateur : présentation à l'ouverture ; plus jamais après une connexion sur l'appareil")

    page.goto(URL + "/confidentialite/#cookies")
    expect(page.locator("#cookies")).to_contain_text("Cookies et stockage")
    expect(page.get_by_text("Seulement avec votre accord")).to_be_visible()
    print("4. politique de confidentialité : tableau détaillé des cookies et du stockage")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
