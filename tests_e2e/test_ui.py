import re, sys
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

with sync_playwright() as p:
    b = lancer(p)
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    erreurs = []
    page.on("pageerror", lambda e: erreurs.append(str(e)))

    page.goto(URL)
    expect(page.get_by_text("Tu es…")).to_be_visible()
    page.get_by_role("button", name="Organisation").click(); page.get_by_label("Identifiant ou e-mail").fill("rayan")
    page.get_by_label("Mot de passe").fill("mauvais")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("alert")).to_contain_text("Identifiants incorrects")
    print("1. refus mauvais mot de passe OK")

    page.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_text("Administrateur", exact=True)).to_be_visible()
    expect(page.get_by_text("Clients", exact=True)).to_be_visible()
    expect(page.get_by_text("3 000", exact=True).first).to_be_visible()
    page.screenshot(path="01_tableau.png", full_page=True)
    print("2. connexion + KPIs OK")

    for s in ["Top 10 clients par solde", "Crédits en défaut", "Transactions frauduleuses par banque",
              "Alertes critiques", "Clients diaspora France", "Volume transactions par ville"]:
        page.get_by_role("button", name=s, exact=True).click()
        expect(page.locator("p.font-medium", has_text=s).first).to_be_visible(timeout=10000)
    expect(page.get_by_text("Résultats (6)")).to_be_visible()
    page.screenshot(path="02_resultats.png", full_page=True)
    print("3. les 6 suggestions renvoient des résultats OK")

    page.get_by_placeholder("Pose ta question en français...").fill("quelle est la météo")
    page.keyboard.press("Enter")
    expect(page.get_by_role("alert")).to_contain_text("IA est indisponible")
    print("4. question incomprise -> message clair OK")

    page.get_by_role("button", name=re.compile(r"^Alertes de fraude")).click()
    expect(page.get_by_role("heading", name="Alertes fraude")).to_be_visible()
    page.get_by_role("button", name="Élevé", exact=True).click()
    expect(page.locator("span", has_text=re.compile("^Élevé$")).nth(1)).to_be_visible()
    print("5. onglet alertes + filtre Élevé OK")

    page.get_by_role("button", name=re.compile(r"^Analyse de transaction")).click()
    page.get_by_label("Montant (FCFA)").fill("4500000000")
    page.get_by_label("Internationale").select_option("Oui")
    page.get_by_role("button", name="Analyser").click()
    expect(page.get_by_text(re.compile(r"Score de fraude : \d"))).to_be_visible()
    page.screenshot(path="03_analyse.png", full_page=True)
    print("6. analyse IA :", page.get_by_text(re.compile("^Risque ")).inner_text())

    page.get_by_role("button", name=re.compile(r"^Historique")).click()
    page.get_by_role("button", name="Tout sélectionner").click()
    with page.expect_download(timeout=30000) as dl:
        page.get_by_role("button", name=re.compile("Rapport PDF")).click()
    chemin = "rapport.pdf"
    dl.value.save_as(chemin)
    print("7. export PDF OK :", dl.value.suggested_filename)

    page.reload()
    expect(page.get_by_text("Résultats (6)")).to_be_visible()
    print("8. historique conservé après rechargement OK")

    page.get_by_role("button", name="Se déconnecter").click()
    expect(page.get_by_text("Tu es…")).to_be_visible()
    page.reload()
    expect(page.get_by_text("Tu es…")).to_be_visible()
    print("9. déconnexion OK")

    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Organisation").click(); page.get_by_label("Identifiant ou e-mail").fill("analyste1")
    page.get_by_label("Mot de passe").fill("Test-Analyste-2026!")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_text("Analyste", exact=True)).to_be_visible()
    expect(page.get_by_text("Résultats (")).to_have_count(0)
    page.screenshot(path="04_mobile.png", full_page=True)
    print("10. compte analyste + historique isolé par utilisateur + mobile OK")

    print("Erreurs JS :", erreurs or "aucune")
    b.close()
    sys.exit(1 if erreurs else 0)
