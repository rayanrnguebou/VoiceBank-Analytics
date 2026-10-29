"""Suivi des alertes (assigner, commenter, verdict), rapport PDF, fiche des modèles, notifications."""
import re
import subprocess

from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ADMIN, MDP = "direction@cooperative.cm", "Baobab-Douala-2026"
ANALYSTE, MDP_A = "nadege.fouda@cooperative.cm", "Mangrove-Kribi-2027!"



sql("DELETE FROM voicebank.suivi_alertes WHERE id_source IN (SELECT id_source FROM voicebank.sources_donnees "
    "WHERE proprietaire = 'direction@cooperative.cm'); DELETE FROM voicebank.preferences_notifications "
    "WHERE utilisateur = 'direction@cooperative.cm'")


def connexion(page, nom, mdp):
    page.goto(URL)
    page.evaluate("sessionStorage.clear()")
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill(nom); page.get_by_label("Mot de passe").fill(mdp)
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)


with sync_playwright() as p:
    b = lancer(p)
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    page = ctx.new_page()
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non');"
                         "localStorage.setItem('voicebank_demarrage_direction@cooperative.cm','non')")
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))

    # 1. Alertes à traiter : assigner, commenter, verdict
    connexion(page, ADMIN, MDP)
    expect(page.get_by_label("Données interrogées").first).to_have_value(re.compile(r"\d+"), timeout=20000)
    nav("Alertes de fraude").click()
    onglet = page.get_by_role("tab", name=re.compile(r"^À traiter \(\d+\)"))
    expect(onglet).to_be_visible(timeout=60000)
    expect(onglet).to_have_attribute("aria-selected", "true")
    page.locator("button", has_text="Plus atypique que").first.click()
    expect(page.get_by_text("Suivi de l'alerte")).to_be_visible(timeout=20000)
    page.get_by_label("Assigner l'alerte").select_option(label="Nadège Fouda")
    expect(page.get_by_text("Assignée à nadege.fouda@cooperative.cm")).to_be_visible(timeout=10000)
    expect(page.locator("button", has_text="Plus atypique que").first.get_by_text("En cours")).to_be_visible()
    page.get_by_role("button", name="Fausse alerte").click()
    expect(page.get_by_role("alert")).to_contain_text("Explique ton verdict")
    page.get_by_placeholder(re.compile("client joint par téléphone")).fill("Paie mensuelle habituelle, confirmée avec l'agence.")
    page.screenshot(path="surveillance_suivi.png", full_page=False)
    page.get_by_role("button", name="Fausse alerte").click()
    expect(page.get_by_text("En cours → Fausse alerte")).to_be_visible(timeout=10000)
    page.get_by_role("tab", name=re.compile(r"^Fausses alertes \(1\)")).click()
    expect(page.locator("button", has_text="Plus atypique que")).to_have_count(1)
    print("1. alerte assignée à Nadège, verdict « fausse alerte » expliqué, historique et onglets à jour")

    # 2. Rapport PDF
    with page.expect_download(timeout=120000) as tel:
        page.get_by_role("button", name=re.compile(r"Rapport de la semaine \(PDF\)")).click()
    chemin = tel.value.path()
    contenu = open(chemin, "rb").read()
    assert contenu[:4] == b"%PDF" and len(contenu) > 3000, (len(contenu), contenu[:120])
    assert tel.value.suggested_filename.startswith("voicebank_rapport_hebdomadaire_")
    print(f"2. rapport PDF téléchargé ({len(contenu) // 1024} Ko)")

    # 3. Fiche des modèles
    nav("Fiche des modèles").click()
    expect(page.get_by_text("Détection des opérations atypiques")).to_be_visible(timeout=60000)
    expect(page.get_by_text("Dérive des données")).to_be_visible()
    expect(page.get_by_text(re.compile(r"1 alerte\(s\) jugée\(s\)"))).to_be_visible()
    page.screenshot(path="surveillance_fiche.png", full_page=True)
    print("3. fiche des modèles : données, seuils, fiabilité, verdicts, dérive")

    # 4. Notifications
    nav("Notifications").click()
    expect(page.get_by_text("Ce que je reçois par e-mail")).to_be_visible(timeout=20000)
    page.get_by_label(re.compile("Rapport hebdomadaire")).check()
    page.get_by_role("button", name="Enregistrer").click()
    expect(page.get_by_text("Préférences enregistrées.")).to_be_visible()
    page.reload()
    nav("Notifications").click()
    expect(page.get_by_label(re.compile("Rapport hebdomadaire"))).to_be_checked(timeout=20000)
    page.screenshot(path="surveillance_notifications.png")
    print("4. notifications : rapport hebdomadaire activé et conservé")

    # 5. L'analyste voit l'alerte qui lui était assignée, avec son historique
    page.get_by_role("button", name="Se déconnecter").click()
    connexion(page, ANALYSTE, MDP_A)
    nav("Alertes de fraude").click()
    page.get_by_role("tab", name=re.compile(r"^Fausses alertes")).click(timeout=60000)
    page.locator("button", has_text="Plus atypique que").first.click()
    expect(page.get_by_text("Paie mensuelle habituelle, confirmée avec l'agence.")).to_be_visible(timeout=20000)
    print("5. l'analyste retrouve l'alerte et tout son historique")

    # 6. Mobile
    page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(400)
    deborde = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    page.screenshot(path="surveillance_mobile.png")
    assert not deborde, "débordement horizontal sur mobile"
    print("6. mobile : pas de débordement")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
