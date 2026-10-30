"""Mémoire des calculs lourds et attente d'un moment calme pour les tâches automatiques (lenteur du serveur)."""
import threading
import time

from app import config, taches
from app.memoire import Memoire


def test_resultat_ancien_rendu_tout_de_suite_puis_actualise_en_fond():
    m = Memoire(frais=0.5, garde=60)
    appels = []

    def lent():
        appels.append(1)
        time.sleep(0.3)
        return len(appels)

    assert m.obtenir("k", lent) == 1                     # premier calcul : on attend
    assert m.obtenir("k", lent) == 1 and len(appels) == 1  # frais : pas de recalcul
    time.sleep(0.6)
    debut = time.time()
    assert m.obtenir("k", lent) == 1                     # ancien : rendu sans attendre…
    assert time.time() - debut < 0.1
    time.sleep(0.4)
    assert m.obtenir("k", lent) == 2                     # … et actualisé en arrière-plan
    assert len(appels) == 2


def test_un_seul_calcul_pour_des_visiteurs_simultanes():
    m = Memoire()
    appels = []

    def lent():
        appels.append(1)
        time.sleep(0.3)
        return "ok"

    res = []
    fils = [threading.Thread(target=lambda: res.append(m.obtenir("k", lent))) for _ in range(5)]
    [f.start() for f in fils]
    [f.join() for f in fils]
    assert res == ["ok"] * 5 and len(appels) == 1


def test_echec_en_arriere_plan_garde_l_ancien_resultat_et_echec_direct_remonte():
    m = Memoire(frais=0, garde=60)
    assert m.obtenir("k", lambda: "ancien") == "ancien"

    def panne():
        raise RuntimeError("base injoignable")

    assert m.obtenir("k", panne) == "ancien"
    time.sleep(0.1)
    assert m.obtenir("k", lambda: "nouveau") in ("ancien", "nouveau")
    try:
        Memoire().obtenir("autre", panne)
        raise AssertionError("l'erreur devait remonter")
    except RuntimeError:
        pass


def test_nouvelle_analyse_remplace_les_anciens_resultats():
    m = Memoire()
    m.obtenir((1, "u", "2026-01-01"), lambda: "a")
    m.obtenir((2, "u", "2026-01-01"), lambda: "b")
    m.obtenir((1, "u", "2026-02-01"), lambda: "c", remplace=lambda k: k[0] == 1 and k[2] != "2026-02-01")
    assert (1, "u", "2026-01-01") not in m._valeurs and (2, "u", "2026-01-01") in m._valeurs


def test_taches_attendent_un_moment_calme(monkeypatch):
    monkeypatch.setattr(config, "TACHES_CALME_S", 0.4)
    taches.noter_activite()
    assert 0.3 < taches.attendre_calme(5) < 1           # attend la fin de l'activité
    taches.noter_activite()
    assert taches.attendre_calme(0.1) < 0.3              # attente bornée
    monkeypatch.setattr(config, "TACHES_CALME_S", 0)
    taches.noter_activite()
    assert taches.attendre_calme(5) < 0.05


def test_requetes_utilisateur_notees_mais_pas_les_sondes(client):
    taches._activite["t"] = 0
    client.get("/health/vivant")
    assert taches._activite["t"] == 0
    client.get("/maintenance")
    assert taches._activite["t"] > 0
