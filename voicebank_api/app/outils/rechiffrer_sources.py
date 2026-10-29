"""Rotation de la clé qui chiffre les identifiants des bases connectées.

1. Génère une nouvelle clé longue et secrète ; mets-la dans CLE_SOURCES et l'ancienne dans CLE_SOURCES_ANCIENNES.
2. Redémarre l'API (les deux clés fonctionnent, aucune coupure), puis lance :
       python -m app.outils.rechiffrer_sources
3. Quand le rapport indique 0 erreur, vide CLE_SOURCES_ANCIENNES et redémarre.
"""
from cryptography.fernet import InvalidToken

from .. import db
from ..connecteur.connexion import rechiffrer


def main() -> dict:
    r = db.ecrire("SELECT id_source, config_chiffree FROM voicebank.sources_donnees WHERE config_chiffree IS NOT NULL")
    faits, erreurs = 0, []
    for l in r.lignes:
        try:
            nouveau = rechiffrer(l.config_chiffree)
        except InvalidToken:
            erreurs.append(l.id_source)
            continue
        db.ecrire("UPDATE voicebank.sources_donnees SET config_chiffree = :c WHERE id_source = :i",
                  {"c": nouveau, "i": l.id_source})
        faits += 1
    print(f"Sources rechiffrées avec la clé actuelle : {faits}")
    if erreurs:
        print(f"Illisibles avec les clés fournies (à reconnecter) : {erreurs}")
    return {"rechiffrees": faits, "erreurs": erreurs}


if __name__ == "__main__":
    main()
