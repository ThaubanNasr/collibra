"""
Einmaliges Skript: Claude analysiert alle 682 Kommentare aus knowledge_base.json
und extrahiert die relevanten Regeln, Ablehnungsgruende und Beispiele.
Ergebnis wird in knowledge_base_distilled.json gespeichert.
Nur einmal ausfuehren.
"""

import os
import sys
import json
import requests

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH  = os.path.join(BASE_DIR, "knowledge_base.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "knowledge_base_distilled.json")

# Konfiguration laden
cfg = {}
with open(os.path.join(BASE_DIR, "marco_config.py"), encoding="utf-8") as f:
    exec(f.read(), cfg)

AI_API_KEY  = cfg["AI_API_KEY"]
AI_BASE_URL = cfg["AI_BASE_URL"]
AI_MODEL    = cfg.get("AI_MODEL", "claude-sonnet-4-6")


def call_claude(system_prompt, user_message):
    resp = requests.post(
        f"{AI_BASE_URL}/anthropic/v1/messages",
        headers={
            "x-api-key":         AI_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type":      "application/json",
        },
        json={
            "model":      AI_MODEL,
            "max_tokens": 8096,
            "system":     system_prompt,
            "messages":   [{"role": "user", "content": user_message}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def main():
    print("=== Knowledge Base destillieren ===\n")

    with open(INPUT_PATH, encoding="utf-8") as f:
        kb = json.load(f)

    print(f"Kommentare gesamt: {len(kb)}")

    # Kommentare nach Status gruppieren und als Text aufbereiten
    rejected   = [e for e in kb if e["status"] == "Rejected"]
    info_req   = [e for e in kb if e["status"] == "Information Required"]
    approved   = [e for e in kb if e["status"] == "Approved"]

    def format_comments(entries):
        lines = []
        for e in entries:
            lines.append(f'[{e["case"][:50]}] {e["comment"][:300]}')
        return "\n".join(lines)

    system_prompt = """Du bist ein Datenschutz-Compliance-Experte bei SAP.
Du analysierst Kommentare aus einem Betriebsrats-Reviewprozess für "Purpose of Use"-Cases.

Deine Aufgabe: Extrahiere aus den Kommentaren die wichtigsten Erkenntnisse als kompakte Wissensbasis.

Antworte NUR mit validem JSON in exakt diesem Format:
{
  "ablehnungsgruende": [
    "Konkreter Ablehnungsgrund der häufig vorkommt"
  ],
  "typische_maengel": [
    "Typischer Mangel der bemängelt wird"
  ],
  "beispiele_gut": [
    "Beispiel was bei Approved-Cases gut beschrieben war"
  ],
  "wichtige_hinweise": [
    "Wichtiger inhaltlicher Hinweis für Bearbeiter"
  ]
}

Sei konkret und präzise. Keine Duplikate. Maximal 15 Einträge pro Kategorie.
Schreibe auf Deutsch."""

    # Alle drei Gruppen in einem einzigen Claude-Call verarbeiten
    user_message = f"""Analysiere diese Kommentare aus dem Betriebsrats-Reviewprozess:

=== REJECTED-CASES ({len(rejected)} Kommentare) ===
{format_comments(rejected)}

=== INFORMATION REQUIRED-CASES ({len(info_req)} Kommentare) ===
{format_comments(info_req)}

=== APPROVED-CASES ({len(approved)} Kommentare) ===
{format_comments(approved)}

Extrahiere die wichtigsten Erkenntnisse als JSON."""

    print("Schicke alle Kommentare an Claude zur Analyse...")
    print(f"  Rejected: {len(rejected)}, Info Required: {len(info_req)}, Approved: {len(approved)}")

    try:
        result_text = call_claude(system_prompt, user_message)

        # JSON extrahieren falls Markdown-Blöcke
        import re
        if "```" in result_text:
            result_text = re.sub(r'```(?:json)?\s*', '', result_text).strip()

        result = json.loads(result_text)

        # Statistik
        print(f"\nErgebnis:")
        for key, val in result.items():
            print(f"  {key}: {len(val)} Eintraege")

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\nGespeichert: {OUTPUT_PATH}")
        print("\nFertig!")

    except Exception as e:
        print(f"FEHLER: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
