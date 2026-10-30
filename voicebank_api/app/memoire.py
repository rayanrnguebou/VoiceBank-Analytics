"""Mémoire des calculs lourds (analyses de risques, tableaux de bord, fiches des modèles).

Sur un petit serveur (offre gratuite de Render : une fraction de processeur), une analyse qui prend 2 s sur un
ordinateur peut en prendre 30 : l'utilisateur ne doit pas l'attendre à chaque visite.

* résultat **frais** (moins de `frais` secondes) : rendu tel quel ;
* résultat **ancien** (moins de `garde` secondes) : rendu tout de suite, et recalculé en arrière-plan pour la visite
  suivante ;
* un seul calcul à la fois par clé : les visiteurs simultanés attendent le même calcul au lieu d'en lancer chacun un.
"""
import logging
import threading
import time
from typing import Any, Callable

log = logging.getLogger("voicebank")


class Memoire:
    def __init__(self, frais: float = 600, garde: float = 24 * 3600, taille_max: int = 200):
        self.frais, self.garde, self.taille_max = frais, garde, taille_max
        self._valeurs: dict = {}          # clé → (horodatage, résultat)
        self._en_cours: dict = {}         # clé → threading.Event
        self._verrou = threading.Lock()

    def obtenir(self, cle, calcul: Callable[[], Any], remplace: Callable[[Any], bool] | None = None):
        """`remplace(autre_cle)` : anciennes clés à oublier quand celle-ci est calculée (ex. analyse plus récente)."""
        maintenant = time.time()
        with self._verrou:
            trouve = self._valeurs.get(cle)
            if trouve and maintenant - trouve[0] < self.frais:
                return trouve[1]
            en_cours = self._en_cours.get(cle)
            if trouve and maintenant - trouve[0] < self.garde:
                if not en_cours:
                    self._en_cours[cle] = threading.Event()
                    threading.Thread(target=self._calculer, args=(cle, calcul, remplace, True), daemon=True,
                                     name="memoire-actualisation").start()
                return trouve[1]
            if not en_cours:
                self._en_cours[cle] = threading.Event()
        if not en_cours:
            return self._calculer(cle, calcul, remplace, False)
        en_cours.wait(timeout=300)                  # un autre visiteur calcule déjà : on attend son résultat
        with self._verrou:
            trouve = self._valeurs.get(cle)
        return trouve[1] if trouve else self.obtenir(cle, calcul, remplace)

    def _calculer(self, cle, calcul, remplace, arriere_plan: bool):
        try:
            res = calcul()
        except Exception:
            with self._verrou:
                self._en_cours.pop(cle).set()
            if arriere_plan:                        # on garde l'ancien résultat ; l'erreur réapparaîtra au besoin
                log.exception("Actualisation en arrière-plan impossible (%s)", cle)
                return None
            raise
        with self._verrou:
            if remplace:
                for k in [k for k in self._valeurs if k != cle and remplace(k)]:
                    self._valeurs.pop(k, None)
            self._valeurs[cle] = (time.time(), res)
            if len(self._valeurs) > self.taille_max:   # les plus anciens d'abord
                for k, _ in sorted(self._valeurs.items(), key=lambda kv: kv[1][0])[:len(self._valeurs) - self.taille_max]:
                    self._valeurs.pop(k, None)
            self._en_cours.pop(cle).set()
        return res

    def oublier(self, filtre: Callable[[Any], bool] | None = None):
        with self._verrou:
            for k in [k for k in self._valeurs if filtre is None or filtre(k)]:
                self._valeurs.pop(k, None)
