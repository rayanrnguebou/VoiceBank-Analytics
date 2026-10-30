"""Organisation avec sa propre base : guide de démarrage, base par défaut, fraude et crédit appris sur ses données."""
import re
import subprocess

from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ADMIN, MDP = "direction@cooperative.cm", "Baobab-Douala-2026"
ANALYSTE, MDP_A = "nadege.fouda@cooperative.cm", "Mangrove-Kribi-2027!"



sql("UPDATE voicebank.organisations SET source_defaut = NULL WHERE nom = 'Coopérative du Moungo'; "
    "DELETE FROM voicebank.sources_donnees WHERE proprietaire = 'direction@cooperative.cm'")


def connexion(page, nom, mdp):
    page.goto(URL)
    page.evaluate("sessionStorage.clear()")
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill(nom); page.get_by_label("Mot de passe").fill(mdp)
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)


with sync_playwright() as p:
    b = lancer(p)
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non');"
                         "localStorage.removeItem('voicebank_demarrage_direction@cooperative.cm')")
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))

    # 1. Guide de démarrage, puis branchement de la base de l'organisation
    connexion(page, ADMIN, MDP)
    expect(page.get_by_text("Bien démarrer")).to_be_visible()
    page.screenshot(path="examen_demarrage.png")
    page.get_by_role("button", name="Mes données").first.click()
    page.get_by_role("button", name="Connecter une source").click()
    page.get_by_role("button", name=re.compile("^PostgreSQL")).click()
    page.get_by_label("Nom de la source").fill("Banque partenaire")
    page.get_by_label("Adresse du serveur").fill(SOURCE_HOTE)
    page.get_by_label("Port").fill(SOURCE_PORT)
    page.get_by_label("Base de données").fill("banque_externe")
    page.get_by_label("Utilisateur (lecture seule)").fill("lecteur_ext")
    page.get_by_label("Mot de passe", exact=True).fill("Lecteur-2026!")
    page.get_by_role("button", name="Tester la connexion").click()
    expect(page.get_by_text(re.compile("Connecté · version"))).to_be_visible(timeout=30000)
    page.get_by_role("button", name="Connecter et analyser").click()
    carte = page.get_by_role("group", name="Source Banque partenaire")
    expect(carte.get_by_role("button", name="Définir par défaut")).to_be_visible(timeout=60000)
    carte.get_by_role("button", name="Définir par défaut").click()
    expect(carte.get_by_text("Par défaut")).to_be_visible()
    print("1. guide de démarrage affiché ; base branchée et définie par défaut pour l'organisation")

    # 2. L'analyste arrive directement sur la base de l'organisation
    page.get_by_role("button", name="Se déconnecter").click()
    connexion(page, ANALYSTE, MDP_A)
    expect(page.get_by_label("Données interrogées").first).to_have_value(re.compile(r"\d+"), timeout=20000)
    expect(page.get_by_text("Bien démarrer")).to_have_count(0)
    print("2. l'analyste arrive directement sur « Banque partenaire » (base par défaut)")

    # 3. Fraude : opérations atypiques apprises sur la base
    nav("Alertes de fraude").click()
    expect(page.get_by_role("heading", name="Opérations atypiques")).to_be_visible(timeout=60000)
    expect(page.get_by_text(re.compile("Modèle appris sur .* opérations récentes de « Transactions »"))).to_be_visible()
    page.locator("button", has_text="Plus atypique que").first.click()
    expect(page.get_by_text("Que faire ?")).to_be_visible()
    page.screenshot(path="examen_fraude_base.png", full_page=True)
    print("3. alertes : opérations atypiques de la base, raisons et conduite à tenir")

    # 4. Analyse d'une opération sur la base
    nav("Analyse de transaction").click()
    expect(page.get_by_text(re.compile("comparée aux habitudes de « Transactions »"))).to_be_visible(timeout=30000)
    page.get_by_label(re.compile(r"^Montant")).fill("90000000")
    page.get_by_role("button", name="Analyser").click()
    expect(page.get_by_text(re.compile("fois le montant habituel"))).to_be_visible(timeout=20000)
    expect(page.get_by_text("Que faire ?")).to_be_visible()
    page.screenshot(path="examen_analyse_base.png", full_page=True)
    print("4. analyse d'une opération : comparée aux habitudes de la base, conseils")

    # 5. Crédit : portefeuille de la base
    nav("Score de crédit").click()
    expect(page.get_by_role("heading", name="Portefeuille de crédits")).to_be_visible(timeout=60000)
    expect(page.get_by_text("Où se concentrent les défauts ?")).to_be_visible()
    page.screenshot(path="examen_credit_base.png", full_page=True)
    print("5. crédit : taux de défaut par segment et crédits en cours à risque, appris sur la base")

    # 6. Retour à la démonstration : modèles pré-entraînés, conseils
    page.get_by_label("Données interrogées").first.select_option(value="")
    expect(page.get_by_text("Démonstration : banque fictive, modèles pré-entraînés.")).to_be_visible()
    page.get_by_role("button", name="Évaluer").click()
    expect(page.get_by_text("Que faire ?")).to_be_visible(timeout=20000)
    nav("Analyse de transaction").click()
    page.get_by_label("Heure de l'opération").fill("03:00")
    page.get_by_role("button", name="Analyser").click()
    expect(page.get_by_text("Ce qui explique ce résultat")).to_be_visible(timeout=20000)
    expect(page.get_by_text(re.compile("modèle entraîné", re.I))).to_be_visible()
    assert page.get_by_text(re.compile("l'heure n'a pas été apprise")).count() == 0
    page.screenshot(path="examen_analyse_demo.png", full_page=True)
    print("6. démonstration : plus de message sur l'heure ; explications et conseils")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
