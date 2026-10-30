"""Mode conversation : après la relance orale, la réponse est écoutée sans clic."""
import re
import time
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

# Synthèse vocale simulée (300 ms par phrase) et reconnaissance vocale simulée :
# l'utilisateur « dit » window.__reponse quand le micro s'ouvre.
SIMULATION = """
window.__lu = []; window.__reponse = ""; window.__ecoutes = 0;
const s = window.speechSynthesis;
let file = [], t = null;
const suivant = () => { const u = file.shift(); if (!u) { t = null; return; }
  window.__lu.push(u.text); t = setTimeout(() => { u.onend && u.onend(); suivant(); }, 300); };
s.speak = u => { file.push(u); if (!t) suivant(); };
s.cancel = () => { const f = file; file = []; clearTimeout(t); t = null; f.forEach(u => u.onerror && u.onerror()); };
class FausseReco {
  start() { window.__ecoutes++; const dit = window.__reponse;
    if (dit) setTimeout(() => this.onresult && this.onresult({ results: [[{ transcript: dit }]] }), 600); }
  stop() {} abort() {}
}
window.SpeechRecognition = FausseReco; window.webkitSpeechRecognition = FausseReco;
"""


def dire(page, texte):
    page.evaluate("t => window.__reponse = t", texte)


with sync_playwright() as p:
    b = lancer(p, args=[
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
        f"--use-file-for-fake-audio-capture={silence_wav()}%noloop"])
    ctx = b.new_context(viewport={"width": 1280, "height": 900}, permissions=["microphone"])
    page = ctx.new_page()
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script(SIMULATION)
    page.goto(URL)
    page.get_by_role("button", name="Organisation").click(); page.get_by_label("Identifiant ou e-mail").fill("rayan")
    page.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible()
    expect(page.get_by_role("button", name="Désactiver le mode conversation")).to_be_visible()
    champ = page.get_by_role("textbox", name="Question")

    # 1. Relance lue à la fin, puis « oui » → la question proposée est posée toute seule
    dire(page, "oui")
    champ.fill("Transactions frauduleuses par banque"); champ.press("Enter")
    expect(page.get_by_role("button", name="Arrêter l'écoute")).to_be_visible(timeout=15000)
    lu = page.evaluate("window.__lu")
    assert lu[-1] == "Veux-tu voir les alertes critiques encore à traiter ?", lu[-3:]
    expect(page.get_by_text("Résultats (2)")).to_be_visible(timeout=15000)
    expect(page.locator("text=Alertes critiques").first).to_be_visible()
    print("1. relance lue :", lu[-1], "→ « oui » → question posée sans clic")

    # 2. Réponse libre → posée telle quelle
    dire(page, "Crédits en défaut")
    expect(page.get_by_text("Résultats (3)")).to_be_visible(timeout=20000)
    print("2. réponse libre « Crédits en défaut » posée sans clic")

    # 3. « non merci » → l'assistant s'arrête poliment
    dire(page, "non merci")
    expect(page.get_by_role("button", name="Arrêter l'écoute")).to_be_visible(timeout=20000)
    expect(page.get_by_role("button", name="Arrêter l'écoute")).to_be_hidden(timeout=20000)
    page.wait_for_timeout(1500)
    assert page.evaluate("window.__lu")[-2:] == ["D'accord.", "Je reste à ta disposition."], page.evaluate("window.__lu")[-3:]
    assert page.get_by_text("Résultats (4)").count() == 0
    print("3. « non merci » → « D'accord. Je reste à ta disposition. », plus d'écoute")

    # 4. Silence → l'écoute s'arrête seule
    dire(page, "")
    champ.fill("Clients diaspora France"); champ.press("Enter")
    ecoute = page.get_by_role("button", name="Arrêter l'écoute")
    expect(ecoute).to_be_visible(timeout=15000)
    t0 = time.time()
    expect(ecoute).to_be_hidden(timeout=15000)
    print(f"4. silence : écoute arrêtée seule après {time.time() - t0:.1f} s")

    # 5. Arrêt manuel, puis mode conversation désactivé
    champ.fill("Alertes critiques"); champ.press("Enter")
    expect(ecoute).to_be_visible(timeout=15000)
    ecoute.click()
    expect(ecoute).to_be_hidden()
    page.get_by_role("button", name="Désactiver le mode conversation").click()
    n = page.evaluate("window.__ecoutes")
    champ.fill("Volume transactions par ville"); champ.press("Enter")
    page.wait_for_timeout(6000)
    assert page.evaluate("window.__ecoutes") == n and ecoute.count() == 0
    print("5. arrêt manuel + mode conversation désactivable (le micro ne s'ouvre plus)")
    page.screenshot(path="conversation.png")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
