"""Comptes utilisateurs : création par l'administrateur, mot de passe provisoire, verrouillage,
désactivation, révocation des sessions, et isolement de la table des comptes."""
import os
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest

from app import securite

BON_MDP = "Baobab-Douala-2026"


# Ne pas importer conftest : le réimporter recréerait la base de test en cours de session.
def _admin_sql(sql, params=None):
    a = urlsplit(os.environ.get("TEST_PG_ADMIN_URL", "postgresql://postgres@/postgres?host=/tmp&port=5433"))
    url = urlunsplit((a.scheme, a.netloc, "/voicebank_test", a.query, ""))
    with psycopg2.connect(url) as c, c.cursor() as cur:
        cur.execute(sql, params)


def _login(client, nom, mdp):
    return client.post("/auth/login", json={"nom": nom, "mot_de_passe": mdp})


def _h(rep):
    return {"Authorization": f"Bearer {rep.json()['access_token']}"}


def _creer(client, admin, nom, role="analyste"):
    r = client.post("/admin/utilisateurs", headers=admin, json={"nom": nom, "role": role})
    assert r.status_code == 200, r.text
    return r.json()["mot_de_passe_provisoire"]


def _activer(client, admin, nom, mdp=BON_MDP):
    """Crée le compte et change le mot de passe provisoire. Retourne les en-têtes."""
    provisoire = _creer(client, admin, nom)
    r = client.post("/auth/mot-de-passe", headers=_h(_login(client, nom, provisoire)),
                    json={"actuel": provisoire, "nouveau": mdp})
    assert r.status_code == 200, r.text
    return _h(r)


def test_comptes_de_configuration_amorces(client, admin):
    j = client.get("/admin/utilisateurs", headers=admin).json()
    assert j["gestion_comptes"] is True
    comptes = {c["nom"]: c for c in j["data"]}
    assert comptes["rayan"]["role"] == "admin" and comptes["rayan"]["cree_par"] == "configuration"
    assert comptes["analyste1"]["doit_changer_mdp"] is False
    assert all("hash_mdp" not in c for c in j["data"])


def test_reserve_aux_administrateurs(client, analyste):
    assert client.get("/admin/utilisateurs", headers=analyste).status_code == 403
    assert client.post("/admin/utilisateurs", headers=analyste, json={"nom": "pirate"}).status_code == 403


def test_premiere_connexion_impose_le_changement(client, admin):
    provisoire = _creer(client, admin, "jean.mballa")
    assert len(provisoire) == 16
    r = _login(client, "jean.mballa", provisoire)
    assert r.status_code == 200 and r.json()["doit_changer_mot_de_passe"] is True
    h = _h(r)
    # Tant que le mot de passe provisoire n'est pas changé : rien d'autre n'est accessible
    assert client.get("/dashboard", headers=h).status_code == 403
    assert client.get("/auth/moi", headers=h).json()["doit_changer_mot_de_passe"] is True
    # Politique de mot de passe
    for faible in ["court1A!", "toutenminuscules", "Jean.Mballa-2026x", provisoire]:
        r = client.post("/auth/mot-de-passe", headers=h, json={"actuel": provisoire, "nouveau": faible})
        assert r.status_code == 400, faible
    assert client.post("/auth/mot-de-passe", headers=h,
                       json={"actuel": "faux", "nouveau": BON_MDP}).status_code == 400
    r = client.post("/auth/mot-de-passe", headers=h, json={"actuel": provisoire, "nouveau": BON_MDP})
    assert r.status_code == 200 and r.json()["doit_changer_mot_de_passe"] is False
    assert client.get("/dashboard", headers=_h(r)).status_code == 200
    # L'ancien jeton est révoqué, l'ancien mot de passe ne marche plus
    assert client.get("/auth/moi", headers=h).status_code == 401
    assert _login(client, "jean.mballa", provisoire).status_code == 401
    assert _login(client, "jean.mballa", BON_MDP).status_code == 200


def test_identifiants_invalides_ou_existants(client, admin):
    assert client.post("/admin/utilisateurs", headers=admin, json={"nom": "Jean Paul!"}).status_code == 400
    assert client.post("/admin/utilisateurs", headers=admin, json={"nom": "rayan"}).status_code == 400
    assert client.post("/admin/utilisateurs", headers=admin,
                       json={"nom": "x.y.z", "role": "superadmin"}).status_code == 422


