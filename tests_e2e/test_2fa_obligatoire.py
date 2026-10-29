"""Administrateur sans double authentification (DOUBLE_AUTH_ADMINS=obligatoire) : écran d'activation avant tout."""
import base64, hashlib, hmac, re, struct, subprocess, time
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ADMIN, MDP = "direction@cooperative.cm", "Baobab-Douala-2026"


def totp(secret):
    s = secret.replace(" ", ""); cle = base64.b32decode(s + "=" * (-len(s) % 8))
    h = hmac.new(cle, struct.pack(">Q", int(time.time() // 30)), hashlib.sha1).digest(); o = h[-1] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6).zfill(6)


subprocess.run(["psql", BASE, "-X", "-qc",
                f"DELETE FROM voicebank.double_authentification WHERE utilisateur = '{ADMIN}'"], check=True)
with sync_playwright() as p:
    b = lancer(p)
    page = b.new_page(viewport={"width": 1280, "height": 900})
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_demarrage_direction@cooperative.cm','non')")
    page.goto(URL); page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill(ADMIN); page.get_by_label("Mot de passe").fill(MDP)
    page.get_by_role("button", name="Se connecter").click()
    expect(page.get_by_role("heading", name="Protège ton compte administrateur")).to_be_visible(timeout=20000)
    assert page.get_by_role("navigation").count() == 0
    secret = page.get_by_label("Clé secrète").inner_text(timeout=15000)
    page.screenshot(path="2fa_obligatoire.png")
    page.get_by_label("Code à 6 chiffres").fill(totp(secret))
    page.get_by_role("button", name="Activer").click()
    page.get_by_label("J'ai mis mes codes de secours en lieu sûr").check(timeout=15000)
    page.get_by_role("button", name="Terminer").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    page.get_by_role("navigation").get_by_role("button", name=re.compile("^Membres")).click()
    expect(page.get_by_text("2FA").first).to_be_visible(timeout=20000)
    print("1. administratrice : activation imposée avant l'accès, puis accès normal (badge 2FA dans Membres)")
    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()
subprocess.run(["psql", BASE, "-X", "-qc",
                f"DELETE FROM voicebank.double_authentification WHERE utilisateur = '{ADMIN}'"], check=True)
