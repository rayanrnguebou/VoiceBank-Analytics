"""Double authentification (activation, connexion, code de secours, désactivation) et protection contre le devinage
de mots de passe (blocage par adresse, mode protégé, lien de déblocage reçu par e-mail)."""
import base64
import email
import hashlib
import hmac
import re
import struct
import subprocess
import sys
import time
from email import policy
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, expect
from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

ANALYSTE, MDP = "nadege.fouda@cooperative.cm", "Mangrove-Kribi-2027!"



def totp(secret, decalage=0):
    s = secret.replace(" ", "")
    cle = base64.b32decode(s + "=" * (-len(s) % 8))
    h = hmac.new(cle, struct.pack(">Q", int(time.time() // 30) + decalage), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6).zfill(6)


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


sql(f"DELETE FROM voicebank.double_authentification WHERE utilisateur = '{ANALYSTE}'; "
    f"DELETE FROM voicebank.echecs_connexion WHERE identifiant = '{ANALYSTE}'; "
    f"DELETE FROM voicebank.appareils_connus WHERE utilisateur = '{ANALYSTE}'; "
    f"UPDATE voicebank.utilisateurs SET verrouille_jusqua = NULL, jeton_deblocage = NULL WHERE nom = '{ANALYSTE}'")


def connexion(page, nom, mdp):
    page.goto(URL)
    page.evaluate("sessionStorage.clear()")
    page.get_by_role("button", name="Organisation").click()
    page.get_by_label("Identifiant ou e-mail").fill(nom); page.get_by_label("Mot de passe").fill(mdp)
    page.get_by_role("button", name="Se connecter").click()


with sync_playwright() as p:
    b = lancer(p)
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()

    def contexte_depuis(ip):
        """Navigateur vu par l'API comme venant d'une autre adresse (en-tête ajouté hors du navigateur : pas de CORS)."""
        c = b.new_context(viewport={"width": 1280, "height": 900})
        c.route(f"{API}/**", lambda r: r.continue_(headers={**r.request.headers, "x-forwarded-for": ip}))
        return c
    erreurs = []; page.on("pageerror", lambda e: erreurs.append(str(e)))
    page.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non');")

    # 1. Activation depuis « Sécurité de mon compte »
    connexion(page, ANALYSTE, MDP)
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    page.get_by_role("button", name=re.compile("^Changer mon mot de passe")).first.click()
    dlg = page.get_by_role("dialog")
    expect(dlg.get_by_text("Double authentification")).to_be_visible()
    dlg.get_by_role("button", name="Activer").click()
    secret = dlg.get_by_label("Clé secrète").inner_text(timeout=15000)
    expect(dlg.get_by_role("img", name=re.compile("QR code"))).to_be_visible()
    page.screenshot(path="2fa_activation.png")
    dlg.get_by_label("Code à 6 chiffres").fill("000000")
    dlg.get_by_role("button", name="Activer").click()
    expect(dlg.get_by_role("alert")).to_contain_text("Code incorrect")
    dlg.get_by_label("Code à 6 chiffres").fill(totp(secret))
    dlg.get_by_role("button", name="Activer").click()
    expect(dlg.get_by_role("list", name="Codes de secours").get_by_role("listitem")).to_have_count(10, timeout=15000)
    codes = dlg.get_by_role("list", name="Codes de secours").get_by_role("listitem").all_inner_texts()
    assert len(codes) == 10, codes
    page.screenshot(path="2fa_codes.png")
    expect(dlg.get_by_role("button", name="Terminer")).to_be_disabled()
    dlg.get_by_label("J'ai mis mes codes de secours en lieu sûr").check()
    dlg.get_by_role("button", name="Terminer").click()
    expect(dlg.get_by_text(re.compile("10 code\\(s\\) de secours restant"))).to_be_visible(timeout=10000)
    print("1. double authentification activée (QR code, code vérifié, 10 codes de secours)")
    page.keyboard.press("Escape")

    # 2. Connexion : mot de passe puis code de l'application
    page.get_by_role("button", name="Se déconnecter").click()
    connexion(page, ANALYSTE, MDP)
    expect(page.get_by_label("Code à 6 chiffres")).to_be_visible(timeout=20000)
    page.screenshot(path="2fa_connexion.png")
    page.get_by_label("Code à 6 chiffres").fill(totp(secret, 1))
    page.get_by_role("button", name="Valider").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    print("2. connexion avec le code de l'application")

    # 3. Téléphone perdu : code de secours (une seule fois)
    page.get_by_role("button", name="Se déconnecter").click()
    connexion(page, ANALYSTE, MDP)
    page.get_by_role("button", name="Téléphone perdu ? Code de secours").click()
    page.get_by_label("Code de secours").fill(codes[0])
    page.get_by_role("button", name="Valider").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    page.get_by_role("button", name="Se déconnecter").click()
    connexion(page, ANALYSTE, MDP)
    page.get_by_role("button", name="Téléphone perdu ? Code de secours").click()
    page.get_by_label("Code de secours").fill(codes[0])
    page.get_by_role("button", name="Valider").click()
    expect(page.get_by_role("alert")).to_contain_text("déjà utilisé")
    print("3. code de secours accepté une fois, refusé la deuxième")

    # 4. Désactivation (rôle analyste : facultative)
    page.get_by_role("button", name="Annuler").click()
    page.get_by_label("Mot de passe").fill(MDP)
    page.get_by_role("button", name="Se connecter").click()
    page.get_by_role("button", name="Téléphone perdu ? Code de secours").click()
    page.get_by_label("Code de secours").fill(codes[2])
    page.get_by_role("button", name="Valider").click()
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    page.get_by_role("button", name=re.compile("^Changer mon mot de passe")).first.click()
    dlg = page.get_by_role("dialog")
    dlg.get_by_role("button", name="Désactiver").click()
    dlg.locator("input[type=password]").first.fill(MDP)
    dlg.get_by_label("Code de l'application").fill(codes[1])
    dlg.get_by_role("button", name="Désactiver").click()
    expect(dlg.get_by_role("button", name="Activer")).to_be_visible(timeout=10000)
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Se déconnecter").click()
    print("4. désactivation (mot de passe + code de secours)")

    # 5. Mots de passe faux : l'adresse de l'essayeur est bloquée, pas le compte
    pirate = contexte_depuis("198.51.100.23")
    pp = pirate.new_page()
    for _ in range(5):
        connexion(pp, ANALYSTE, "Mauvais-mot-de-passe-1")
        expect(pp.get_by_role("alert")).to_have_text("Identifiants incorrects.", timeout=15000)
    connexion(pp, ANALYSTE, MDP)
    expect(pp.get_by_role("alert")).to_contain_text("Trop d'essais depuis cette connexion", timeout=15000)
    pp.screenshot(path="protection_adresse.png")
    connexion(page, ANALYSTE, MDP)
    expect(page.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    page.get_by_role("button", name="Se déconnecter").click()
    print("5. 5 échecs : l'adresse de l'essayeur bloquée ; le titulaire se connecte normalement")

    # 6. Attaque depuis 20 adresses : mode protégé ; lien reçu par e-mail pour autoriser un nouvel appareil
    debut = time.time()
    for n in range(20):
        requests.post(f"{API}/auth/login", headers={"X-Forwarded-For": f"203.0.113.{n + 1}"},
                      json={"nom": ANALYSTE, "mot_de_passe": f"essai-{n}"})
    m = mail(ANALYSTE, "Sécurité de votre compte", debut)
    assert "protégé" in m.get_body(preferencelist=("plain",)).get_content()
    nouveau = contexte_depuis("192.0.2.150")
    np_ = nouveau.new_page()
    connexion(np_, ANALYSTE, MDP)
    expect(np_.get_by_role("alert")).to_contain_text("temporairement protégé", timeout=15000)
    np_.screenshot(path="protection_mode_protege.png")
    m = mail(ANALYSTE, "Sécurité de votre compte", time.time() - 5)
    lien = re.search(r"(http://localhost:3000/\?deblocage=[^\s\"<]+)", m.get_body(preferencelist=("plain",)).get_content()).group(1)
    np_.goto(lien)
    expect(np_.get_by_text("Cet appareil est autorisé")).to_be_visible(timeout=20000)
    np_.get_by_label("Identifiant ou e-mail").fill(ANALYSTE); np_.get_by_label("Mot de passe").fill(MDP)
    np_.get_by_role("button", name="Se connecter").click()
    expect(np_.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=20000)
    np_.get_by_role("button", name="Se déconnecter").click()
    np_.goto(lien)
    expect(np_.get_by_role("alert")).to_contain_text("déjà été utilisé", timeout=20000)
    print("6. mode protégé : nouvel appareil refusé, autorisé par le lien reçu par e-mail (usage unique)")

    print("Erreurs JS :", erreurs or "aucune")
    assert not erreurs
    b.close()

sql(f"DELETE FROM voicebank.echecs_connexion WHERE identifiant = '{ANALYSTE}'; "
    f"UPDATE voicebank.utilisateurs SET verrouille_jusqua = NULL, jeton_deblocage = NULL WHERE nom = '{ANALYSTE}'")