def test_verrouillage_apres_5_echecs_puis_reinitialisation(client, admin):
    _activer(client, admin, "marie.ndi")
    for _ in range(5):
        assert _login(client, "marie.ndi", "mauvais").status_code == 401
    # Verrouillé : même le bon mot de passe est refusé, avec le même message
    r = _login(client, "marie.ndi", BON_MDP)
    assert r.status_code == 401 and r.json()["detail"] == _login(client, "inconnu", "x").json()["detail"]
    liste = {c["nom"]: c for c in client.get("/admin/utilisateurs", headers=admin).json()["data"]}
    assert liste["marie.ndi"]["verrouille"] is True
    nouveau = client.post("/admin/utilisateurs/marie.ndi/reinitialiser", headers=admin).json()["mot_de_passe_provisoire"]
    r = _login(client, "marie.ndi", nouveau)
    assert r.status_code == 200 and r.json()["doit_changer_mot_de_passe"] is True


def test_mot_de_passe_provisoire_expire(client, admin):
    provisoire = _creer(client, admin, "paul.eto")
    _admin_sql("UPDATE voicebank.utilisateurs SET mdp_provisoire_expire = LOCALTIMESTAMP - INTERVAL '1 hour' "
               "WHERE nom = 'paul.eto'")
    assert _login(client, "paul.eto", provisoire).status_code == 401
    liste = {c["nom"]: c for c in client.get("/admin/utilisateurs", headers=admin).json()["data"]}
    assert liste["paul.eto"]["provisoire_expire"] is True


def test_desactivation_et_role_revoquent_les_sessions(client, admin):
    h = _activer(client, admin, "alice.fotso")
    assert client.get("/dashboard", headers=h).status_code == 200
    r = client.post("/admin/utilisateurs/alice.fotso/modifier", headers=admin, json={"role": "admin"})
    assert r.json()["changements"] == {"role": "admin"}
    assert client.get("/dashboard", headers=h).status_code == 401          # session révoquée
    h = _h(_login(client, "alice.fotso", BON_MDP))
    assert client.get("/admin/utilisateurs", headers=h).status_code == 200
    client.post("/admin/utilisateurs/alice.fotso/modifier", headers=admin, json={"actif": False})
    assert client.get("/dashboard", headers=h).status_code == 401
    assert _login(client, "alice.fotso", BON_MDP).status_code == 401
    # Réactivation possible (aucun compte n'est supprimé)
    client.post("/admin/utilisateurs/alice.fotso/modifier", headers=admin, json={"actif": True})
    assert _login(client, "alice.fotso", BON_MDP).status_code == 200


def test_protections_administrateur(client, admin):
    for corps in ({"actif": False}, {"role": "analyste"}):
        r = client.post("/admin/utilisateurs/rayan/modifier", headers=admin, json=corps)
        assert r.status_code == 400 and "propre compte" in r.json()["detail"]
    # Dernier administrateur actif : impossible de le retirer, même par un autre compte
    _admin_sql("UPDATE voicebank.utilisateurs SET actif = FALSE WHERE role = 'admin' AND nom <> 'rayan'")
    with pytest.raises(securite.CompteRefuse, match="au moins un administrateur"):
        securite.modifier("rayan", "quelquun", actif=False)
    assert client.post("/admin/utilisateurs/inconnu/reinitialiser", headers=admin).status_code == 400


def test_table_des_comptes_inaccessible_a_l_ia(client, admin):
    r = client.post("/sql/executer", headers=admin, json={"sql": "SELECT * FROM voicebank.utilisateurs"})
    assert r.status_code == 400
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        with psycopg2.connect(os.environ["READONLY_DATABASE_URL"]) as c:
            c.cursor().execute("SELECT hash_mdp FROM voicebank.utilisateurs")


def test_actions_tracees_dans_l_audit(client, admin):
    actions = {e["action"] for e in client.get("/admin/audit?limit=200", headers=admin).json()["evenements"]}
    assert {"compte_cree", "compte_reinitialise", "compte_modifie", "mot_de_passe_change"} <= actions


def test_politique_et_generation():
    for _ in range(50):
        mdp = securite.mdp_provisoire()
        securite.verifier_politique(mdp, "jean")
        assert not set(mdp) & set("0O1lI")


def test_renouvellement_du_jeton(client, admin):
    h = _activer(client, admin, "lea.tchami")
    r = client.post("/auth/renouveler", headers=h)
    assert r.status_code == 200 and r.json()["utilisateur"] == "lea.tchami"
    nouveau = _h(r)
    assert client.get("/dashboard", headers=nouveau).status_code == 200
    # Compte désactivé : plus de renouvellement possible
    client.post("/admin/utilisateurs/lea.tchami/modifier", headers=admin, json={"actif": False})
    assert client.post("/auth/renouveler", headers=nouveau).status_code == 401
    assert client.post("/auth/renouveler").status_code == 401
