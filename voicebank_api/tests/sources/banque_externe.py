"""Base « externe » de test, au schéma très différent de VoiceBank (anglais, autres noms, défauts
de qualité volontaires), créée à l'identique dans PostgreSQL, MySQL/MariaDB et SQLite."""
import random
from datetime import date, timedelta

VILLES = ["Douala", "Yaoundé", "Bafoussam", "Garoua", "Bamenda"]
SEGMENTS = ["Retail", "SME", "Corporate"]
STATUTS = ["active", "closed", "late", "default"]
CANAUX = ["mobile_money", "branch", "card", "transfer"]

DDL = """
CREATE TABLE branches (branch_id INTEGER PRIMARY KEY, branch_name VARCHAR(60), city VARCHAR(40));
CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, first_name VARCHAR(40), last_name VARCHAR(40),
  email VARCHAR(80), phone VARCHAR(20), city VARCHAR(40), segment VARCHAR(20), branch_id INTEGER, created_at DATE);
CREATE TABLE accounts (account_id INTEGER PRIMARY KEY, customer_id INTEGER, account_number VARCHAR(30),
  balance DECIMAL(14,2), currency VARCHAR(3), opened_on DATE);
CREATE TABLE loans (loan_id INTEGER PRIMARY KEY, customer_id INTEGER, principal DECIMAL(14,2),
  interest_rate DECIMAL(5,2), status VARCHAR(20), start_date DATE, due_date DATE);
CREATE TABLE payments (payment_id INTEGER PRIMARY KEY, loan_id INTEGER, amount DECIMAL(14,2), paid_at DATE,
  channel VARCHAR(20), is_fraud INTEGER, user_password VARCHAR(60));
"""


def lignes():
    r = random.Random(7)
    base = date(2025, 1, 1)
    branches = [(i, f"Agence {v}", v) for i, v in enumerate(VILLES, 1)]
    customers = []
    for i in range(1, 301):
        v = r.choice(VILLES)
        customers.append((i, f"Prenom{i}", f"Nom{i}", f"client{i}@mail.cm", f"+2376{r.randint(10000000, 99999999)}",
                          v if i % 25 else None, r.choice(SEGMENTS), VILLES.index(v) + 1,
                          base - timedelta(days=r.randint(0, 900))))
    accounts = [(i, r.randint(1, 300), f"CM21{r.randint(10**9, 10**10 - 1)}",
                 round(r.uniform(-50000, 5_000_000), 2) if i % 40 == 0 else round(r.uniform(0, 5_000_000), 2),
                 "XAF", base - timedelta(days=r.randint(0, 900))) for i in range(1, 401)]
    loans = []
    for i in range(1, 201):
        cust = r.randint(1, 300) if i % 50 else 999          # 4 crédits orphelins (client inexistant)
        start = base + timedelta(days=r.randint(0, 600))
        loans.append((i, cust, round(r.uniform(100_000, 20_000_000), 2), round(r.uniform(6, 24), 2),
                      r.choices(STATUTS, [6, 2, 2, 1])[0], start, start + timedelta(days=365)))
    payments = []
    for i in range(1, 1501):
        d = base + timedelta(days=r.randint(0, 640))
        if i % 300 == 0:
            d = date(2031, 1, 1)                           # dates futures
        payments.append((i, r.randint(1, 200), round(r.uniform(5_000, 900_000), 2), d, r.choice(CANAUX),
                         1 if r.random() < 0.04 else 0, "x"))
    return {"branches": branches, "customers": customers, "accounts": accounts, "loans": loans, "payments": payments}


def remplir(curseur, style="%s"):
    for instr in [s for s in DDL.split(";") if s.strip()]:
        curseur.execute(instr)
    for table, rows in lignes().items():
        marques = ", ".join([style] * len(rows[0]))
        curseur.executemany(f"INSERT INTO {table} VALUES ({marques})", rows)
