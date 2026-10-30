"""Organisation cliente : abonnement → administrateur → invitation par e-mail → activation → analyste
qui partage l'abonnement, sans administration de la plateforme. Captures des e-mails reçus."""
import email
import re
import subprocess
import sys
import time
from email import policy
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ADMIN_ORG = "direction@cooperative.cm"
ANALYSTE = "nadege.fouda@cooperative.cm"
MDP = "Baobab-Douala-2026"
MDP_A = "Mangrove-Kribi-2027!"



for e in (ADMIN_ORG, ANALYSTE):
    sql(f"DELETE FROM voicebank.codes_recuperation WHERE utilisateur = '{e}'; DELETE FROM voicebank.paiements WHERE utilisateur = '{e}'; "
        f"DELETE FROM voicebank.logs_vocaux WHERE utilisateur = '{e}'; DELETE FROM voicebank.profils_facturation WHERE utilisateur = '{e}'; "
        f"DELETE FROM voicebank.journal_audit WHERE utilisateur = '{e}'; DELETE FROM voicebank.appareils_connus WHERE utilisateur = '{e}'; "
        f"DELETE FROM voicebank.double_authentification WHERE utilisateur = '{e}'; DELETE FROM voicebank.echecs_connexion WHERE identifiant = '{e}'")
sql(f"DELETE FROM voicebank.sources_donnees WHERE proprietaire IN ('{ADMIN_ORG}', '{ANALYSTE}'); "
    f"UPDATE voicebank.utilisateurs SET id_org = NULL WHERE nom IN ('{ADMIN_ORG}', '{ANALYSTE}') OR id_org IN "
    f"(SELECT id_org FROM voicebank.organisations WHERE cree_par = '{ADMIN_ORG}'); "
    f"DELETE FROM voicebank.organisations WHERE cree_par = '{ADMIN_ORG}'; "
    f"DELETE FROM voicebank.utilisateurs WHERE nom IN ('{ADMIN_ORG}', '{ANALYSTE}')")


def mail(destinataire, motif, apres):
    for _ in range(60):
        for f in sorted(MAILS.glob("*.eml"), reverse=True):
            if float(f.stem) < apres:
                continue
            m = email.message_from_bytes(f.read_bytes(), policy=policy.default)
            if destinataire in (m["To"] or "") and re.search(motif, m["Subject"] or ""):
                return m, f
        time.sleep(0.25)
    raise AssertionError(f"pas d'e-mail « {motif} » pour {destinataire}")


def capture_mail(navigateur, m, chemin):
    html = m.get_body(preferencelist=("html",)).get_content()
    p = navigateur.new_page(viewport={"width": 700, "height": 900})
    p.set_content(html); p.screenshot(path=chemin, full_page=True); p.close()


