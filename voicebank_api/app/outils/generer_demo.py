"""Génère un jeu de données de DÉMONSTRATION (fictif) dans une base vide.

Utile pour une démo en ligne (Render) ou un essai sans les vrais CSV.
Refuse d'écrire si la base contient déjà des clients (protège tes vraies données).

  ADMIN_DATABASE_URL=postgresql://admin:mdp@hote:5432/voicebank_db python -m app.outils.generer_demo
"""
import argparse
import os
import random
from datetime import date, time, timedelta

import psycopg2
from psycopg2.extras import execute_values

BANQUES = ["Afriland First Bank", "BICEC", "Ecobank Cameroun", "SCB Cameroun", "Société Générale Cameroun",
           "UBA Cameroun", "CCA Bank", "BGFIBank Cameroun", "NSIA Banque Cameroun", "Atlantic Business International"]
VILLES = ["Douala", "Yaoundé", "Bafoussam", "Garoua", "Bamenda", "Limbe", "Kribi", "Maroua", "Buea", "Bertoua"]
PAYS_DIASPORA = ["France", "Belgique", "Canada", "États-Unis", "Allemagne", "Royaume-Uni", "Suisse"]
TYPES = ["Dépôt espèces", "Retrait DAB", "Virement sortant", "Virement entrant", "Paiement marchand",
         "Paiement facture", "Mobile Money (envoi)", "Mobile Money (réception)", "Transfert international",
         "Paiement en ligne"]
CANAUX = ["Agence", "DAB", "Mobile Banking", "USSD", "Internet Banking"]
TYPES_CREDIT = ["Crédit immobilier", "Crédit à la consommation", "Crédit automobile", "Crédit professionnel",
                "Crédit scolaire", "Microfinancement", "Crédit agricole"]
GARANTIES = ["Caution personnelle", "Hypothèque", "Nantissement", "Sans garantie"]
PROFESSIONS = ["Commerçant", "Enseignant", "Ingénieur", "Médecin", "Fonctionnaire", "Étudiant", "Agriculteur",
               "Artisan", "Chauffeur", "Infirmier", "Comptable", "Entrepreneur"]
PRENOMS = ["Jean", "Marie", "Paul", "Aïcha", "Samuel", "Grace", "Ibrahim", "Christelle", "Hervé", "Nadège",
           "Boris", "Sandrine", "Rodrigue", "Larissa", "Franck", "Vanessa"]
NOMS = ["Mbarga", "Nguema", "Tchoupo", "Fotso", "Ndongo", "Kamga", "Essomba", "Abena", "Talla", "Njoya",
        "Owona", "Biya", "Manga", "Djoumessi", "Etoundi", "Nkoulou"]


