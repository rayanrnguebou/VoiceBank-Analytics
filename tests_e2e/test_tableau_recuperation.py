"""Tableau de bord adapté à la base choisie + mot de passe oublié (code par e-mail)."""
import email
import re
import sys
import time
from email import policy
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

MDP = "Test-Admin-2026!"
NOUVEAU = "Mangrove-Kribi-2027!"


def dernier_code(apres):
    for _ in range(40):
        fichiers = sorted(f for f in MAILS.glob("*.eml") if float(f.stem) > apres)
        for f in reversed(fichiers):
            m = email.message_from_bytes(f.read_bytes(), policy=policy.default)
            code = re.match(r"(\d{6}) :", m["Subject"] or "")
            if code:
                return code.group(1), m
        time.sleep(0.25)
    raise AssertionError("aucun e-mail reçu")


with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_conversation','non'); localStorage.setItem('voicebank_voix','non');"
                         "sessionStorage.removeItem('voicebank_source')")
    page.goto(URL)
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill("rayan"); page.get_by_label("Mot de passe").fill(MDP)
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)

    # 1. Indicateurs de la démo, puis ceux de la base « Banque partenaire »
    expect(page.get_by_text("Crédits en cours")).to_be_visible()
    page.get_by_label("Données interrogées").select_option(label="Banque partenaire · PostgreSQL")
    expect(page.get_by_text("Montant des crédits")).to_be_visible(timeout=30000)
    expect(page.get_by_role("main").get_by_text("Comptes", exact=True)).to_be_visible()
    expect(page.get_by_text("Crédits en cours")).to_have_count(0)
    print("1. assistant : indicateurs de la base connectée (Clients, Comptes, Fraudes, Montant des crédits)")

    # 2. Tableau de bord : graphiques calculés d'après la base
    page.get_by_role("navigation").get_by_role("button", name=re.compile("^Tableau de bord")).click()
    expect(page.get_by_text("Vue d'ensemble de « Banque partenaire »")).to_be_visible()
    expect(page.get_by_role("region", name="Transactions par mois", exact=True)).to_be_visible(timeout=30000)
    expect(page.get_by_role("region", name="Clients par ville", exact=True)).to_be_visible()
    page.screenshot(path="tableau_source.png", full_page=True)
    # Changement de base sans quitter le tableau de bord, puis retour à la démo
    page.get_by_label("Données interrogées").select_option(label="Ventes 2025 · Excel / CSV")
    expect(page.get_by_text("Vue d'ensemble de « Ventes 2025 »")).to_be_visible()
    expect(page.get_by_role("region", name=re.compile("^Ventes")).first).to_be_visible(timeout=30000)
    expect(page.get_by_role("region", name="Clients par ville", exact=True)).to_have_count(0)
    titres = page.locator("section[aria-label]").evaluate_all("l => l.map(e => e.getAttribute('aria-label'))")
    page.screenshot(path="tableau_fichier.png", full_page=True)
    page.get_by_label("Données interrogées").select_option(value="")
    expect(page.get_by_text("Clients par banque")).to_be_visible()
    print("2. tableau de bord : graphiques de la base PostgreSQL, puis du fichier", titres, "puis de la démo")

    # 3. E-mail de récupération dans « Changer mon mot de passe »
    page.get_by_role("button", name="Changer mon mot de passe").first.click()
    dialogue = page.get_by_role("dialog")
    dialogue.get_by_role("button", name=re.compile("Ajouter|Modifier")).click()
    dialogue.get_by_label("Adresse e-mail (vide pour la retirer)").fill("rayan.test@exemple.cm")
    dialogue.get_by_label("Mot de passe actuel (pour confirmer)").fill(MDP)
    dialogue.get_by_role("button", name="Enregistrer l'adresse").click()
    expect(dialogue.get_by_text("rayan.test@exemple.cm")).to_be_visible()
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Se déconnecter").click()
    print("3. adresse de récupération enregistrée")

    # 4. Mot de passe oublié
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill("rayan")
    page.get_by_role("button", name="Mot de passe oublié ?").click()
    depart = time.time()
    page.get_by_role("button", name="Recevoir un code").click()
    expect(page.get_by_text(re.compile("un code à 6 chiffres vient d'y être envoyé"))).to_be_visible()
    code, mail = dernier_code(depart)
    assert mail["To"] == "rayan.test@exemple.cm", mail["To"]
    page.screenshot(path="oubli_code.png")
    page.get_by_label("Code reçu par e-mail").fill("000000" if code != "000000" else "111111")
    page.get_by_label("Nouveau mot de passe", exact=True).fill(NOUVEAU)
    page.get_by_label("Confirme le nouveau mot de passe").fill(NOUVEAU)
    page.get_by_role("button", name="Changer le mot de passe").click()
    expect(page.get_by_text("Code incorrect ou expiré")).to_be_visible()
    page.get_by_label("Code reçu par e-mail").fill(code)
    page.get_by_role("button", name="Changer le mot de passe").click()
    expect(page.get_by_text("Mot de passe changé. Tu peux te connecter.")).to_be_visible()
    page.get_by_label("Mot de passe").fill(NOUVEAU)
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    print("4. code reçu par e-mail (" + mail["Subject"][:6] + "…), mauvais code refusé, nouveau mot de passe actif")

    # Remise en état pour les autres tests : mot de passe d'origine, sans adresse de récupération
    page.evaluate("""async ([nouveau, mdp]) => {
      const api = 'http://localhost:8000';
      const t = (await (await fetch(api + '/auth/login', {method: 'POST', headers: {'content-type': 'application/json'},
        body: JSON.stringify({nom: 'rayan', mot_de_passe: nouveau})})).json()).access_token;
      const h = {'content-type': 'application/json', authorization: 'Bearer ' + t};
      await fetch(api + '/auth/email', {method: 'POST', headers: h, body: JSON.stringify({mot_de_passe: nouveau, email: null})});
      await fetch(api + '/auth/mot-de-passe', {method: 'POST', headers: h, body: JSON.stringify({actuel: nouveau, nouveau: mdp})});
    }""", [NOUVEAU, MDP])
    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