with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("window.speechSynthesis && (window.speechSynthesis.speak = () => {});"
                         "localStorage.setItem('voicebank_conversation', 'non');")
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))
    debut = time.time()

    # 1. Une directrice s'inscrit, reçoit l'e-mail de bienvenue et abonne son organisation
    page.goto(URL)
    page.get_by_role("button", name=re.compile("^Visiteur")).click()
    page.get_by_label("Nom complet").fill("Mireille Ekambi")
    page.get_by_label("E-mail (ce sera ton identifiant)").fill(ADMIN_ORG)
    page.get_by_label("Mot de passe").fill(MDP)
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name=re.compile("Démarrer l'essai gratuit")).click()
    expect(page.get_by_text("Essai gratuit").first).to_be_visible()
    bienvenue, _ = mail(ADMIN_ORG, "Bienvenue", debut)
    nav("Abonnement").click()
    page.locator("div", has=page.get_by_text("Mois", exact=True)).last.get_by_role("button", name="Choisir").click()
    page.get_by_label("Raison sociale").fill("Coopérative du Moungo")
    page.get_by_label("Ville").fill("Nkongsamba")
    page.get_by_label("Fonction").fill("Directrice générale")
    page.get_by_label("Téléphone").fill("+237 690 11 22 33")
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name=re.compile(r"Payer 6\s000 FCFA")).click()
    expect(page.get_by_text(re.compile("Paiement confirmé"))).to_be_visible(timeout=15000)
    recu, _ = mail(ADMIN_ORG, "Paiement confirmé", debut)
    expect(page.get_by_text("Admin · Coopérative du Moungo")).to_be_visible()
    assert nav("Comptes").count() == 0, "l'administration de la plateforme ne doit plus être visible"
    print("1. inscription → e-mail de bienvenue → abonnement Mois → administratrice de « Coopérative du Moungo », reçu envoyé")

    # 2. Elle invite une analyste
    nav("Membres").click()
    expect(page.get_by_text("1 / 10")).to_be_visible()
    page.get_by_label("Nom complet").fill("Nadège Fouda")
    page.get_by_label("E-mail professionnel").fill(ANALYSTE)
    page.get_by_role("button", name="Inviter").click()
    expect(page.get_by_text(f"e-mail d'invitation envoyé à {ANALYSTE}")).to_be_visible(timeout=15000)
    expect(page.get_by_text("Invitation envoyée")).to_be_visible()
    expect(page.get_by_text("2 / 10")).to_be_visible()
    page.screenshot(path="org_membres.png", full_page=True)
    invitation, _ = mail(ANALYSTE, "Invitation à rejoindre", debut)
    lien = re.search(r"(http://localhost:3000/\?invitation=[^\s\"<]+)", invitation.get_body(preferencelist=("plain",)).get_content()).group(1)
    print("2. invitation envoyée ; e-mail reçu :", invitation["Subject"])

    # 3. L'analyste clique le lien, choisit son mot de passe et arrive connectée
    page.get_by_role("button", name="Se déconnecter").click()
    page.goto(lien)
    expect(page.get_by_text("Activer ton compte")).to_be_visible()
    page.get_by_label("Mot de passe", exact=True).fill(MDP_A)
    page.get_by_label("Confirme le mot de passe").fill(MDP_A)
    page.screenshot(path="org_activation.png")
    page.get_by_role("button", name="Activer mon compte").click()
    expect(page.get_by_text("Analyste · Coopérative du Moungo")).to_be_visible(timeout=15000)
    assert "invitation=" not in page.url
    print("3. lien d'activation → mot de passe choisi → connectée en analyste")

    # 4. Elle partage l'abonnement, sans le gérer, et ne voit pas l'administration de la plateforme
    expect(page.get_by_text("Géré par l'administrateur de l'organisation")).to_be_visible()
    assert nav("Comptes").count() == 0 and nav("Audit").count() == 0
    champ = page.get_by_role("textbox", name="Question")
    champ.fill("Top 10 clients par solde"); champ.press("Enter")
    expect(page.get_by_text("Résultats (1)")).to_be_visible(timeout=20000)
    nav("Abonnement").click()
    expect(page.get_by_text(re.compile("Ton accès est inclus dans l'abonnement mois"))).to_be_visible()
    nav("Membres").click()
    expect(page.get_by_text("Nadège Fouda (toi)")).to_be_visible()
    assert page.get_by_role("button", name="Inviter").count() == 0
    page.screenshot(path="org_analyste.png", full_page=True)
    print("4. l'analyste pose ses questions avec l'abonnement de l'organisation ; aucune gestion ni administration")

    # 5. Le super-administrateur voit l'organisation
    page.get_by_role("button", name="Se déconnecter").click()
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill("rayan"); page.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    page.get_by_role("button", name="Se connecter").click()
    nav("Abonnements").click()
    ligne = page.locator("tr", has_text="Coopérative du Moungo").first
    expect(ligne).to_contain_text("2/10")
    page.get_by_role("button", name="Envoyer un test").click()
    expect(page.get_by_text(re.compile("E-mail de test envoyé|ajoute ton e-mail"))).to_be_visible(timeout=15000)
    page.screenshot(path="org_super_admin.png", full_page=True)
    print("5. super-administrateur : organisation listée (2/10 comptes), test d'e-mail disponible")

    for m, nom in ((invitation, "mail_invitation.png"), (recu, "mail_recu.png"), (bienvenue, "mail_bienvenue.png")):
        capture_mail(b, m, nom)
    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
