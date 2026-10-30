"""Parcours navigateur des fonctions v3.1 (base de démo, comptes à privilèges minimaux)."""
import re
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

CAPTURE_VOIX = """
window.__lu = [];
const s = window.speechSynthesis;
if (s) { s.speak = u => window.__lu.push(u.text); s.cancel = () => {}; }
"""

def connexion(page, nom, mdp):
    page.goto(URL)
    page.get_by_role("button", name="Organisation").click(); page.get_by_label("Identifiant ou e-mail").fill(nom)
    page.get_by_label("Mot de passe").fill(mdp)
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible()

def demander(page, texte):
    champ = page.get_by_role("textbox", name="Question")
    champ.fill(texte); champ.press("Enter")

NAV = {"Alertes": "Alertes de fraude", "Score crédit": "Score de crédit", "Analyse fraude": "Analyse de transaction"}

def onglet(page, nom):
    nom = NAV.get(nom, nom)
    page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{re.escape(nom)}( \d+\+?)?$")).click()

with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1200, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.on("dialog", lambda d: d.accept())
    page.add_init_script(CAPTURE_VOIX)
    connexion(page, "rayan", "Test-Admin-2026!")

    # 1. Résumé + lecture vocale
    demander(page, "Transactions frauduleuses par banque")
    resume = page.locator("p.text-sm.flex-1").first
    expect(resume).to_contain_text("En tête")
    page.wait_for_timeout(300)
    lu = page.evaluate("window.__lu")
    texte_lu, texte_resume = " ".join(lu), resume.inner_text()
    assert texte_lu.startswith(texte_resume), lu
    commentaire = texte_lu[len(texte_resume):].strip()
    assert len(commentaire) > 80 and commentaire[:40] not in page.inner_text("body"), commentaire
    print("1. résumé affiché et lu, puis commentaire lu (non affiché) :", commentaire[:90], "…")
    n = len(lu)
    page.get_by_role("button", name="Désactiver la réponse vocale").click()
    demander(page, "Alertes critiques"); page.wait_for_timeout(800)
    assert len(page.evaluate("window.__lu")) == n
    page.get_by_role("button", name="Activer la réponse vocale").click()
    print("   bouton voix on/off OK")

    # 2. Question de suite
    demander(page, "Transactions frauduleuses")
    expect(page.get_by_text("Résultats (3)")).to_be_visible()
    demander(page, "et à Douala ?")
    expect(page.get_by_text("suite de « Transactions frauduleuses »")).to_be_visible()
    print("2. question de suite « et à Douala ? » OK :", page.locator("p.text-sm.flex-1").first.inner_text())

    # 4. Signaler puis corriger (Apprentissage)
    page.get_by_role("button", name="Réponse incorrecte ?").first.click()
    page.get_by_placeholder(re.compile("Qu'est-ce qui est faux")).fill("Je voulais seulement les montants > 5 M")
    page.get_by_role("button", name="Envoyer le signalement").click()
    expect(page.get_by_text("Merci, un administrateur va vérifier")).to_be_visible()
    onglet(page, "Apprentissage")
    expect(page.get_by_text("Je voulais seulement les montants > 5 M", exact=False)).to_be_visible()
    page.get_by_role("button", name="Corriger", exact=True).first.click()
    editeur = page.locator("textarea").first
    editeur.fill("SELECT id_transaction, montant_fcfa FROM voicebank.transactions WHERE est_frauduleuse = 'Oui' AND ville = 'Douala' AND montant_fcfa > 5000000")
    page.get_by_role("button", name="Tester la requête").click()
    expect(page.get_by_text(re.compile(r"\d+ ligne\(s\) — aperçu"))).to_be_visible()
    page.get_by_role("button", name="Enregistrer la correction").click()
    expect(page.get_by_text("Correction enregistrée")).to_be_visible()
    page.wait_for_timeout(1500)
    expect(page.get_by_text("Aucun signalement en attente.")).to_be_visible()
    print("4. signalement → correction testée et enregistrée OK")
    page.screenshot(path="v31_apprentissage.png", full_page=True)

    # 6. Alertes
    onglet(page, "Alertes")
    page.get_by_role("button", name="Traiter", exact=True).first.click()
    page.get_by_placeholder(re.compile("Commentaire")).fill("Client joint par téléphone, achat confirmé")
    page.get_by_role("button", name="Faux positif").click()
    page.wait_for_timeout(800)
    page.get_by_role("button", name="Traitées", exact=True).click()
    expect(page.get_by_text("Client joint par téléphone", exact=False).first).to_be_visible()
    expect(page.get_by_text(re.compile("par rayan")).first).to_be_visible()
    print("6. alerte traitée (Faux positif + commentaire, par rayan) OK")

    # 5. Score de crédit
    onglet(page, "Score crédit")
    page.get_by_role("button", name="Évaluer", exact=True).click()
    expect(page.get_by_text("Ce qui explique ce résultat").first).to_be_visible()
    page.locator("button", has_text="CRD-").first.click()
    expect(page.get_by_text("Ce qui explique ce résultat")).to_have_count(2)
    print("5. score de crédit + explication + crédits à risque OK")
    page.screenshot(path="v31_credit.png", full_page=True)

    # 3. Fiabilité
    onglet(page, "Fiabilité")
    page.get_by_role("button", name="Lancer l'évaluation").click()
    expect(page.locator("span.text-4xl")).to_be_visible(timeout=60000)
    print("3. évaluation :", page.locator("span.text-4xl").inner_text(), "(sans Gemini)")

    # 7. Audit
    onglet(page, "Audit")
    expect(page.locator("td", has_text="Alerte traitée").first).to_be_visible()
    expect(page.locator("td", has_text="Correction enregistrée").first).to_be_visible()
    expect(page.locator("td", has_text="Connexion").first).to_be_visible()
    print("7. journal d'audit OK")
    page.screenshot(path="v31_audit.png", full_page=True)

    page.get_by_role("button", name="Se déconnecter").click()

    # 7. Analyste : noms masqués, pas d'onglets admin
    connexion(page, "analyste1", "Test-Analyste-2026!")
    demander(page, "Crédits en défaut")
    try:
        expect(page.get_by_text("Résultats (1)")).to_be_visible(timeout=15000)
    except AssertionError:
        page.screenshot(path="echec_analyste.png", full_page=True)
        print("TEXTE:", page.locator("main").inner_text()[:600])
        raise
    recu = page.evaluate("JSON.parse(sessionStorage.getItem('voicebank_historique_analyste1'))[0].data.slice(0, 3)")
    assert recu and all(l["nom"].endswith("***") and l["prenom"].endswith("***") for l in recu), recu
    print("   données reçues par le navigateur :", [(l["id_client"], l["nom"], l["prenom"]) for l in recu])
    assert page.get_by_role("button", name="Apprentissage").count() == 0
    assert page.get_by_role("button", name="Corriger la requête").count() == 0
    print("7. analyste : noms masqués, pas d'outils admin OK")
    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
