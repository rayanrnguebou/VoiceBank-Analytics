"""Réveil du serveur, export CSV, déconnexion après inactivité."""
import csv
import io
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)



def connexion(page):
    page.get_by_role("button", name="Organisation").click(); page.get_by_label("Identifiant ou e-mail").fill("rayan")
    page.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)


with sync_playwright() as p:
    b = lancer(p)
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("window.speechSynthesis && (window.speechSynthesis.speak = () => {});"
                         "localStorage.setItem('voicebank_conversation', 'non');")

    # 1. Serveur endormi : message de réveil, puis connexion possible
    def lent(route):
        page.wait_for_timeout(4000); route.continue_()
    page.route("**/health", lent)
    page.goto(URL)
    expect(page.get_by_text("Démarrage du serveur")).to_be_visible(timeout=4000)
    expect(page.get_by_text("Démarrage du serveur")).to_be_hidden(timeout=10000)
    page.unroute("**/health")
    print("1. message « Démarrage du serveur… » affiché pendant le réveil de l'API")

    # 2. Export CSV
    page.clock.install()
    connexion(page)
    champ = page.get_by_role("textbox", name="Question")
    champ.fill("Transactions frauduleuses par banque"); champ.press("Enter")
    expect(page.get_by_text("Résultats (1)")).to_be_visible()
    with page.expect_download() as dl:
        page.get_by_role("button", name="Exporter en CSV (Excel)").click()
    f = dl.value
    contenu = open(f.path(), encoding="utf-8-sig").read()
    lignes = list(csv.reader(io.StringIO(contenu), delimiter=";"))
    assert f.suggested_filename.startswith("voicebank_transactions-frauduleuses-par-banque_")
    assert len(lignes) == 11 and "banque" in lignes[0], lignes[:2]
    print("2. export CSV :", f.suggested_filename, "→", lignes[0], lignes[1])

    # 3. Inactivité : avertissement à 14 min, « Rester connecté », puis déconnexion à 15 min
    page.clock.fast_forward("14:05")
    expect(page.get_by_role("alertdialog")).to_be_visible()
    expect(page.get_by_text("Toujours là ?")).to_be_visible()
    page.get_by_role("button", name="Rester connecté").click()
    expect(page.get_by_role("alertdialog")).to_be_hidden()
    page.clock.fast_forward("14:05")
    expect(page.get_by_role("alertdialog")).to_be_visible()
    page.screenshot(path="inactivite.png")
    page.clock.fast_forward("01:00")
    expect(page.get_by_role("button", name="Se connecter")).to_be_visible()
    expect(page.get_by_text("Déconnecté après 15 minutes d'inactivité")).to_be_visible()
    print("3. avertissement d'inactivité, « Rester connecté », puis déconnexion automatique avec message")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
