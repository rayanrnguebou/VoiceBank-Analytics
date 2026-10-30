"""Double authentification par notification : l'ordinateur affiche un nombre, le téléphone le choisit ; refus
(« Ce n'était pas moi ») ; repli sur le code à 6 chiffres. La notification elle-même ne peut pas transiter par les
services des navigateurs ici (hors ligne) : le téléphone ouvre directement le lien qu'elle contient."""
import base64
import hashlib
import hmac
import re
import struct
import subprocess
import time

import requests
from playwright.sync_api import sync_playwright, expect

from commun import *  # noqa: F401,F403  (URL, API, BASE, MAILS, sql, lancer…)

COMPTE, MDP = "nadege.fouda@cooperative.cm", "Mangrove-Kribi-2027!"
ABONNEMENT = {"endpoint": "https://fcm.googleapis.com/fcm/send/e2e-voicebank",
              "keys": {"p256dh": "B" + "x" * 86, "auth": "a" * 22}}


def nettoyer():
    sql(f"DELETE FROM voicebank.appareils_approbation WHERE utilisateur = '{COMPTE}'; "
        f"DELETE FROM voicebank.demandes_approbation WHERE utilisateur = '{COMPTE}'; "
        f"DELETE FROM voicebank.double_authentification WHERE utilisateur = '{COMPTE}'; "
        f"DELETE FROM voicebank.echecs_connexion WHERE identifiant IN ('{COMPTE}', '2fa:{COMPTE}')")


def totp(secret, decalage=0):
    s = secret.replace(" ", ""); cle = base64.b32decode(s + "=" * (-len(s) % 8))
    h = hmac.new(cle, struct.pack(">Q", int(time.time() // 30) + decalage), hashlib.sha1).digest(); o = h[-1] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** 6).zfill(6)


def derniere_demande():
    return subprocess.run(["psql", BASE, "-X", "-tAc", "SELECT id_demande FROM voicebank.demandes_approbation WHERE "
                           f"utilisateur = '{COMPTE}' ORDER BY date_creation DESC LIMIT 1"],
                          check=True, capture_output=True, text=True).stdout.strip()


nettoyer()
# Double authentification activée et téléphone enregistré (par l'API, comme le ferait l'écran de réglages)
h = {"Authorization": "Bearer " + requests.post(f"{API}/auth/login", json={"nom": COMPTE, "mot_de_passe": MDP}).json()["access_token"]}
prep = requests.post(f"{API}/auth/2fa/preparer", headers=h).json()
act = requests.post(f"{API}/auth/2fa/activer", headers=h, json={"code": totp(prep["secret"])}).json()
h = {"Authorization": f"Bearer {act['access_token']}"}
tel = requests.post(f"{API}/auth/approbation/telephones", headers=h,
                    json={"code": act["codes_secours"][0], "nom": "Chrome · Android", "abonnement": ABONNEMENT})
assert tel.status_code == 200, tel.text
SECRET = tel.json()["secret"]

try:
    with sync_playwright() as p:
        b = lancer(p)
        ordi = b.new_page(viewport={"width": 1280, "height": 900})
        tele_ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
        tele_ctx.add_init_script(f"localStorage.setItem('voicebank_approbation_secret', '{SECRET}')")
        tele = tele_ctx.new_page()
        erreurs = []
        for pg in (ordi, tele):
            pg.on("pageerror", lambda e: erreurs.append(str(e)))
        ordi.add_init_script("localStorage.setItem('voicebank_voix','non'); localStorage.setItem('voicebank_conversation','non')")

        def mot_de_passe():
            ordi.goto(URL); ordi.evaluate("sessionStorage.clear()"); ordi.reload()
            ordi.get_by_role("button", name="Organisation").click()
            ordi.get_by_label("Identifiant ou e-mail").fill(COMPTE); ordi.get_by_label("Mot de passe").fill(MDP)
            ordi.get_by_role("button", name="Se connecter").click()
            expect(ordi.get_by_text("Approuve la connexion sur ton téléphone")).to_be_visible(timeout=20000)
            nombre = ordi.get_by_label(re.compile(r"^Nombre à choisir")).inner_text().strip()
            return nombre, derniere_demande()

        # 1. Bon nombre : l'ordinateur se connecte tout seul
        nombre, demande = mot_de_passe()
        ordi.screenshot(path="approbation_ordinateur.png")
        tele.goto(f"{URL}/?approbation={demande}")
        expect(tele.get_by_text("Connexion demandée")).to_be_visible(timeout=15000)
        expect(tele.get_by_text(COMPTE)).to_be_visible()
        tele.screenshot(path="approbation_telephone.png", full_page=True)
        tele.get_by_role("button", name=nombre, exact=True).click()
        expect(tele.get_by_role("status")).to_contain_text("Connexion approuvée", timeout=10000)
        expect(ordi.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=15000)
        print("1. nombre choisi sur le téléphone : l'ordinateur est connecté sans taper de code")

        # 2. « Ce n'était pas moi » : refusé, expliqué sur l'ordinateur
        nombre, demande = mot_de_passe()
        tele.goto(f"{URL}/?approbation={demande}")
        tele.get_by_role("button", name="Ce n'était pas moi").click()
        expect(tele.get_by_role("alert")).to_contain_text("Connexion bloquée", timeout=10000)
        expect(ordi.get_by_role("alert")).to_contain_text("Connexion refusée depuis le téléphone", timeout=15000)
        print("2. « Ce n'était pas moi » : connexion bloquée")

        # 3. Repli sur le code à 6 chiffres
        ordi.get_by_role("button", name="Utiliser plutôt le code à 6 chiffres").click()
        ordi.get_by_label("Code à 6 chiffres").fill(totp(prep["secret"], 1))
        ordi.get_by_role("button", name="Valider").click()
        expect(ordi.get_by_role("button", name="Se déconnecter")).to_be_visible(timeout=15000)
        print("3. le code à 6 chiffres reste possible")

        # 4. Réglages : le téléphone apparaît dans « Approuver depuis mon téléphone »
        ordi.get_by_role("button", name="Changer mon mot de passe et la double authentification").click()
        expect(ordi.get_by_text("Approuver depuis mon téléphone")).to_be_visible(timeout=10000)
        expect(ordi.get_by_text("Chrome · Android")).to_be_visible()
        ordi.screenshot(path="approbation_reglages.png", full_page=True)
        print("4. le téléphone enregistré est listé dans les réglages")

        print("Erreurs JS :", erreurs or "aucune")
        assert not erreurs
        b.close()
finally:
    nettoyer()
