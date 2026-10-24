"""Mesure le taux de bonnes réponses sur evaluation/questions.json.

Avec Docker : docker compose exec api python -m app.outils.evaluer
Écrit aussi evaluation/rapport.md (si le dossier est accessible en écriture).
"""
import sys

from ..evaluation import FICHIER_QUESTIONS, evaluer


def main():
    r = evaluer()
    lignes = [f"# Fiabilité VoiceBank — {r['date']}", "",
              f"**{r['taux_reussite']} %** de bonnes réponses ({r['nb_reussies']}/{r['nb_questions']}), "
              f"Gemini {'actif' if r['gemini_actif'] else 'inactif'}.", "",
              "| Catégorie | Justes | Taux |", "|---|---|---|"]
    lignes += [f"| {c} | {s['justes']}/{s['questions']} | {s['taux']} % |" for c, s in r["par_categorie"].items()]
    lignes += ["", "| Source | Justes | Taux |", "|---|---|---|"]
    lignes += [f"| {c} | {s['justes']}/{s['questions']} | {s['taux']} % |"
               for c, s in r["par_source"].items() if s["questions"]]
    lignes += ["", "## Réponses fausses ou non traitées", ""]
    lignes += [f"- [{d['statut']}] {d['question']}" + (f" — `{d.get('sql', '')[:150]}`" if d.get("sql") else "")
               for d in r["details"] if d["statut"] != "juste"]
    rapport = "\n".join(lignes)
    print(rapport)
    try:
        (FICHIER_QUESTIONS.parent / "rapport.md").write_text(rapport + "\n", encoding="utf-8")
    except OSError:
        pass
    return 0 if r["nb_questions"] else 1


if __name__ == "__main__":
    sys.exit(main())