def generer(conn, n_clients: int, n_txn: int, n_credits: int, graine: int = 2026):
    rnd = random.Random(graine)
    cur = conn.cursor()
    clients = []
    for i in range(1, n_clients + 1):
        diaspora = rnd.random() < 0.18
        clients.append((
            f"CLI-{i:06d}", f"CM{i:010d}", rnd.choice(NOMS), rnd.choice(PRENOMS), rnd.choice(["M", "F"]),
            rnd.randint(18, 80), rnd.choice(PAYS_DIASPORA) if diaspora else "Cameroun", "Oui" if diaspora else "Non",
            f"+2376{rnd.randint(10_000_000, 99_999_999)}", f"client{i}@exemple.cm", rnd.choice(PROFESSIONS),
            rnd.choice(BANQUES), rnd.choice(VILLES), rnd.choice(["Courant", "Épargne", "Professionnel"]),
            rnd.choices(["Actif", "Inactif", "Suspendu"], [85, 10, 5])[0],
            int(rnd.lognormvariate(14, 1.2)), rnd.choices(["Faible", "Moyen", "Élevé"], [60, 30, 10])[0]))
    execute_values(cur, """INSERT INTO voicebank.clients (id_client, numero_compte, nom, prenom, sexe, age,
        pays_residence, est_diaspora, telephone, email, profession, banque, ville_compte, type_compte,
        statut_compte, solde_fcfa, score_risque) VALUES %s""", clients)

    txns, alertes = [], []
    for i in range(1, n_txn + 1):
        c = rnd.choice(clients)
        heure = rnd.randint(0, 23)
        international = c[7] == "Oui" and rnd.random() < 0.5 or rnd.random() < 0.05
        montant = int(rnd.lognormvariate(11.5, 1.6)) + 500
        risque = (heure <= 5) * 0.04 + international * 0.03 + (montant > 5e6) * 0.05
        fraude = rnd.random() < 0.01 + risque
        txns.append((f"TXN-{i:08d}", c[0], c[6], c[7], c[11], c[12],
                     "Transfert international" if international else rnd.choice(TYPES), rnd.choice(CANAUX), montant,
                     "EUR" if c[7] == "Oui" else "XAF",
                     "Suspecte" if fraude else rnd.choices(["Réussie", "Échouée"], [95, 5])[0],
                     "Oui" if fraude else "Non", "Oui" if international else "Non",
                     date(2024, 1, 1) + timedelta(days=rnd.randint(0, 900)), time(heure, rnd.randint(0, 59))))
        if fraude or rnd.random() < 0.004:
            score = round(min(0.99, 0.5 + rnd.random() * 0.5), 4)
            niveau = "Critique" if score >= 0.85 else "Élevé" if score >= 0.7 else "Moyen"
            motif = rnd.choice(["Montant inhabituel", "Transaction nocturne", "Transfert international atypique",
                                "Canal inhabituel pour ce client"])
            alertes.append((txns[-1][0], c[0], score, niveau, motif))
    execute_values(cur, """INSERT INTO voicebank.transactions (id_transaction, id_client, pays_residence,
        est_diaspora, banque, ville, type_transaction, canal, montant_fcfa, devise_origine, statut,
        est_frauduleuse, est_internationale, date_transaction, heure_transaction) VALUES %s""", txns,
                   page_size=5000)
    execute_values(cur, """INSERT INTO voicebank.alertes_fraude (id_transaction, id_client, score_anomalie,
        niveau_alerte, motif) VALUES %s""", alertes)

    credits = []
    for i in range(1, n_credits + 1):
        c = rnd.choice(clients)
        revenu = int(rnd.lognormvariate(15.5, 0.6))
        montant = int(rnd.lognormvariate(15.3, 1.1))
        duree = rnd.choice([12, 24, 36, 48, 60, 120, 180])
        taux = round(rnd.uniform(6, 18), 2)
        mensualite = int(montant * (1 + taux / 100 * duree / 12) / duree)
        score = rnd.randint(300, 850)
        poids = mensualite / (revenu / 12)
        p_defaut = min(0.9, 0.04 + max(0, poids - 0.35) * 0.8 + (score < 500) * 0.15)
        tirage = rnd.random()
        statut = ("Défaut" if tirage < p_defaut * 0.5 else "En retard" if tirage < p_defaut
                  else rnd.choices(["En cours", "Remboursé"], [70, 30])[0])
        credits.append((f"CRD-{i:07d}", c[0], c[6], c[7], c[11], c[12], rnd.choice(TYPES_CREDIT), montant, taux,
                        duree, mensualite, revenu, score, rnd.choice(GARANTIES), statut,
                        date(2020, 1, 1) + timedelta(days=rnd.randint(0, 2000))))
    execute_values(cur, """INSERT INTO voicebank.credits (id_credit, id_client, pays_residence, est_diaspora,
        banque, ville, type_credit, montant_fcfa, taux_interet_pct, duree_mois, mensualite_fcfa,
        revenu_annuel_fcfa, score_credit, garantie, statut_credit, date_debut) VALUES %s""", credits)
    conn.commit()
    return len(clients), len(txns), len(credits), len(alertes)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--clients", type=int, default=3000)
    p.add_argument("--transactions", type=int, default=60000)
    p.add_argument("--credits", type=int, default=6000)
    p.add_argument("--si-vide", action="store_true", help="ne rien faire (sans erreur) si la base contient déjà des données")
    a = p.parse_args()
    url = os.environ.get("ADMIN_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Définis ADMIN_DATABASE_URL")
    with psycopg2.connect(url.replace("postgresql+psycopg2://", "postgresql://")) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM voicebank.clients")
        if cur.fetchone()[0] > 0:
            if a.si_vide:
                print("Base déjà remplie : données de démonstration non générées.")
                return
            raise SystemExit("La base contient déjà des clients : génération annulée pour protéger tes données.")
        nc, nt, ncr, na = generer(conn, a.clients, a.transactions, a.credits)
        print(f"✅ Démo générée : {nc} clients, {nt} transactions, {ncr} crédits, {na} alertes (données fictives).")


if __name__ == "__main__":
    main()
