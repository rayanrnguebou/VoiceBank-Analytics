"""v3.2 : comptes gérés par l'administrateur, mot de passe provisoire, lecture vocale, favicon."""
import re
import subprocess
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

# Synthèse vocale simulée : chaque phrase « dure » 300 ms, pour voir l'indicateur de lecture.
VOIX = """
window.__lu = [];
const s = window.speechSynthesis;
if (s) {
  let file = [], t = null;
  const suivant = () => { const u = file.shift(); if (!u) { t = null; return; }
    window.__lu.push(u.text); t = setTimeout(() => { u.onend && u.onend(); suivant(); }, 300); };
  s.speak = u => { file.push(u); if (!t) suivant(); };
  s.cancel = () => { const f = file; file = []; clearTimeout(t); t = null; f.forEach(u => u.onerror && u.onerror()); };
}
"""
NOUVEAU = "Cacao-Kribi-2026"


def connexion(page, nom, mdp):
    page.goto(URL)
    page.get_by_role("button", name="Organisation").click(); page.get_by_label("Identifiant ou e-mail").fill(nom)
    page.get_by_label("Mot de passe").fill(mdp)
    page.get_by_role("button", name="Se connecter").click()


subprocess.run(["psql", BASE, "-X", "-qc",
                "DELETE FROM voicebank.appareils_connus WHERE utilisateur = 'awa.bello'; DELETE FROM voicebank.echecs_connexion "
                "WHERE identifiant = 'awa.bello'; DELETE FROM voicebank.utilisateurs WHERE nom = 'awa.bello'"], check=True)

with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.add_init_script(VOIX)

    # Favicon
    page.goto(URL)
    assert page.locator('link[rel="icon"][type="image/svg+xml"]').count() == 1
    assert page.request.get(URL + "/favicon.svg").ok and page.request.get(URL + "/favicon.ico").ok
    print("1. favicon SVG + ICO servis")

    # Lecture : résumé puis commentaire, indicateur « Lecture » avec arrêt
    connexion(page, "rayan", "Test-Admin-2026!")
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible()
    champ = page.get_by_role("textbox", name="Question")
    champ.fill("Volume transactions par ville"); champ.press("Enter")
    stop = page.get_by_role("button", name="Arrêter la lecture")
    expect(stop).to_be_visible()
    page.wait_for_timeout(700)
    stop.click()
    expect(stop).to_be_hidden()
    nb = len(page.evaluate("window.__lu"))
    page.wait_for_timeout(700)
    assert len(page.evaluate("window.__lu")) == nb, "la lecture devait s'arrêter"
    print(f"2. indicateur de lecture + arrêt OK ({nb} phrases lues avant l'arrêt)")

    # Création d'un compte
    page.get_by_role("navigation").get_by_role("button", name="Comptes").click()
    expect(page.get_by_text("Pas d'inscription libre")).to_be_visible()
    page.get_by_label("Identifiant").fill("Awa.Bello")
    page.locator("form select").first.select_option("analyste")
    page.get_by_role("button", name="Créer").click()
    code = page.locator("code.select-all")
    expect(code).to_be_visible()
    provisoire = code.inner_text().strip()
    assert len(provisoire) == 16, provisoire
    ligne = page.locator("tr", has_text="awa.bello")
    expect(ligne).to_contain_text("Première connexion en attente")
    page.screenshot(path="v32_comptes.png", full_page=True)
    print("3. compte awa.bello créé, mot de passe provisoire affiché une fois")
    page.get_by_role("button", name="C'est noté, masquer").click()
    expect(code).to_be_hidden()
    page.get_by_role("button", name="Se déconnecter").click()

    # Première connexion : changement imposé
    connexion(page, "awa.bello", provisoire)
    expect(page.get_by_text("Première connexion")).to_be_visible()
    page.screenshot(path="v32_premiere_connexion.png")
    page.get_by_label("Mot de passe provisoire").fill(provisoire)
    page.get_by_label("Nouveau mot de passe", exact=True).fill("court")
    enregistrer = page.get_by_role("button", name="Enregistrer")
    assert enregistrer.is_disabled()
    page.get_by_label("Nouveau mot de passe", exact=True).fill(NOUVEAU)
    page.get_by_label("Confirme le nouveau mot de passe").fill(NOUVEAU)
    enregistrer.click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible()
    expect(page.get_by_text("Assistant vocal").first).to_be_visible()
    assert page.get_by_role("navigation").get_by_role("button", name="Comptes").count() == 0
    print("4. première connexion : mot de passe changé, accès analyste sans administration")

    # Changer son mot de passe depuis la barre latérale
    page.get_by_role("button", name="Changer mon mot de passe").click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_label("Mot de passe actuel").fill(NOUVEAU)
    dlg.get_by_label("Nouveau mot de passe", exact=True).fill("Manioc-Garoua-77")
    dlg.get_by_label("Confirme le nouveau mot de passe").fill("Manioc-Garoua-77")
    dlg.get_by_role("button", name="Enregistrer").click()
    expect(dlg.get_by_text("Mot de passe changé")).to_be_visible()
    dlg.get_by_role("button", name="Fermer", exact=True).last.click()
    champ = page.get_by_role("textbox", name="Question")
    champ.fill("Crédits en défaut"); champ.press("Enter")
    expect(page.get_by_text("Résultats (1)")).to_be_visible()     # la session continue
    print("5. changement de mot de passe volontaire, session conservée")
    page.get_by_role("button", name="Se déconnecter").click()

    # Mauvais mots de passe : blocage, puis réinitialisation par l'admin
    for _ in range(5):
        connexion(page, "awa.bello", "faux-mot-de-passe")
        expect(page.get_by_role("alert")).to_contain_text("Identifiants incorrects")
    connexion(page, "awa.bello", "Manioc-Garoua-77")
    expect(page.get_by_role("alert")).to_contain_text("Trop d'essais depuis cette connexion")   # l'adresse, pas le compte
    connexion(page, "rayan", "Test-Admin-2026!")
    page.get_by_role("navigation").get_by_role("button", name="Comptes").click()
    ligne = page.locator("tr", has_text="awa.bello")
    expect(ligne).to_contain_text("Actif")
    ligne.get_by_role("button", name=re.compile("Réinitialiser")).click()
    expect(page.locator("code.select-all")).to_be_visible()
    expect(ligne).to_contain_text("Première connexion en attente")
    print("6. 5 échecs : adresse bloquée (pas le compte), réinitialisation par l'administrateur")

    # Désactivation, et protections sur son propre compte
    ligne.get_by_role("button", name="Désactiver").click()
    expect(ligne).to_contain_text("Désactivé")
    moi = page.locator("tr", has_text="(toi)")
    assert moi.get_by_role("button", name="Désactiver").count() == 0
    page.get_by_role("navigation").get_by_role("button", name="Audit").click()
    expect(page.locator("td", has_text="Compte créé").first).to_be_visible()
    print("7. désactivation, son propre compte protégé, actions dans l'audit")

    # Mobile : écran de première connexion lisible
    m = b.new_page(viewport={"width": 390, "height": 800})
    m.goto(URL); m.screenshot(path="v32_mobile_login.png")
    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
