"""Champs à suggestions : on tape quelques lettres, on choisit dans la liste (pays, ville, banque, filtres)."""
import re
import subprocess
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

EMAIL = "listes@exemple.cm"
MDP = "Baobab-Douala-2026"



sql(f"DELETE FROM voicebank.paiements WHERE utilisateur = '{EMAIL}'; DELETE FROM voicebank.logs_vocaux WHERE utilisateur = '{EMAIL}'; "
    f"DELETE FROM voicebank.profils_facturation WHERE utilisateur = '{EMAIL}'; DELETE FROM voicebank.journal_audit WHERE utilisateur = '{EMAIL}'; "
    f"DELETE FROM voicebank.utilisateurs WHERE nom = '{EMAIL}'")

with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_conversation','non'); localStorage.setItem('voicebank_voix','non');")
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))

    page.goto(URL)
    page.get_by_role("button", name=re.compile("^Visiteur")).click()
    page.get_by_label("Nom complet").fill("Léa Listes")
    page.get_by_label("E-mail (ce sera ton identifiant)").fill(EMAIL)
    page.get_by_label("Mot de passe").fill(MDP)
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name=re.compile("Démarrer l'essai gratuit")).click()
    expect(page.get_by_text("Essai gratuit").first).to_be_visible()

    # 1. Analyse de transaction : « yao » → Yaoundé, sans accent ni majuscule
    nav("Analyse de transaction").click()
    ville = page.get_by_role("combobox", name="Ville")
    ville.click(); ville.press_sequentially("yao")
    expect(page.get_by_role("option", name="Yaoundé", exact=True)).to_be_visible()
    page.screenshot(path="listes_analyse.png")
    ville.press("Enter")
    expect(ville).to_have_value("Yaoundé")
    banque = page.get_by_role("combobox", name="Banque")
    banque.click(); banque.press_sequentially("eco")
    page.get_by_role("option", name=re.compile("Ecobank", re.I)).first.click()
    expect(banque).to_have_value(re.compile("Ecobank", re.I))
    page.get_by_role("button", name="Analyser").click()
    expect(page.get_by_text("Ce qui explique ce résultat")).to_be_visible(timeout=20000)
    expect(page.get_by_text(re.compile("Ville · Yaoundé|Yaoundé")).first).to_be_visible()
    print("1. analyse : ville et banque choisies en tapant quelques lettres")

    # 2. Abonnement : pays → indicatif téléphonique, villes du pays
    sql(f"UPDATE voicebank.utilisateurs SET essai_fin = LOCALTIMESTAMP - INTERVAL '1 minute' WHERE nom = '{EMAIL}'")
    page.reload()
    page.locator("div", has=page.get_by_text("Semaine", exact=True)).last.get_by_role("button", name="Choisir").click()
    tel = page.get_by_label("Téléphone")
    expect(tel).to_have_value("+237 ")
    pays = page.get_by_role("combobox", name="Pays")
    pays.click(); pays.press_sequentially("fra")
    expect(page.get_by_role("option", name="France", exact=True)).to_be_visible()
    pays.press("Enter")
    expect(pays).to_have_value("France")
    expect(tel).to_have_value("+33 ")
    v = page.get_by_role("combobox", name="Ville")
    v.click(); v.press_sequentially("ly")
    expect(page.get_by_role("option", name="Lyon", exact=True)).to_be_visible()
    page.screenshot(path="listes_abonnement.png")
    v.press("Enter")
    expect(v).to_have_value("Lyon")
    # saisie hors liste refusée pour le pays, acceptée pour une petite ville
    pays.click(); pays.press_sequentially("xyz")
    expect(page.get_by_text("Aucun résultat")).to_be_visible()
    page.keyboard.press("Escape")
    expect(pays).to_have_value("France")
    v.click(); v.press_sequentially("Villeurbanne"); v.press("Tab")
    expect(v).to_have_value("Villeurbanne")
    print("2. abonnement : « fra » → France, indicatif +33, villes françaises ; saisie libre pour une petite ville")

    # 3. Mobile : la liste reste dans l'écran
    page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(400)
    pays.click(); pays.press_sequentially("ca")
    expect(page.get_by_role("option", name="Cameroun", exact=True)).to_be_visible()
    debord = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    page.screenshot(path="listes_mobile.png")
    assert not debord, "débordement horizontal sur mobile"
    page.get_by_role("option", name="Cameroun", exact=True).click()
    expect(tel).to_have_value("+237 ")
    print("3. mobile : suggestions lisibles, clic → Cameroun, indicatif +237")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
