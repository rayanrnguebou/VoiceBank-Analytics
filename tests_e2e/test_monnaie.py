"""Monnaie d'affichage : tout suit la monnaie choisie (indicateurs, réponses, résumé, alertes, crédit, tarifs)."""
import re
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)


with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("window.__lu = []; window.speechSynthesis && (window.speechSynthesis.speak = u => window.__lu.push(u.text));"
                         "localStorage.setItem('voicebank_conversation', 'non'); localStorage.removeItem('voicebank_devise');")

    # 1. Accueil : tarif en FCFA, puis en euros
    page.goto(URL)
    expect(page.get_by_text(re.compile(r"500\sFCFA / journée"))).to_be_visible(timeout=20000)
    page.get_by_label("Monnaie").select_option("EUR")
    expect(page.get_by_text(re.compile(r"≈ 0,76 € \(500\sFCFA\) / journée"))).to_be_visible()
    print("1. accueil : 500 FCFA → ≈ 0,76 € (500 FCFA)")

    # 2. Connecté : la monnaie choisie est conservée
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill("rayan"); page.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_label("Monnaie")).to_have_value("EUR")
    expect(page.get_by_text(re.compile(r"\d+,\d M €")).first).to_be_visible()          # crédits en cours
    print("2. indicateur « crédits en cours » en euros :", page.get_by_text(re.compile(r"\d+,\d M €")).first.inner_text())

    # 3. Réponse convertie, en-tête de colonne et résumé parlé en euros
    champ = page.get_by_role("textbox", name="Question")
    champ.fill("Top 10 clients par solde"); champ.press("Enter")
    expect(page.get_by_text("Montants en EUR")).to_be_visible(timeout=20000)
    resume = page.locator("p.text-sm.flex-1").first
    expect(resume).to_contain_text("euros")
    lu = " ".join(page.evaluate("window.__lu"))
    assert "euros" in lu and "FCFA" not in lu, lu
    page.locator("button", has_text="Top 10 clients par solde").first.click() if page.locator("table").count() == 0 else None
    print("3. réponse en euros :", resume.inner_text()[:110])

    # 4. Alertes, crédit, analyse : montants et saisies dans la monnaie choisie
    nav = lambda n: page.get_by_role("navigation").get_by_role("button", name=re.compile(rf"^{n}"))
    nav("Alertes de fraude").click()
    expect(page.get_by_text("€", exact=True).first).to_be_visible()
    nav("Score de crédit").click()
    expect(page.get_by_text("Montant (€)")).to_be_visible()
    montant = page.get_by_label("Montant (€)")
    expect(montant).to_have_value("15244.9")                       # 10 000 000 FCFA
    page.get_by_role("button", name="Évaluer").click()
    expect(page.get_by_text(re.compile("Probabilité de défaut"))).to_be_visible()
    nav("Analyse de transaction").click()
    expect(page.get_by_text("Montant (€)")).to_be_visible()
    print("4. alertes, crédit (10 000 000 FCFA affichés 15 244,9 €) et analyse de transaction en euros")

    # 5. Retour au FCFA
    page.get_by_label("Monnaie").select_option("XAF")
    nav("Score de crédit").click()
    expect(page.get_by_label("Montant (FCFA)")).to_have_value("10000000")
    nav("Assistant vocal").click()
    expect(page.get_by_text(re.compile(r"Mds FCFA|M FCFA")).first).to_be_visible()
    page.screenshot(path="monnaie.png")
    print("5. retour au FCFA : valeurs d'origine retrouvées")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
