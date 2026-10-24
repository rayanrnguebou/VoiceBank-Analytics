"""Jeu de données synthétique (petit) pour les tests — aucune donnée réelle."""
import random
from datetime import date, time, timedelta

BANQUES = ["Afriland First Bank", "BICEC", "Ecobank Cameroun", "SCB Cameroun", "UBA Cameroun"]
VILLES = ["Douala", "Yaoundé", "Bafoussam", "Garoua", "Limbe"]
PAYS = ["Cameroun", "Cameroun", "Cameroun", "France", "Belgique", "Canada"]
TYPES = ["Dépôt espèces", "Retrait DAB", "Virement sortant", "Paiement marchand", "Transfert international"]
CANAUX = ["Agence", "DAB", "Mobile Banking", "USSD", "Internet Banking"]


def inserer(conn, n_clients=200, n_txn=2000, n_credits=300):
    rnd = random.Random(42)
    clients = []
    for i in range(1, n_clients + 1):
        pays = rnd.choice(PAYS)
        clients.append(dict(
            id_client=f"CLI-{i:06d}", numero_compte=f"CM{i:010d}", nom=f"Nom{i}", prenom=f"Prenom{i}",
            sexe=rnd.choice(["M", "F"]), age=rnd.randint(18, 80), pays_residence=pays,
            est_diaspora="Non" if pays == "Cameroun" else "Oui", telephone="+237600000000",
            email=f"client{i}@exemple.cm", banque=rnd.choice(BANQUES), ville_compte=rnd.choice(VILLES),
            statut_compte=rnd.choice(["Actif", "Actif", "Inactif", "Suspendu"]),
            solde_fcfa=rnd.randint(0, 50_000_000), score_risque=rnd.choice(["Faible", "Moyen", "Élevé"])))
    conn.execute_many("""INSERT INTO voicebank.clients (id_client, numero_compte, nom, prenom, sexe, age,
        pays_residence, est_diaspora, telephone, email, banque, ville_compte, statut_compte, solde_fcfa,
        score_risque) VALUES (%(id_client)s, %(numero_compte)s, %(nom)s, %(prenom)s, %(sexe)s, %(age)s,
        %(pays_residence)s, %(est_diaspora)s, %(telephone)s, %(email)s, %(banque)s, %(ville_compte)s,
        %(statut_compte)s, %(solde_fcfa)s, %(score_risque)s)""", clients)

    txns = []
    for i in range(1, n_txn + 1):
        c = rnd.choice(clients)
        fraude = rnd.random() < 0.04
        txns.append(dict(
            id_transaction=f"TXN-{i:08d}", id_client=c["id_client"], banque=c["banque"],
            ville=c["ville_compte"], type_transaction=rnd.choice(TYPES), canal=rnd.choice(CANAUX),
            montant_fcfa=rnd.randint(1_000, 20_000_000),
            statut="Suspecte" if fraude else rnd.choice(["Réussie", "Réussie", "Échouée"]),
            est_frauduleuse="Oui" if fraude else "Non", est_internationale=rnd.choice(["Oui", "Non"]),
            date_transaction=date(2025, 1, 1) + timedelta(days=rnd.randint(0, 600)),
            heure_transaction=time(rnd.randint(0, 23), rnd.randint(0, 59))))
    conn.execute_many("""INSERT INTO voicebank.transactions (id_transaction, id_client, banque, ville,
        type_transaction, canal, montant_fcfa, statut, est_frauduleuse, est_internationale,
        date_transaction, heure_transaction) VALUES (%(id_transaction)s, %(id_client)s, %(banque)s,
        %(ville)s, %(type_transaction)s, %(canal)s, %(montant_fcfa)s, %(statut)s, %(est_frauduleuse)s,
        %(est_internationale)s, %(date_transaction)s, %(heure_transaction)s)""", txns)

    credits = []
    for i in range(1, n_credits + 1):
        c = rnd.choice(clients)
        credits.append(dict(
            id_credit=f"CRD-{i:07d}", id_client=c["id_client"], banque=c["banque"], ville=c["ville_compte"],
            type_credit=rnd.choice(["Crédit immobilier", "Crédit à la consommation", "Crédit automobile"]),
            garantie=rnd.choice(["Caution personnelle", "Hypothèque", "Sans garantie"]),
            revenu_annuel_fcfa=rnd.randint(1_000_000, 60_000_000),
            montant_fcfa=rnd.randint(100_000, 80_000_000), taux_interet_pct=round(rnd.uniform(5, 18), 2),
            duree_mois=rnd.choice([12, 24, 36, 60]), mensualite_fcfa=rnd.randint(10_000, 2_000_000),
            score_credit=rnd.randint(300, 850),
            statut_credit=rnd.choice(["En cours", "En cours", "Remboursé", "En retard", "Défaut"]),
            date_debut=date(2024, 1, 1) + timedelta(days=rnd.randint(0, 700))))
    conn.execute_many("""INSERT INTO voicebank.credits (id_credit, id_client, banque, ville, type_credit,
        garantie, revenu_annuel_fcfa, montant_fcfa, taux_interet_pct, duree_mois, mensualite_fcfa,
        score_credit, statut_credit, date_debut)
        VALUES (%(id_credit)s, %(id_client)s, %(banque)s, %(ville)s, %(type_credit)s, %(garantie)s,
        %(revenu_annuel_fcfa)s, %(montant_fcfa)s, %(taux_interet_pct)s, %(duree_mois)s, %(mensualite_fcfa)s,
        %(score_credit)s, %(statut_credit)s, %(date_debut)s)""", credits)

    alertes = [dict(id_transaction=t["id_transaction"], id_client=t["id_client"],
                    score=round(rnd.uniform(0.5, 1), 4),
                    niveau=rnd.choice(["Moyen", "Élevé", "Critique"]), motif="Montant inhabituel")
               for t in txns if t["est_frauduleuse"] == "Oui"]
    conn.execute_many("""INSERT INTO voicebank.alertes_fraude (id_transaction, id_client, score_anomalie,
        niveau_alerte, motif) VALUES (%(id_transaction)s, %(id_client)s, %(score)s, %(niveau)s,
        %(motif)s)""", alertes)
