"""Maintenance : annonce prévue, page de maintenance pour les utilisateurs, accès conservé pour l'administrateur,
retour automatique, et bandeau de reconnexion quand le serveur ne répond plus."""
import re
import subprocess
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)



def remise_a_zero():
    import json, urllib.request
    def post(url, corps, jeton=None):
        req = urllib.request.Request("http://localhost:8000" + url, data=json.dumps(corps).encode(), method="POST",
                                     headers={"content-type": "application/json", **({"authorization": "Bearer " + jeton} if jeton else {})})
        return json.load(urllib.request.urlopen(req))
    t = post("/auth/login", {"nom": "rayan", "mot_de_passe": "Test-Admin-2026!"})["access_token"]
    post("/admin/maintenance", {"active": False}, t)


remise_a_zero()


def connexion(page, nom, mdp):
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill(nom); page.get_by_label("Mot de passe").fill(mdp)
    page.get_by_role("button", name="Se connecter").click()


with sync_playwright() as p:
    b = lancer(p)
    admin = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
    user = b.new_context(viewport={"width": 1280, "height": 900}).new_page()
    erreurs = []
    for pg in (admin, user):
        pg.on("pageerror", lambda e: erreurs.append(str(e)))
        pg.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non')")
    nav = lambda pg, nom: pg.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))

    admin.goto(URL); connexion(admin, "rayan", "Test-Admin-2026!")
    expect(admin.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    user.goto(URL); connexion(user, "analyste1", "Test-Analyste-2026!")
    expect(user.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)

    # 1. Annonce d'une maintenance prévue
    nav(admin, "Maintenance").click()
    debut = (datetime.now() + timedelta(days=1)).replace(hour=22, minute=0)
    admin.get_by_label("Message de l'annonce").fill("Le service sera indisponible une heure pour une mise à jour.")
    admin.get_by_label("Début").fill(debut.strftime("%Y-%m-%dT%H:%M"))
    admin.get_by_label("Fin").fill((debut + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"))
    admin.get_by_role("button", name="Publier l'annonce").click()
    expect(admin.get_by_text("Enregistré.")).to_be_visible()
    user.reload()
    expect(user.get_by_text(re.compile("Maintenance prévue"))).to_be_visible(timeout=20000)
    accueil = b.new_page(viewport={"width": 1280, "height": 900}); accueil.goto(URL)
    expect(accueil.get_by_text(re.compile("Maintenance prévue"))).to_be_visible(timeout=20000)
    accueil.screenshot(path="maintenance_annonce.png")
    print("1. annonce publiée : bandeau visible dans l'application et sur la page d'accueil")

    # 2. Activation : l'utilisateur voit la page de maintenance dès sa prochaine action
    admin.get_by_label("Message affiché aux utilisateurs").fill("Nous mettons à jour le modèle de détection de fraude.")
    admin.get_by_label("Retour prévu (facultatif)").fill((datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"))
    admin.once("dialog", lambda d: d.accept())
    admin.get_by_role("button", name="Activer la maintenance").click()
    expect(admin.get_by_text("Maintenance en cours :")).to_be_visible()
    champ = user.get_by_role("textbox", name="Question")
    champ.fill("Top 10 clients par solde"); champ.press("Enter")
    expect(user.get_by_role("heading", name="Maintenance en cours")).to_be_visible(timeout=20000)
    expect(user.get_by_text("Nous mettons à jour le modèle de détection de fraude.")).to_be_visible()
    expect(user.get_by_text(re.compile(r"Retour prévu .+ à \d\d:\d\d"))).to_be_visible()
    user.screenshot(path="maintenance_page.png")
    print("2. maintenance activée : l'utilisateur voit la page avec le message et l'heure de retour")

    # 3. Nouveau visiteur : page de maintenance ; « Accès administrateur » permet à l'admin de se connecter
    accueil.reload()
    expect(accueil.get_by_role("heading", name="Maintenance en cours")).to_be_visible(timeout=20000)
    accueil.get_by_role("button", name="Accès administrateur").click()
    connexion(accueil, "analyste1", "Test-Analyste-2026!")
    expect(accueil.get_by_text("Nous mettons à jour le modèle de détection de fraude.")).to_be_visible(timeout=20000)
    # L'administrateur, lui, continue de travailler
    nav(admin, "Assistant vocal").click()
    c = admin.get_by_role("textbox", name="Question"); c.fill("Top 10 clients par solde"); c.press("Enter")
    expect(admin.get_by_text("Résultats (1)")).to_be_visible(timeout=20000)
    print("3. connexion refusée aux utilisateurs pendant la maintenance ; l'administrateur travaille normalement")

    # 4. Fin de la maintenance : l'utilisateur retrouve l'application
    nav(admin, "Maintenance").click()
    admin.get_by_role("button", name="Terminer la maintenance").click()
    expect(admin.get_by_text("Service ouvert")).to_be_visible()
    user.get_by_role("button", name="Réessayer maintenant").click()
    expect(user.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    admin.get_by_role("button", name="Retirer l'annonce").click()
    expect(admin.get_by_role("button", name="Retirer l'annonce")).to_have_count(0)
    print("4. maintenance terminée : retour automatique à l'application")

    # 5. Serveur injoignable (redémarrage pendant une mise à jour) : bandeau de reconnexion
    user.route("**/localhost:8000/**", lambda r: r.abort("connectionrefused"))
    nav(user, "Tableau de bord").click()
    c = None
    nav(user, "Assistant vocal").click()
    q = user.get_by_role("textbox", name="Question"); q.fill("Crédits en défaut"); q.press("Enter")
    expect(user.get_by_text(re.compile("Le serveur ne répond pas"))).to_be_visible(timeout=20000)
    user.screenshot(path="maintenance_reconnexion.png")
    user.unroute("**/localhost:8000/**")
    expect(user.get_by_text(re.compile("Le serveur ne répond pas"))).to_have_count(0, timeout=30000)
    print("5. serveur coupé → bandeau « reconnexion automatique », qui disparaît dès son retour")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
