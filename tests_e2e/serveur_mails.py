"""Faux serveur d'e-mails (SMTP minimal) : chaque message reçu est écrit dans DOSSIER/<horodatage>.eml.

Usage : python serveur_mails.py DOSSIER [PORT=1025]. L'API l'utilise avec SMTP_HOTE=localhost, SMTP_PORT=PORT
(adresse locale : aucune authentification ni chiffrement demandés). Rien ne sort de la machine.
"""
import asyncio
import sys
import time
from pathlib import Path

DOSSIER = Path(sys.argv[1])
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 1025


async def client(lecteur: asyncio.StreamReader, ecrivain: asyncio.StreamWriter):
    def dire(ligne: str):
        ecrivain.write((ligne + "\r\n").encode())

    dire("220 e2e ESMTP")
    await ecrivain.drain()
    while True:
        ligne = await lecteur.readline()
        if not ligne:
            break
        commande = ligne.decode(errors="replace").strip()
        verbe = commande[:4].upper()
        if verbe == "EHLO":
            dire("250-e2e"); dire("250-8BITMIME"); dire("250 SMTPUTF8")
        elif verbe == "DATA":
            dire("354 fin par <CRLF>.<CRLF>")
            await ecrivain.drain()
            corps = []
            while True:
                l = await lecteur.readline()
                if l in (b".\r\n", b".\n", b""):
                    break
                corps.append(l[1:] if l.startswith(b"..") else l)
            DOSSIER.mkdir(parents=True, exist_ok=True)
            (DOSSIER / f"{time.time():.6f}.eml").write_bytes(b"".join(corps))
            dire("250 OK")
        elif verbe == "QUIT":
            dire("221 au revoir")
            await ecrivain.drain()
            break
        else:                        # HELO, MAIL, RCPT, RSET, NOOP…
            dire("250 OK")
        await ecrivain.drain()
    ecrivain.close()


async def main():
    serveur = await asyncio.start_server(client, "127.0.0.1", PORT)
    print(f"Serveur d'e-mails de test sur 127.0.0.1:{PORT} → {DOSSIER}", flush=True)
    async with serveur:
        await serveur.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
