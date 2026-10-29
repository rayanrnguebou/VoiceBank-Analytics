"""Dictée en direct : le texte apparaît dans le champ pendant qu'on parle, puis Whisper le finalise."""
import re, json
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

# Faux moteur de reconnaissance du navigateur : émet des résultats partiels comme Chrome.
FAUX_SR = """
class FauxSR {
  constructor(){ this.lang=''; this.interimResults=false; this.continuous=false; }
  start(){
    const etapes = ["crédits", "crédits en", "crédits en défaut", "crédits en défaut à Douala"];
    etapes.forEach((t, i) => setTimeout(() => {
      if (this.arrete) return;
      this.onresult && this.onresult({ results: [[{ transcript: t }]] });
      window.__etapes = (window.__etapes || []).concat([document.querySelector('input[aria-label=Question]').value]);
    }, 300 * (i + 1)));
  }
  stop(){ this.arrete = true; }
  abort(){ this.arrete = true; }
}
window.webkitSpeechRecognition = FauxSR; window.SpeechRecognition = FauxSR;
"""

def connexion(page):
    page.goto("http://localhost:3000")
    page.get_by_role("button", name="Organisation").click(); page.get_by_label("Identifiant ou e-mail").fill("rayan")
    page.get_by_label("Mot de passe").fill("Test-Admin-2026!")
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_text("Administrateur", exact=True)).to_be_visible()

with sync_playwright() as p:
    b = lancer(p, args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
    for scenario in ["whisper_ok", "whisper_en_panne", "sans_reco_navigateur"]:
        ctx = b.new_context(permissions=["microphone"])
        page = ctx.new_page()
        erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
        if scenario != "sans_reco_navigateur":
            page.add_init_script(FAUX_SR)
        else:
            page.add_init_script("delete window.webkitSpeechRecognition; delete window.SpeechRecognition;")

        def transcrire(route):
            if scenario == "whisper_en_panne":
                route.fulfill(status=502, content_type="application/json",
                              headers={"access-control-allow-origin": "http://localhost:3000"},
                              body=json.dumps({"detail": "Le service de transcription a échoué"}))
            else:
                route.fulfill(status=200, content_type="application/json",
                              headers={"access-control-allow-origin": "http://localhost:3000"},
                              body=json.dumps({"status": "ok", "texte": "Crédits en défaut à Douala.", "moteur": "groq"}))
        page.route("**/vocal/transcrire", transcrire)
        connexion(page)
        champ = page.get_by_role("textbox", name="Question")

        page.get_by_role("button", name="Poser une question à voix haute").click()
        if scenario != "sans_reco_navigateur":
            expect(champ).to_have_value("crédits en défaut à Douala", timeout=5000)   # texte en direct
            etapes = page.evaluate("window.__etapes")
            print(f"[{scenario}] texte en direct dans le champ :", etapes)
        page.get_by_role("button", name="Arrêter l'enregistrement").click()

        if scenario == "whisper_ok":
            expect(champ).to_have_value("Crédits en défaut à Douala.")
            expect(champ).to_be_focused()
            print(f"[{scenario}] texte final Whisper :", champ.input_value(), "| champ actif, rien envoyé tout seul")
            assert page.get_by_text("Résultats (").count() == 0
            page.keyboard.press("Enter")
            expect(page.get_by_text("Résultats (1)")).to_be_visible()
            print(f"[{scenario}] Entrée -> question envoyée, résultat affiché")
        elif scenario == "whisper_en_panne":
            expect(champ).to_have_value("crédits en défaut à Douala")
            expect(page.get_by_role("alert")).to_contain_text("texte du navigateur conservé")
            print(f"[{scenario}] texte du navigateur conservé + avertissement")
        else:
            expect(champ).to_have_value("Crédits en défaut à Douala.")
            print(f"[{scenario}] (Firefox) texte Whisper écrit dans le champ à la fin :", champ.input_value())
        page.wait_for_timeout(300)
        assert not erreurs, erreurs
        ctx.close()
    b.close()
print("OK")
