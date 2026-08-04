"""
Einmaliges Skript: Laedt alle Kommentare von Approved-Cases aus Collibra
und speichert sie in approved_comments.json.
Nur einmal ausfuehren — danach liegt die Datei lokal.
"""

import os
import re
import sys
import json
import requests

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH   = os.path.join(BASE_DIR, "approved_comments.json")
COLLIBRA_HOST = "https://sap.collibra.com"

# Konfiguration laden
_cfg = {}
with open(os.path.join(BASE_DIR, "marco_config.py"), encoding="utf-8") as f:
    exec(f.read(), _cfg)
JSESSIONID = _cfg["JSESSIONID"]


def build_session():
    session = requests.Session()
    session.cookies.set("DGC_DISCLAIMER_COOKIE", "true",     domain="sap.collibra.com")
    session.cookies.set("JSESSIONID",            JSESSIONID, domain="sap.collibra.com")
    session.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    return session


def strip_html(text):
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    return re.sub(r'\s+', ' ', text).strip()


def get_assets_by_status(session, status_name):
    all_assets, offset, limit = [], 0, 50
    while True:
        resp = session.get(f"{COLLIBRA_HOST}/rest/2.0/assets",
                           params={"typePublicIds": "PurposeOfUse_C", "limit": limit, "offset": offset})
        resp.raise_for_status()
        data  = resp.json()
        batch = data.get("results", [])
        all_assets.extend(batch)
        if len(all_assets) >= data["total"] or not batch:
            break
        offset += limit
    return [a for a in all_assets if a.get("status", {}).get("name", "") == status_name]


def load_all_comments(session):
    all_comments, offset, limit = [], 0, 500
    print("Lade alle Kommentare...")
    while True:
        resp = session.get(f"{COLLIBRA_HOST}/rest/2.0/comments",
                           params={"limit": limit, "offset": offset})
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        data  = resp.json()
        batch = data.get("results", [])
        all_comments.extend(batch)
        total = data.get("total", 0)
        print(f"  {len(all_comments)}/{total} geladen...")
        if len(all_comments) >= total or not batch:
            break
        offset += limit
    print(f"  -> {len(all_comments)} Kommentare gesamt\n")

    # Index: asset_id -> kommentare
    index = {}
    for c in all_comments:
        if c.get("system", False):
            continue
        aid = (c.get("baseResource") or {}).get("id")
        if not aid:
            continue
        content = strip_html(c.get("content", "")).strip()
        if not content or len(content) < 10:
            continue
        skip = ["i hereby confirm", "looks good", "automatically generated",
                "good to go", "technischer check", "zugestimmt bis"]
        if any(content.lower().startswith(p) for p in skip):
            continue
        if aid not in index:
            index[aid] = []
        index[aid].append(content)
    return index


def main():
    print("=== Approved-Kommentare laden ===\n")

    session = build_session()
    test = session.get(f"{COLLIBRA_HOST}/rest/2.0/users/current")
    if test.status_code != 200:
        print(f"FEHLER: Collibra nicht erreichbar (Status {test.status_code})")
        sys.exit(1)
    print(f"Eingeloggt als: {test.json().get('userName', '?')}\n")

    # Approved Cases laden
    print("Lade Approved-Cases...")
    approved = get_assets_by_status(session, "Approved")
    print(f"  -> {len(approved)} Approved Cases\n")

    # Alle Kommentare laden
    comment_index = load_all_comments(session)

    # Nur Kommentare von Approved-Cases sammeln
    entries = []
    for asset in approved:
        aid  = asset["id"]
        name = asset.get("name", aid)
        comments = comment_index.get(aid, [])
        for c in comments:
            entries.append({
                "status":  "Approved",
                "case":    name,
                "comment": c,
            })

    print(f"Approved-Kommentare: {len(entries)}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"Gespeichert: {OUTPUT_PATH}")
    print("\nFertig!")


if __name__ == "__main__":
    main()
