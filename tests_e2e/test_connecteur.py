"""Connecteur dans le navigateur : brancher une base PostgreSQL externe et un fichier Excel,
lire le diagnostic, puis interroger ces données depuis l'assistant."""
import re
import subprocess
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

subprocess.run(["psql", BASE, "-X", "-qc",
                "DELETE FROM voicebank.sources_donnees WHERE proprietaire = 'rayan'"], check=True)

with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.add_init_script("window.speechSynthesis && (window.speechSynthesis.speak = () => {});"
                         "localStorage.setItem('voicebank_conversation', 'non');")
    page.goto(URL)
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill("rayan"); page.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    page.get_by_role("button", name="Se connecter").click()
    page.get_by_role("navigation").get_by_role("button", name="Mes données").click()
    expect(page.get_by_text("Démonstration VoiceBank").first).to_be_visible()
    print("1. page « Mes données » avec la source de démonstration")

    # 2. Base PostgreSQL externe (schéma anglais inconnu)
    page.get_by_role("button", name="Connecter une source").click()
    page.get_by_role("button", name=re.compile("^PostgreSQL")).click()
    page.get_by_label("Nom de la source").fill("Banque partenaire")
    page.get_by_label("Adresse du serveur").fill(SOURCE_HOTE)
    page.get_by_label("Port").fill(SOURCE_PORT)
    page.get_by_label("Base de données").fill("banque_externe")
    page.get_by_label("Utilisateur (lecture seule)").fill("lecteur_ext")
    page.get_by_label("Mot de passe", exact=True).fill("Lecteur-2026!")
    page.get_by_role("button", name="Comment créer un compte en lecture seule ?").click()
    expect(page.get_by_text("GRANT SELECT ON ALL TABLES")).to_be_visible()
    page.get_by_role("button", name="Tester la connexion").click()
    expect(page.get_by_text(re.compile(r"Connecté · version 16.*5 table"))).to_be_visible()
    page.screenshot(path="connecteur_formulaire.png", full_page=True)
    page.get_by_role("button", name="Connecter et analyser").click()
    carte = page.get_by_role("group", name="Source Banque partenaire")
    expect(carte.get_by_text(re.compile("Banque · 5 tables"))).to_be_visible(timeout=30000)
    print("2. base PostgreSQL connectée et analysée")

    # 3. Diagnostic et carte des données
    carte.get_by_role("button", name="Diagnostic et carte").click()
    expect(page.get_by_text(re.compile("4 ligne\\(s\\) pointent vers"))).to_be_visible(timeout=20000)
    expect(page.get_by_text(re.compile("Dates dans le futur"))).to_be_visible()
    page.screenshot(path="connecteur_diagnostic.png", full_page=True)
    page.get_by_role("button", name=re.compile("^Carte des données")).click()
    page.get_by_role("button", name=re.compile("^payments")).click()
    expect(page.get_by_text("Secret", exact=True)).to_be_visible()
    page.get_by_role("button", name=re.compile("^customers")).click()
    expect(page.get_by_title("Donnée personnelle : masquée, jamais envoyée à l'IA").first).to_be_visible()
    page.screenshot(path="connecteur_carte.png", full_page=True)
    page.get_by_role("button", name="Questions suggérées").click()
    suggestion = page.get_by_role("button", name="Nombre de transactions frauduleuses par channel")
    expect(suggestion).to_be_visible()
    print("3. diagnostic (orphelins, dates futures), rôles, secrets et données personnelles affichés")

    # 4. Interroger depuis l'assistant
    suggestion.click()
    expect(page.get_by_label("Données interrogées")).to_have_value(re.compile(r"\d+"))
    expect(page.get_by_text("Base : Banque partenaire")).to_be_visible(timeout=20000)
    expect(page.locator("code", has_text="is_fraud").first).to_be_visible()
    champ = page.get_by_role("textbox", name="Question")
    champ.fill("Top 10 clients par solde"); champ.press("Enter")
    expect(page.get_by_text("Résultats (2)")).to_be_visible(timeout=20000)
    expect(page.locator("code", has_text="SUM(\"balance\")").first).to_be_visible()
    page.screenshot(path="connecteur_assistant.png", full_page=True)
    print("4. questions en français sur la base externe, depuis l'assistant")

    # 5. Fichier Excel
    page.get_by_label("Données interrogées").select_option("")
    page.get_by_role("navigation").get_by_role("button", name="Mes données").click()
    page.get_by_role("button", name="Connecter une source").click()
    page.get_by_role("button", name=re.compile(r"^Excel . CSV")).click()
    page.get_by_label("Nom de la source").fill("Ventes 2025")
    page.get_by_label("Fichiers").set_input_files(str(DONNEES / "ventes_2025.xlsx"))
    page.get_by_role("button", name="Importer et analyser").click()
    carte = page.get_by_role("group", name="Source Ventes 2025")
    expect(carte.get_by_text(re.compile("1 tables"))).to_be_visible(timeout=30000)
    carte.get_by_role("button", name="Interroger").click()
    champ.fill("Montant total des ventes par agence"); champ.press("Enter")
    expect(page.get_by_text("Base : Ventes 2025")).to_be_visible(timeout=20000)
    expect(page.get_by_text("Douala").first).to_be_visible()
    print("5. fichier Excel importé, analysé et interrogé")

    # 6. Un visiteur ne peut pas brancher de données
    page.get_by_role("button", name="Se déconnecter").click()
    subprocess.run(["psql", BASE, "-X", "-qc",
                    "DELETE FROM voicebank.utilisateurs WHERE nom = 'curieux.connecteur@exemple.cm'"], check=True)
    page.get_by_role("button", name=re.compile("^Visiteur")).click()
    page.get_by_label("Nom complet").fill("Curieux")
    page.get_by_label("E-mail (ce sera ton identifiant)").fill("curieux.connecteur@exemple.cm")
    page.get_by_label("Mot de passe").fill("Baobab-Douala-2026")
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name=re.compile("Démarrer l'essai")).click()
    page.get_by_role("navigation").get_by_role("button", name="Mes données").click()
    expect(page.get_by_role("button", name="S'abonner pour brancher ses données")).to_be_visible()
    assert page.get_by_text("Banque partenaire").count() == 0
    page.get_by_role("button", name="Diagnostic et carte").first.click()
    expect(page.get_by_text("Démonstration VoiceBank").first).to_be_visible(timeout=20000)
    print("6. visiteur : source de démonstration explorable, rien d'autre")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
