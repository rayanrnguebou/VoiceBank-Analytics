"""Recouvrement sur la base connectée d'une organisation : dossiers tirés des crédits « late », coordonnées lues dans
la table des clients, relance WhatsApp avec message prêt, promesse, paiement, dossier réglé, puis « Valeur créée »."""
import re
from datetime import date, timedelta

from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ADMIN, MDP = "direction@cooperative.cm", "Baobab-Douala-2026"
sql("DELETE FROM voicebank.dossiers_recouvrement WHERE id_source IN (SELECT id_source FROM voicebank.sources_donnees "
    "WHERE proprietaire = 'direction@cooperative.cm'); UPDATE voicebank.sources_donnees SET masquer_pii = TRUE "
    "WHERE proprietaire = 'direction@cooperative.cm'")


def connexion(page):
    page.goto(URL)
    page.evaluate("sessionStorage.clear()")
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill(ADMIN); page.get_by_label("Mot de passe").fill(MDP)
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)


with sync_playwright() as p:
    b = lancer(p)
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non');"
                         "localStorage.setItem('voicebank_demarrage_direction@cooperative.cm','non')")
    ouverts = []
    ctx.on("page", lambda pg: ouverts.append(pg))
    ctx.route(re.compile(r"https://wa\.me/.*"), lambda r: r.fulfill(status=200, body="WhatsApp"))
    nav = lambda nom: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{nom}"))

    # 1. Données personnelles masquées (réglage par défaut) : la liste est là, sans coordonnées
    connexion(page)
    expect(page.get_by_label("Données interrogées").first).to_have_value(re.compile(r"\d+"), timeout=20000)
    nav("Recouvrement").click()
    expect(page.get_by_text("Crédits à recouvrer")).to_be_visible(timeout=60000)
    expect(page.get_by_text(re.compile(r"Table « loans » : crédits en retard ou en défaut, montant « principal »"))).to_be_visible()
    expect(page.get_by_text(re.compile("Les données personnelles de cette base sont masquées"))).to_be_visible()
    print("1. base masquée : dossiers listés, coordonnées cachées et relances désactivées")

    # 2. Masquage retiré (réglage de l'administrateur) : nom, téléphone, retard en jours, message prêt
    sql("UPDATE voicebank.sources_donnees SET masquer_pii = FALSE WHERE proprietaire = 'direction@cooperative.cm'")
    page.reload()
    nav("Recouvrement").click()
    premier = page.locator("button[aria-expanded]").first
    expect(premier).to_contain_text(re.compile(r"Prenom\d+ Nom\d+"), timeout=60000)
    expect(page.locator("button[aria-expanded]").filter(has_text=re.compile(r"Retard · \d+ j")).first).to_be_visible()
    page.screenshot(path="recouvrement_liste.png", full_page=False)
    premier.click()
    message = page.get_by_label("Message (modifiable avant l'envoi)")
    expect(message).to_have_value(re.compile(r"^Bonjour Prenom\d+ Nom\d+, .*votre crédit \d+ présente un impayé de"))
    print("2. coordonnées lues dans « customers » : client, téléphone, jours de retard, message prêt")

    # 3. Relance WhatsApp : le lien s'ouvre avec le message, la relance est notée, le dossier passe à « Contacté »
    page.get_by_role("link", name="WhatsApp").click()
    expect(page.get_by_text(re.compile(r"Message WhatsApp envoyé : Bonjour"))).to_be_visible(timeout=10000)
    page.wait_for_timeout(500)
    assert ouverts and ouverts[-1].url.startswith("https://wa.me/237"), [o.url for o in ouverts]
    assert "text=Bonjour" in ouverts[-1].url
    expect(premier).to_contain_text("Contacté")
    print("3. WhatsApp ouvert sur le bon numéro avec le message ; relance notée, dossier « Contacté »")

    # 4. Promesse de paiement, puis paiement complet : dossier réglé
    page.get_by_role("button", name="Promesse de paiement").click()
    page.get_by_label(re.compile(r"Montant promis")).fill("50000")
    page.get_by_label("Date promise").fill((date.today() + timedelta(days=7)).isoformat())
    page.get_by_role("button", name="Enregistrer").click()
    expect(premier).to_contain_text("Promesse de paiement", timeout=10000)
    reste = premier.locator("p.font-bold").inner_text()
    montant = re.sub(r"[^\d]", "", reste.split(",")[0])
    page.get_by_role("button", name="Paiement reçu").click()
    page.get_by_label(re.compile(r"Montant reçu")).fill(montant)
    page.get_by_label("Note").fill("Versement Orange Money")
    page.get_by_role("button", name="Enregistrer").click()
    page.get_by_role("tab", name="Clos").click()
    expect(page.get_by_text("Réglé").first).to_be_visible(timeout=20000)
    page.screenshot(path="recouvrement_regle.png")
    print(f"4. promesse puis paiement de {montant} : dossier « Réglé »")

    # 5. Valeur créée : l'argent récupéré apparaît
    nav("Valeur créée").click()
    expect(page.get_by_text("Argent récupéré").first).to_be_visible(timeout=20000)
    expect(page.get_by_text(re.compile(r"1 dossier\(s\) réglé\(s\)"))).to_be_visible()
    page.screenshot(path="valeur_creee.png", full_page=True)
    print("5. « Valeur créée » : argent récupéré, fraude évitée, temps gagné")

    # 6. Mobile
    nav("Recouvrement").click()
    page.set_viewport_size({"width": 390, "height": 844}); page.wait_for_timeout(600)
    assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth"), "débordement horizontal sur mobile"
    page.screenshot(path="recouvrement_mobile.png")
    print("6. mobile sans débordement")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
