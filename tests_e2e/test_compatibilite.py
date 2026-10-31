"""Compatibilité : la page d'accueil, la connexion et le tableau de bord s'ouvrent sans erreur ni débordement sur
téléphones (Android, iPhone), tablettes et ordinateurs, et sur un navigateur ancien (fonctions récentes retirées)."""
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

# Navigateur « ancien » simulé : ce que n'ont pas iOS 14-15, les vieux Android ou certains navigateurs intégrés
ANCIEN = """
delete Object.hasOwn; delete Array.prototype.at; delete window.structuredClone;
delete window.MediaRecorder; delete window.speechSynthesis; delete window.SpeechSynthesisUtterance;
delete window.SpeechRecognition; delete window.webkitSpeechRecognition;
try { Object.defineProperty(navigator, 'serviceWorker', { value: undefined }); } catch (e) {}
try { Object.defineProperty(navigator, 'clipboard', { value: undefined }); } catch (e) {}
"""
# Stockage du navigateur bloqué (navigation privée stricte, cookies tiers bloqués…)
SANS_STOCKAGE = """
for (const nom of ['localStorage', 'sessionStorage']) {
  try { Object.defineProperty(window, nom, { get() { throw new DOMException('bloqué', 'SecurityError'); } }); } catch (e) {}
}
"""


def appareils(p):
    d = p.devices
    ordi = {"viewport": {"width": 1366, "height": 768}}
    return [
        ("Android petit écran (Galaxy S9+)", d["Galaxy S9+"], ""),
        ("Android récent (Pixel 7)", d["Pixel 7"], ""),
        ("Android d'entrée de gamme 320 px", {**d["Galaxy S5"], "viewport": {"width": 320, "height": 568}}, ""),
        ("iPhone SE", d["iPhone SE"], ""),
        ("iPhone 15 Pro Max", d["iPhone 15 Pro Max"], ""),
        ("iPad Mini", d["iPad Mini"], ""),
        ("Tablette Android (Galaxy Tab S4)", d["Galaxy Tab S4"], ""),
        ("Téléphone en paysage (Pixel 7)", d["Pixel 7 landscape"], ""),
        ("Ordinateur portable 1366×768", ordi, ""),
        ("Grand écran 1920×1080", {"viewport": {"width": 1920, "height": 1080}}, ""),
        ("Écran 4K 3840×2160", {"viewport": {"width": 3840, "height": 2160}}, ""),
        ("Navigateur ancien (iOS 14, vieil Android)", d["iPhone 12"], ANCIEN),
        ("Stockage du navigateur bloqué", ordi, SANS_STOCKAGE),
    ]


def deborde(page) -> int:
    return page.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - window.innerWidth")


with sync_playwright() as p:
    b = lancer(p)
    bilan = []
    for nom, reglages, script in appareils(p):
        reglages = {k: v for k, v in reglages.items() if k != "default_browser_type"}
        ctx = b.new_context(**reglages, locale="fr-FR")
        if script:
            ctx.add_init_script(script)
        page = ctx.new_page()
        erreurs = []
        page.on("pageerror", lambda e: erreurs.append(str(e)))
        page.goto(URL)
        expect(page.get_by_role("button", name="Organisation")).to_be_visible(timeout=30000)
        assert deborde(page) <= 1, f"{nom} : la page d'accueil déborde de {deborde(page)} px"
        page.get_by_role("button", name="Organisation").click()
        page.get_by_label("Identifiant ou e-mail").fill("analyste1")
        page.get_by_label("Mot de passe").fill("Test-Analyste-2026!")
        page.get_by_role("button", name="Se connecter").click()
        expect(page.get_by_role("button", name="Se déconnecter").first).to_be_attached(timeout=30000)
        page.wait_for_timeout(1500)
        assert deborde(page) <= 1, f"{nom} : le tableau de bord déborde de {deborde(page)} px"
        page.screenshot(path=f"compat_{nom.split(' (')[0].replace(' ', '_').replace('×', 'x').lower()}.png")
        assert not erreurs, f"{nom} : erreurs JavaScript {erreurs}"
        bilan.append(nom)
        ctx.close()
        print(f"{len(bilan)}. {nom} : accueil, connexion et tableau de bord sans erreur ni débordement")
    print("Erreurs JS : aucune")
