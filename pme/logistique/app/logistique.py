"""Logistique : petit logiciel de gestion des commandes de la PME fictive.

Une commande décrémente le stock, est enregistrée en base, puis un mail de
confirmation part vers la boîte « commandes ». La commande passe alors au
statut « confirmée ». Configuration : /etc/logistique/logistique.conf.
"""

import configparser
import os
import smtplib
import uuid
from email.message import EmailMessage

import psycopg
from flask import Flask, abort, jsonify, redirect, render_template_string, request

CONF = configparser.ConfigParser()
CONF.read(os.environ.get("LOGISTIQUE_CONF", "/etc/logistique/logistique.conf"))

app = Flask(__name__)

PAGE = """<!doctype html><html lang="fr"><meta charset="utf-8">
<title>Logistique</title>
<style>body{font-family:sans-serif;margin:2rem;max-width:60rem}table{border-collapse:collapse;width:100%}
td,th{border-bottom:1px solid #ccc;padding:.3rem;text-align:left}</style>
<h1>Logistique</h1>
<h2>Nouvelle commande</h2>
<form method="post" action="/commandes">
 Client <input name="client" required>
 Produit <select name="sku">{% for p in produits %}<option value="{{p[0]}}">{{p[1]}}</option>{% endfor %}</select>
 Quantité <input name="quantite" type="number" min="1" value="1">
 <button>Commander</button>
</form>
<h2>Stocks</h2>
<table><tr><th>Réf.</th><th>Produit</th><th>Stock</th></tr>
{% for p in produits %}<tr><td>{{p[0]}}</td><td>{{p[1]}}</td><td>{{p[2]}}</td></tr>{% endfor %}</table>
<h2>Dernières commandes</h2>
<table><tr><th>N°</th><th>Réf.</th><th>Client</th><th>Produit</th><th>Qté</th><th>Statut</th><th>Date</th></tr>
{% for c in commandes %}<tr>{% for v in c %}<td>{{v}}</td>{% endfor %}</tr>{% endfor %}</table>
</html>"""


def db():
    return psycopg.connect(CONF["base"]["dsn"], connect_timeout=5)


def notify(ref, client, sku, quantite):
    msg = EmailMessage()
    msg["From"] = CONF["mail"]["expediteur"]
    msg["To"] = CONF["mail"]["destinataire"]
    msg["Subject"] = f"Commande {ref} confirmée"
    msg.set_content(f"Commande {ref}\nClient : {client}\nProduit : {sku}\nQuantité : {quantite}\n")
    with smtplib.SMTP(CONF["mail"]["smtp_host"], int(CONF["mail"].get("smtp_port", "25")), timeout=10) as s:
        s.send_message(msg)


def create(client, sku, quantite, ref=None):
    ref = ref or f"CMD-{uuid.uuid4().hex[:8].upper()}"
    with db() as conn:
        row = conn.execute("UPDATE produits SET stock = stock - %s WHERE sku = %s AND stock >= %s RETURNING nom",
                           (quantite, sku, quantite)).fetchone()
        if row is None:
            raise ValueError("produit inconnu ou stock insuffisant")
        cid = conn.execute("INSERT INTO commandes (ref, client, sku, quantite) VALUES (%s, %s, %s, %s) RETURNING id",
                           (ref, client, sku, quantite)).fetchone()[0]
    try:
        notify(ref, client, sku, quantite)
        statut = "confirmée"
    except OSError as exc:
        app.logger.error("mail de confirmation en échec pour %s : %s", ref, exc)
        statut = "mail en échec"
    with db() as conn:
        conn.execute("UPDATE commandes SET statut = %s WHERE id = %s", (statut, cid))
    return cid, ref, statut


@app.get("/health")
def health():
    with db() as conn:
        n = conn.execute("SELECT count(*) FROM commandes").fetchone()[0]
    return jsonify(base="ok", commandes=n)


@app.get("/")
def index():
    with db() as conn:
        produits = conn.execute("SELECT sku, nom, stock FROM produits ORDER BY sku").fetchall()
        commandes = conn.execute("SELECT id, ref, client, sku, quantite, statut, to_char(cree_le, 'YYYY-MM-DD HH24:MI') "
                                 "FROM commandes ORDER BY id DESC LIMIT 20").fetchall()
    return render_template_string(PAGE, produits=produits, commandes=commandes)


@app.post("/commandes")
def form_create():
    create(request.form["client"], request.form["sku"], int(request.form.get("quantite", 1)))
    return redirect("/", code=303)


@app.post("/api/commandes")
def api_create():
    data = request.get_json(force=True)
    try:
        cid, ref, statut = create(data["client"], data["sku"], int(data["quantite"]), data.get("ref"))
    except (KeyError, ValueError) as exc:
        return jsonify(erreur=str(exc)), 400
    return jsonify(id=cid, ref=ref, statut=statut), 201


@app.get("/api/commandes/<int:cid>")
def api_get(cid):
    with db() as conn:
        row = conn.execute("SELECT id, ref, client, sku, quantite, statut, cree_le FROM commandes WHERE id = %s",
                           (cid,)).fetchone()
    if row is None:
        abort(404)
    keys = ("id", "ref", "client", "sku", "quantite", "statut", "cree_le")
    return jsonify({k: (v.isoformat() if k == "cree_le" else v) for k, v in zip(keys, row)})
