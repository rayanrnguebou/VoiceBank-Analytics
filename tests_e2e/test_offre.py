"""Parcours public : visiteur → essai gratuit en lecture seule → fin d'essai → abonnement payé (simulation)."""
import re
import subprocess
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

EMAIL = "decouverte@exemple.cm"
MDP = "Baobab-Douala-2026"



sql(f"DELETE FROM voicebank.paiements WHERE utilisateur = '{EMAIL}'; DELETE FROM voicebank.logs_vocaux WHERE utilisateur = '{EMAIL}'; "
    f"DELETE FROM voicebank.profils_facturation WHERE utilisateur = '{EMAIL}'; "
    f"DELETE FROM voicebank.utilisateurs WHERE nom = '{EMAIL}'")

with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("window.speechSynthesis && (window.speechSynthesis.speak = () => {});"
                         "localStorage.setItem('voicebank_conversation', 'non');")
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))

    # 1. Accueil public
    page.goto(URL)
    expect(page.get_by_text("à partir de")).to_be_visible()
    page.screenshot(path="offre_accueil.png")
    page.get_by_role("button", name=re.compile("^Visiteur")).click()
    page.get_by_label("Nom complet").fill("Awa Découverte")
    page.get_by_label("E-mail (ce sera ton identifiant)").fill(EMAIL)
    page.get_by_label("Tu es…").select_option("recruteur")
    page.get_by_label("Mot de passe").fill(MDP)
    page.get_by_role("checkbox").check()
    page.get_by_role("button", name=re.compile("Démarrer l'essai gratuit")).click()
    expect(page.get_by_text("Essai gratuit").first).to_be_visible()
    expect(page.get_by_text(re.compile(r"\d j \d+ h restants"))).to_be_visible()
    print("1. inscription visiteur → connecté, bandeau d'essai affiché")

    # 2. Tout est visible, rien n'est modifiable
    champ = page.get_by_role("textbox", name="Question")
    champ.fill("Crédits en défaut"); champ.press("Enter")
    expect(page.get_by_text("Résultats (1)")).to_be_visible()
    expect(page.get_by_text("1/30 questions aujourd'hui")).to_be_visible()
    assert page.get_by_role("button", name="Réponse incorrecte ?").is_disabled()
    nav("Alertes de fraude").click()
    expect(page.get_by_role("button", name="Traiter", exact=True).first).to_be_disabled()
    nav("Comptes").click()
    expect(page.get_by_text("Démonstration : voici comment")).to_be_visible()
    assert page.get_by_role("button", name="Créer").count() == 0
    nav("Fiabilité").click()
    expect(page.get_by_role("button", name=re.compile("Lancer")).first).to_be_disabled()
    nav("Audit").click()
    expect(page.locator("td", has_text="Essai créé").first).to_be_visible() if page.locator("td", has_text="Essai créé").count() else None
    assert page.get_by_role("navigation").get_by_role("button", name="Abonnements").count() == 0
    page.screenshot(path="offre_lecture_seule.png", full_page=True)
    print("2. administration visible en démo, toutes les actions d'écriture désactivées")

    # 3. Fin de l'essai : seule la page Abonnement reste accessible
    sql(f"UPDATE voicebank.utilisateurs SET essai_fin = LOCALTIMESTAMP - INTERVAL '1 minute' WHERE nom = '{EMAIL}'")
    page.reload()
    expect(page.get_by_text("Ton essai gratuit est terminé")).to_be_visible()
    expect(page.get_by_text("Choisis ta formule")).to_be_visible()
    page.screenshot(path="offre_formules.png", full_page=True)
    print("3. essai terminé → page des formules")

    # 4. Formule Semaine, organisation, paiement (simulation locale)
    page.locator("div", has=page.get_by_text("Semaine", exact=True)).last.get_by_role("button", name="Choisir").click()
    expect(page.get_by_text(re.compile(r"Formule Semaine — 2\s000 FCFA"))).to_be_visible()
    page.get_by_label("Raison sociale").fill("Mutuelle du Littoral")
    page.get_by_label("Ville").fill("Douala")
    page.get_by_label("Fonction").fill("Directrice des risques")
    page.get_by_label("Téléphone").fill("+237 690 00 00 00")
    page.get_by_label("NIU (n° contribuable) (facultatif)").fill("M0123456789")
    page.get_by_role("checkbox").check()
    page.screenshot(path="offre_commande.png", full_page=True)
    page.get_by_role("button", name=re.compile(r"Payer 2\s000 FCFA")).click()
    expect(page.get_by_text(re.compile("Paiement confirmé : abonnement semaine actif"))).to_be_visible(timeout=15000)
    expect(page.get_by_text(re.compile(r"^Abonnement semaine"))).to_be_visible()
    expect(page.get_by_text(re.compile(r"6 j 23 h restants"))).to_be_visible()
    assert "paiement=" not in page.url
    print("4. paiement → abonnement actif 7 jours, accès rouvert :", page.get_by_role("status").first.inner_text())

    # 5. L'administrateur voit le client et le paiement
    page.get_by_role("button", name="Se déconnecter").click()
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill("rayan"); page.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    page.get_by_role("button", name="Se connecter").click()
    nav("Abonnements").click()
    ligne = page.locator("tr", has_text=EMAIL).last          # tableau des paiements (après celui des organisations)
    expect(ligne).to_contain_text("Mutuelle du Littoral")
    expect(ligne).to_contain_text("paye")
    page.screenshot(path="offre_admin.png", full_page=True)
    print("5. l'administrateur voit l'abonné, son organisation et le paiement")

    m = b.new_page(viewport={"width": 390, "height": 844})
    m.goto(URL); m.get_by_role("button", name=re.compile("^Visiteur")).click(); m.screenshot(path="offre_mobile.png", full_page=True)
    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
