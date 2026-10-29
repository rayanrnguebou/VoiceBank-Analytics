"""Questions favorites, surveillance (erreur de test), Mes appareils (alerte e-mail, déconnexion à distance) et
Mes données (export)."""
import email
import json
import re
import time
from email import policy

from playwright.sync_api import sync_playwright, expect

from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ADMIN_ORG, MDP = "direction@cooperative.cm", "Baobab-Douala-2026"
INIT = ("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non');"
        "localStorage.setItem('voicebank_demarrage_direction@cooperative.cm','non')")
sql("DELETE FROM voicebank.questions_favorites WHERE utilisateur IN ('rayan', 'direction@cooperative.cm')")


def mails(destinataire, motif, apres):
    res = []
    for f in sorted(MAILS.glob("*.eml")):
        if float(f.stem) < apres:
            continue
        m = email.message_from_bytes(f.read_bytes(), policy=policy.default)
        if destinataire in (m["To"] or "") and re.search(motif, m["Subject"] or ""):
            res.append(m)
    return res


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
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))

    # 1. Questions favorites : étoile, barre des favoris, envoi du lundi, relance en un clic
    connexion(page, "rayan", "Test-Admin-2026!")
    nav("Assistant vocal").click()
    page.get_by_role("button", name="Top 10 clients par solde", exact=True).click()
    expect(page.get_by_text("Résultats (1)")).to_be_visible(timeout=30000)
    page.get_by_role("button", name="Ajouter aux favoris").first.click()
    expect(page.get_by_text("Mes favoris")).to_be_visible(timeout=10000)
    page.get_by_role("button", name="Réglages du favori « Top 10 clients par solde »").click()
    page.get_by_role("checkbox", name="chaque lundi par e-mail").check()
    expect(page.get_by_label("envoyé chaque lundi")).to_be_visible(timeout=10000)
    page.reload()
    nav("Assistant vocal").click()
    page.get_by_role("list").get_by_role("button", name="Top 10 clients par solde", exact=True).click()
    expect(page.get_by_text("Résultats (2)")).to_be_visible(timeout=30000)
    expect(page.get_by_role("button", name="Retirer des favoris").first).to_have_attribute("aria-pressed", "true")
    page.screenshot(path="favoris.png", full_page=True)
    print("1. favori ajouté, envoi du lundi coché, relancé en un clic")

    # 2. Surveillance : erreur de test (Sentry non configuré en test : chaque partie le dit)
    nav("Maintenance").click()
    page.get_by_role("button", name="Envoyer une erreur de test").click()
    statut = page.get_by_role("status").filter(has_text="API")
    expect(statut).to_contain_text("SENTRY_DSN", timeout=20000)
    expect(statut).to_contain_text("REACT_APP_SENTRY_DSN")
    print("2. erreur de test : l'absence de Sentry est expliquée pour l'API et l'interface")

    # 3. Mes données : export JSON complet, effacement refusé pour un compte interne
    page.get_by_role("button", name="Changer mon mot de passe et la double authentification").click()
    expect(page.get_by_text("Mes appareils")).to_be_visible(timeout=10000)
    expect(page.get_by_text("cet appareil")).to_be_visible()
    with page.expect_download() as tele:
        page.get_by_role("button", name="Télécharger mes données").click()
    export = json.loads(open(tele.value.path(), encoding="utf-8").read())
    assert export["compte"]["identifiant"] == "rayan" and "Top 10 clients par solde" in json.dumps(export["questions_favorites"])
    assert "hash_mdp" not in json.dumps(export)
    expect(page.get_by_text(re.compile("Compte interne à la plateforme"))).to_be_visible()
    page.screenshot(path="securite_compte.png", full_page=True)
    print("3. export de mes données téléchargé ; effacement d'un compte interne expliqué")

    # 4. Nouvel appareil : e-mail d'alerte ; déconnexion à distance depuis l'autre appareil
    autre = b.new_context(viewport={"width": 1280, "height": 900})
    autre.add_init_script(INIT)
    telephone = autre.new_page()
    connexion(page, ADMIN_ORG, MDP)
    debut = time.time()
    connexion(telephone, ADMIN_ORG, MDP)              # navigateur jamais vu : nouvel identifiant d'appareil
    for _ in range(40):
        if mails(ADMIN_ORG, "Nouvelle connexion", debut):
            break
        time.sleep(0.25)
    alerte = mails(ADMIN_ORG, "Nouvelle connexion", debut)
    assert len(alerte) == 1, "pas d'e-mail de nouvelle connexion"
    texte = alerte[0].get_body(preferencelist=("plain",)).get_content()
    assert "Déconnecter les autres appareils" in texte
    page.get_by_role("button", name="Changer mon mot de passe et la double authentification").click()
    page.get_by_role("button", name="Déconnecter", exact=True).first.click()
    expect(page.get_by_text(re.compile("est déconnecté"))).to_be_visible(timeout=10000)
    telephone.reload()
    expect(telephone.get_by_role("button", name="Se connecter")).to_be_visible(timeout=20000)
    print("4. e-mail « nouvelle connexion » reçu ; l'autre appareil est déconnecté à distance")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
