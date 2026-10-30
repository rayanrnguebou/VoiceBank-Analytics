"""Rôles fins : auditeur (journal, consultation sans traitement), accès d'un membre limité à certaines bases."""
import email
import re
import subprocess
import sys
import time
from email import policy
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ADMIN, MDP = "direction@cooperative.cm", "Baobab-Douala-2026"
AUDITRICE, MDP_AU = "controle.interne@cooperative.cm", "Ebene-Limbe-2028!"



sql(f"DELETE FROM voicebank.acces_sources WHERE utilisateur IN ('{AUDITRICE}', 'nadege.fouda@cooperative.cm'); "
    f"DELETE FROM voicebank.preferences_notifications WHERE utilisateur = '{AUDITRICE}'; "
    f"DELETE FROM voicebank.codes_recuperation WHERE utilisateur = '{AUDITRICE}'; "
    f"DELETE FROM voicebank.journal_audit WHERE utilisateur = '{AUDITRICE}'; "
    f"DELETE FROM voicebank.utilisateurs WHERE nom = '{AUDITRICE}'")


def mail(destinataire, motif, apres):
    for _ in range(60):
        for f in sorted(MAILS.glob("*.eml"), reverse=True):
            if float(f.stem) < apres:
                continue
            m = email.message_from_bytes(f.read_bytes(), policy=policy.default)
            if destinataire in (m["To"] or "") and re.search(motif, m["Subject"] or ""):
                return m
        time.sleep(0.25)
    raise AssertionError(f"pas d'e-mail « {motif} » pour {destinataire}")


def connexion(page, nom, mdp):
    page.goto(URL)
    page.evaluate("sessionStorage.clear()")
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill(nom); page.get_by_label("Mot de passe").fill(mdp)
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)


with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non');"
                         "localStorage.setItem('voicebank_demarrage_direction@cooperative.cm','non')")
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))
    debut = time.time()

    # 1. L'administratrice invite une auditrice (rôle expliqué) et limite les bases de l'analyste
    connexion(page, ADMIN, MDP)
    nav("Membres").click()
    page.get_by_label("Nom complet").fill("Clarisse Ngo")
    page.get_by_label("E-mail professionnel").fill(AUDITRICE)
    page.get_by_label("Rôle du nouveau membre").select_option("auditeur")
    expect(page.get_by_text(re.compile("Auditeur : Consulte tout et lit le journal"))).to_be_visible()
    page.get_by_role("button", name="Inviter").click()
    expect(page.get_by_text(f"e-mail d'invitation envoyé à {AUDITRICE}")).to_be_visible(timeout=15000)
    page.get_by_role("button", name=re.compile("^Bases de Nadège Fouda")).click()
    page.get_by_role("radio", name=re.compile("^Seulement")).check()
    page.get_by_role("dialog").get_by_role("checkbox").first.check()
    page.get_by_role("dialog").get_by_role("button", name="Enregistrer").click()
    expect(page.get_by_role("button", name=re.compile("^Bases de Nadège Fouda"))).to_have_text(re.compile("1 base sur 1"), timeout=10000)
    page.screenshot(path="roles_membres.png", full_page=True)
    print("1. auditrice invitée ; accès de l'analyste limité à une base")

    # 2. L'auditrice active son compte : journal visible, alertes en lecture seule
    m = mail(AUDITRICE, "Invitation à rejoindre", debut)
    assert "Auditeur (contrôle interne)" in m.get_body(preferencelist=("plain",)).get_content()
    lien = re.search(r"(http://localhost:3000/\?invitation=[^\s\"<]+)", m.get_body(preferencelist=("plain",)).get_content()).group(1)
    page.get_by_role("button", name="Se déconnecter").click()
    page.goto(lien)
    page.get_by_label("Mot de passe", exact=True).fill(MDP_AU)
    page.get_by_label("Confirme le mot de passe").fill(MDP_AU)
    page.get_by_role("button", name="Activer mon compte").click()
    expect(page.get_by_text("Auditeur · Coopérative du Moungo")).to_be_visible(timeout=15000)
    nav("Journal").click()
    expect(page.get_by_role("heading", name="Journal de l'organisation")).to_be_visible(timeout=20000)
    expect(page.get_by_text("Paie mensuelle habituelle, confirmée avec l'agence.").first).to_be_visible()
    page.get_by_role("tab", name=re.compile("^Activité")).click()
    expect(page.get_by_text("Accès aux bases modifié").first).to_be_visible()
    page.screenshot(path="roles_journal.png", full_page=True)
    nav("Alertes de fraude").click()
    page.get_by_role("tab", name=re.compile("^Fausses alertes")).click(timeout=60000)
    page.locator("button", has_text="Plus atypique que").first.click()
    expect(page.get_by_text("Ton rôle permet de consulter les alertes, pas de les traiter.")).to_be_visible(timeout=20000)
    assert page.get_by_role("button", name="Fraude confirmée").count() == 0
    print("2. auditrice : journal (alertes et activité), alertes en lecture seule")

    # 3. L'analyste ne voit pas le journal
    page.get_by_role("button", name="Se déconnecter").click()
    connexion(page, "nadege.fouda@cooperative.cm", "Mangrove-Kribi-2027!")
    assert page.get_by_role("navigation").get_by_role("button", name=re.compile("^Journal")).count() == 0
    print("3. analyste : pas de journal")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
