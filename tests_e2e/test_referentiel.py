"""Toutes les villes et banques d'Afrique et d'Europe : pays → banques et localités du pays, recherche par sigle."""
import re
import subprocess
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

EMAIL = "referentiel@exemple.cm"
MDP = "Baobab-Douala-2026"



sql(f"DELETE FROM voicebank.paiements WHERE utilisateur = '{EMAIL}'; DELETE FROM voicebank.logs_vocaux WHERE utilisateur = '{EMAIL}'; "
    f"DELETE FROM voicebank.profils_facturation WHERE utilisateur = '{EMAIL}'; DELETE FROM voicebank.journal_audit WHERE utilisateur = '{EMAIL}'; "
    f"DELETE FROM voicebank.utilisateurs WHERE nom = '{EMAIL}'")


def choisir(page, champ, saisie, option):
    champ.click(); champ.press_sequentially(saisie)
    page.get_by_role("option", name=option).first.click()


with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_conversation','non'); localStorage.setItem('voicebank_voix','non');")
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))

    page.goto(URL)
    page.get_by_role("button", name=re.compile("^Visiteur")).click()
    page.get_by_label("Nom complet").fill("Awa Référentiel")
    page.get_by_label("E-mail (ce sera ton identifiant)").fill(EMAIL)
    page.get_by_label("Mot de passe").fill(MDP)
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name=re.compile("Démarrer l'essai gratuit")).click()
    expect(page.get_by_text("Essai gratuit").first).to_be_visible()

    # 1. Analyse : au Cameroun, les banques apprises par le modèle sont signalées
    nav("Analyse de transaction").click()
    banque = page.get_by_role("combobox", name="Banque")
    banque.click(); banque.press_sequentially("bic")
    expect(page.get_by_role("option", name=re.compile("BICEC"))).to_be_visible()
    expect(page.get_by_text("appris par le modèle").first).to_be_visible()
    page.screenshot(path="ref_cameroun.png")
    page.keyboard.press("Escape")
    print("1. Cameroun : banques du pays, celles apprises par le modèle signalées ; « bic » → BICEC")

    # 2. Gabon : banques et villes du Gabon, l'opération devient internationale
    choisir(page, page.get_by_role("combobox", name="Pays"), "gab", "Gabon")
    expect(page.get_by_label("Internationale")).to_have_value("Oui")
    choisir(page, banque, "bicig", re.compile("BICIG"))
    ville = page.get_by_role("combobox", name="Ville")
    ville.click(); ville.press_sequentially("port")
    expect(page.get_by_role("option", name="Port-Gentil")).to_be_visible()
    page.screenshot(path="ref_gabon.png")
    page.get_by_role("option", name="Port-Gentil").click()
    page.get_by_role("button", name="Analyser").click()
    expect(page.get_by_text(re.compile("n'a pas appris"))).to_be_visible(timeout=20000)
    expect(page.get_by_text("Ce qui explique ce résultat")).to_be_visible()
    page.screenshot(path="ref_gabon_resultat.png", full_page=True)
    print("2. Gabon : « bicig » → BICIG, Port-Gentil ; analyse faite, avec l'avertissement « n'a pas appris »")

    # 3. Europe : Londres trouvée en tapant « London », une petite ville française
    choisir(page, page.get_by_role("combobox", name="Pays"), "roy", "Royaume-Uni")
    ville.click(); ville.press_sequentially("london")
    expect(page.get_by_role("option", name="Londres")).to_be_visible()
    page.keyboard.press("Enter")
    expect(ville).to_have_value("Londres")
    choisir(page, page.get_by_role("combobox", name="Pays"), "fra", "France")
    choisir(page, ville, "chamb", "Chambéry")
    choisir(page, banque, "crédit agri", re.compile("^Crédit Agricole", re.I))
    print("3. Europe : « london » → Londres ; Chambéry ; Crédit Agricole")

    # 4. Score de crédit : banque belge
    nav("Score de crédit").click()
    choisir(page, page.get_by_role("combobox", name="Pays"), "belg", "Belgique")
    choisir(page, page.get_by_role("combobox", name="Banque"), "belf", re.compile("Belfius"))
    page.get_by_role("button", name="Évaluer").click()
    expect(page.get_by_text(re.compile("Belfius.*n'a pas appris|n'a pas appris.*Belfius"))).to_be_visible(timeout=20000)
    print("4. crédit : banque belge (Belfius) acceptée, avertissement affiché")

    # 5. Abonnement : banque du Sénégal pour la raison sociale, toutes les villes du pays
    sql(f"UPDATE voicebank.utilisateurs SET essai_fin = LOCALTIMESTAMP - INTERVAL '1 minute' WHERE nom = '{EMAIL}'")
    page.reload()
    page.locator("div", has=page.get_by_text("Semaine", exact=True)).last.get_by_role("button", name="Choisir").click()
    page.get_by_label("Secteur").select_option("banque")
    choisir(page, page.get_by_role("combobox", name="Pays"), "séné", "Sénégal")
    expect(page.get_by_label("Téléphone")).to_have_value("+221 ")
    rs = page.get_by_role("combobox", name="Raison sociale")
    rs.click(); rs.press_sequentially("cbao")
    expect(page.get_by_role("option", name=re.compile("CBAO"))).to_be_visible()
    page.screenshot(path="ref_abonnement.png")
    page.keyboard.press("Enter")
    expect(rs).to_have_value(re.compile("CBAO"))
    choisir(page, page.get_by_role("combobox", name="Ville"), "mbo", "Mbour")
    print("5. abonnement : « cbao » → CBAO Groupe Attijariwafa Bank, Mbour, indicatif +221")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
