"""Génère un hash bcrypt pour VOICEBANK_USERS.

Usage : python -m app.outils.creer_hash
"""
import getpass

import bcrypt

if __name__ == "__main__":
    mdp = getpass.getpass("Mot de passe : ")
    if len(mdp) < 12:
        raise SystemExit("Choisis au moins 12 caractères.")
    if mdp != getpass.getpass("Confirmation : "):
        raise SystemExit("Les mots de passe ne correspondent pas.")
    print(bcrypt.hashpw(mdp.encode()[:72], bcrypt.gensalt(rounds=12)).decode())
