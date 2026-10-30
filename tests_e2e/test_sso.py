"""Connexion avec un compte d'entreprise : boutons, redirection vers le fournisseur, retour, annulation, erreur."""
import json
import re
from urllib.parse import parse_qs, urlparse

import requests
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ADMIN, MDP = "direction@cooperative.cm", "Baobab-Douala-2026"

with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non');"
                         "localStorage.setItem('voicebank_demarrage_direction@cooperative.cm','non')")
    vers = []
    page.route(re.compile(r"https://(accounts\.google\.com|login\.microsoftonline\.com)/.*"),
               lambda r: (vers.append(r.request.url), r.fulfill(status=200, body="fournisseur"))[1])

    # 1. Boutons présents, redirection vers Google avec PKCE et adresse de retour
    page.goto(URL)
    page.get_by_role("button", name="Organisation").click()
    expect(page.get_by_role("button", name="Continuer avec Google")).to_be_visible(timeout=30000)
    expect(page.get_by_role("button", name="Continuer avec Microsoft")).to_be_visible()
    page.screenshot(path="sso_boutons.png")
    page.get_by_role("button", name="Continuer avec Google").click()
    page.wait_for_url(re.compile("accounts.google.com"), timeout=20000)
    q = parse_qs(urlparse(vers[-1]).query)
    assert q["redirect_uri"] == [f"{URL}/connexion-sso"] and q["code_challenge_method"] == ["S256"], q
    print("1. boutons Google/Microsoft ; redirection vers Google avec PKCE")

    # 2. Retour du fournisseur : l'interface termine la connexion avec le vérificateur gardé dans l'onglet
    jeton = requests.post(f"{API}/auth/login", json={"nom": ADMIN, "mot_de_passe": MDP}).json()
    recu = {}

    def fin(route):
        recu.update(json.loads(route.request.post_data))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(jeton),
                      headers={"Access-Control-Allow-Origin": URL})
    page.route(f"{API}/auth/sso/google/fin", fin)
    page.goto(f"{URL}/connexion-sso?code=code-e2e&state={q['state'][0]}")
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=30000)
    assert recu["code"] == "code-e2e" and recu["etat"] == q["state"][0] and len(recu["verificateur"]) >= 43
    assert urlparse(page.url).path == "/", page.url
    print("2. retour : connexion terminée, adresse nettoyée")
    page.unroute(f"{API}/auth/sso/google/fin")

    # 3. Annulation chez le fournisseur
    page.get_by_role("button", name="Se déconnecter").click()
    page.goto(f"{URL}/connexion-sso?error=access_denied")
    expect(page.get_by_role("alert")).to_have_text("Connexion annulée.", timeout=20000)
    page.get_by_role("button", name="Retour à la connexion").click()
    expect(page.get_by_role("button", name="Continuer avec Google")).to_be_visible(timeout=20000)
    print("3. annulation : message clair, retour à la connexion")

    # 4. Retour sans connexion commencée dans cet onglet : refus
    page.evaluate("sessionStorage.clear()")
    page.goto(f"{URL}/connexion-sso?code=x&state=y")
    expect(page.get_by_role("alert")).to_contain_text("autre onglet", timeout=20000)
    print("4. retour d'un autre onglet refusé")

    # 5. Code invalide transmis à l'API (Google injoignable ou refus) : erreur affichée, pas de session
    page.goto(URL)
    page.get_by_role("button", name="Organisation").click()
    page.get_by_role("button", name="Continuer avec Google").click()
    page.wait_for_url(re.compile("accounts.google.com"), timeout=20000)
    etat = parse_qs(urlparse(vers[-1]).query)["state"][0]
    page.goto(f"{URL}/connexion-sso?code=faux&state={etat}")
    expect(page.get_by_role("alert")).to_contain_text(re.compile("Google"), timeout=40000)
    assert page.get_by_role("button", name="Se déconnecter").count() == 0
    page.screenshot(path="sso_erreur.png")
    print("5. code refusé :", page.get_by_role("alert").inner_text())

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
