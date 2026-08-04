"""
MARCO — Metadata Audit and Review for Compliance Operations
Laedt alle "In Review By Domain"-Cases aus Collibra und bewertet sie
mit Claude (SAP AI Proxy) dynamisch. Erstellt einen HTML-Bericht.

Konfiguration: marco_config.py (JSESSIONID + AI_API_KEY anpassen)
"""

import os
import re
import sys
import json
import requests
from datetime import datetime

# ── Konfiguration laden ───────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
_today      = datetime.now().strftime("%Y-%m-%d")
REPORT_PATH = os.path.join(BASE_DIR, f"marco_{_today}.html")

COLLIBRA_HOST = "https://sap.collibra.com"
STATUS_IN_REVIEW = "In Review By Domain"

# Konfigurationsdatei einlesen (marco_config.py im selben Ordner)
_config_path = os.path.join(BASE_DIR, "marco_config.py")
if not os.path.exists(_config_path):
    print("FEHLER: marco_config.py nicht gefunden.")
    print(f"Bitte die Datei '{_config_path}' erstellen (Vorlage: marco_config.example.py)")
    sys.exit(1)

_cfg = {}
with open(_config_path, encoding="utf-8") as _f:
    exec(_f.read(), _cfg)

JSESSIONID  = _cfg.get("JSESSIONID", "")
AI_API_KEY  = _cfg.get("AI_API_KEY", "")
AI_BASE_URL = _cfg.get("AI_BASE_URL", "http://localhost:6655")
AI_MODEL    = _cfg.get("AI_MODEL", "claude-sonnet-4-6")

if not JSESSIONID or JSESSIONID == "DEINE-JSESSIONID-HIER":
    print("FEHLER: JSESSIONID in marco_config.py ist nicht gesetzt.")
    sys.exit(1)
if not AI_API_KEY or AI_API_KEY == "DEIN-AI-API-KEY-HIER":
    print("FEHLER: AI_API_KEY in marco_config.py ist nicht gesetzt.")
    sys.exit(1)

# Feldreihenfolge in der Attribut-Tabelle
REQUIRED_FIELDS = [
    "Purpose",
    "Beschreibung",
    "Authorization",
    "Authorization (German)",
    "User Group",
    "Domain",
]
BOOLEAN_FIELDS = [
    "Data Downloading Allowed",
    "Data Forwarding Allowed",
    "Contains direct Personal Data",
    "Contains indirect Personal Data",
    "German Employee Data",
    "Intends Performance Control",
]
ATTRIBUTE_ORDER = REQUIRED_FIELDS + BOOLEAN_FIELDS

# Wissensbasis laden (einmalig beim Start)
_kb_path = os.path.join(BASE_DIR, "knowledge_base_distilled.json")
_kb = {}
if os.path.exists(_kb_path):
    with open(_kb_path, encoding="utf-8") as _f:
        _kb = json.load(_f)

def _kb_section(key, title):
    items = _kb.get(key, [])
    if not items:
        return ""
    return f"\n## {title}\n" + "\n".join(f"- {item}" for item in items)


def build_system_prompt():
    kb_block = (
        _kb_section("ablehnungsgruende",  "Häufige Ablehnungsgründe des Betriebsrats (aus echten Cases)") +
        _kb_section("typische_maengel",   "Typische Mängel die zur Ablehnung führen") +
        _kb_section("beispiele_gut",      "Was bei genehmigten Cases gut gemacht wurde") +
        _kb_section("wichtige_hinweise",  "Wichtige Hinweise aus dem Betriebsrats-Prozess")
    )

    return f"""Du bist ein Datenschutz-Compliance-Experte bei SAP.
Du prüfst "Purpose of Use"-Cases (PoU) vor der Einreichung beim Betriebsrat.

Deine Aufgabe: Analysiere die Felder eines PoU-Cases und identifiziere alle
offenen Punkte die ergänzt oder geklärt werden müssen.

## Pflichtfelder (müssen ausgefüllt sein)
- Purpose, Beschreibung, Authorization, Authorization (German), User Group, Domain

## Boolean-Felder (müssen explizit Ja oder Nein sein)
- Data Downloading Allowed, Data Forwarding Allowed, Contains direct Personal Data,
  Contains indirect Personal Data, German Employee Data, Intends Performance Control

## Prüfregeln

**Personenbezug**
- Direkter oder indirekter Personenbezug = Ja → German Employee Data und Intends Performance Control müssen explizit gesetzt sein
- German Employee Data = Ja → Intends Performance Control muss angegeben sein
- German Employee Data = Ja → Purpose/Beschreibung muss erläutern wie LVK verhindert wird
- Intends Performance Control = Ja → Purpose muss erläutern dass nur direkte Vorgesetzte Einzeldaten sehen, höhere Ebenen nur aggregierte Daten

**Data Download**
- Data Downloading = Ja → PET-Eintrag zwingend erforderlich (im Purpose/Beschreibung)
- Data Downloading = Ja und PET vorhanden → Löschkonzept mit Fristen muss beschrieben sein
- Data Downloading = Ja → Zweck des Downloads muss beschrieben sein
- Data Downloading = Ja → Beschreibung der Berechtigungsprüfung nach Download erforderlich

**Data Forwarding**
- Data Forwarding = Ja → Zweck der Datenweitergabe und Empfängerkreis muss beschrieben sein

**Authorization**
- Nur Rollencode ohne Erklärung (z.B. "ZAUTH:00 CRMS06") → unzureichend
- Muss beschreiben wie Zugriff beantragt wird (ARM, Shop, Antrag etc.)
- Authorization (German) fehlt obwohl Authorization (English) vorhanden → ergänzen

**User Group**
- Zu vage (nur "colleagues", "employees", "users" etc.) → konkrete Rollen und Abteilungen nennen
- Nur ein einziger Eintrag ohne Komma → wahrscheinlich zu vage

**Textqualität**
- Purpose sehr kurz (unter 50 Zeichen) → ausführlicher beschreiben
- Beschreibung sehr kurz (unter 80 Zeichen) → ausführlicher beschreiben
- Abkürzungen sollten ausgeschrieben oder erklärt werden
{kb_block}

## Ausgabeformat

Antworte NUR mit validem JSON in exakt diesem Format:
{{
  "findings": [
    "Konkreter Hinweis was fehlt oder zu prüfen ist",
    "Weiterer Hinweis"
  ],
  "summary": "Ein Satz der den wichtigsten offenen Punkt beschreibt, oder 'Alle Felder vollständig — bereit für den Betriebsrat.' wenn nichts offen ist."
}}

- findings: Liste der offenen Punkte (leer wenn alles OK)
- summary: Genau ein Satz, klar und präzise
- Schreibe auf Deutsch
- Sei direkt und konkret — kein unnötiges Aufblähen
- Zitiere bei Bedarf den tatsächlichen Feldinhalt um klar zu machen was gemeint ist
"""

CLAUDE_SYSTEM_PROMPT = build_system_prompt()


# ── Collibra Session aufbauen ─────────────────────────────────────────────────
def build_session() -> requests.Session:
    session = requests.Session()
    session.cookies.set("DGC_DISCLAIMER_COOKIE", "true",     domain="sap.collibra.com")
    session.cookies.set("JSESSIONID",            JSESSIONID, domain="sap.collibra.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json",
    })
    return session


# ── Cases laden ───────────────────────────────────────────────────────────────
def get_assets_by_status(session, status_name):
    all_assets = []
    offset, limit = 0, 50
    while True:
        resp = session.get(
            f"{COLLIBRA_HOST}/rest/2.0/assets",
            params={"typePublicIds": "PurposeOfUse_C", "limit": limit, "offset": offset}
        )
        resp.raise_for_status()
        data  = resp.json()
        batch = data.get("results", [])
        all_assets.extend(batch)
        if len(all_assets) >= data["total"] or not batch:
            break
        offset += limit
    return [a for a in all_assets if a.get("status", {}).get("name", "") == status_name]


def get_attributes(session, asset_id):
    resp = session.get(
        f"{COLLIBRA_HOST}/rest/2.0/attributes",
        params={"assetId": asset_id, "limit": 100}
    )
    resp.raise_for_status()
    result = {}
    for attr in resp.json().get("results", []):
        result[attr["type"]["name"]] = attr.get("value", "")
    return result


# ── HTML-Tags entfernen ───────────────────────────────────────────────────────
def strip_html(text):
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    text = re.sub(r'<p[^>]*>', '', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>', ', ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = (text.replace('&nbsp;', ' ').replace('&amp;', '&')
                .replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"'))
    text = re.sub(r',\s*,', ',', text)
    return text.strip().strip(',')


def field_is_empty(value):
    if value is None:
        return True
    return strip_html(str(value)).strip().lower() in ("", "none", "null")


# ── Claude-Bewertung eines Cases ──────────────────────────────────────────────
def evaluate_with_claude(asset_name, attributes):
    """Schickt die Attribute an Claude und bekommt Findings als JSON zurück."""

    # Attribute als lesbaren Text aufbereiten
    lines = []
    for field in ATTRIBUTE_ORDER:
        val = attributes.get(field, "")
        if isinstance(val, bool):
            val_str = "Ja" if val else "Nein"
        elif val:
            val_str = strip_html(str(val)).strip()
            if not val_str:
                val_str = "(leer)"
        else:
            val_str = "(leer)"
        lines.append(f"{field}: {val_str}")

    # Weitere Felder die nicht in ATTRIBUTE_ORDER sind
    for field, val in attributes.items():
        if field not in ATTRIBUTE_ORDER:
            if isinstance(val, bool):
                val_str = "Ja" if val else "Nein"
            else:
                val_str = strip_html(str(val)).strip() or "(leer)"
            lines.append(f"{field}: {val_str}")

    case_text = "\n".join(lines)

    user_message = f"""Bitte prüfe diesen Purpose of Use Case:

Case-Name: {asset_name}

Felder:
{case_text}

Antworte nur mit dem JSON-Objekt, ohne Markdown-Codeblöcke."""

    try:
        resp = requests.post(
            f"{AI_BASE_URL}/anthropic/v1/messages",
            headers={
                "x-api-key":         AI_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type":      "application/json",
            },
            json={
                "model":      AI_MODEL,
                "max_tokens": 2048,
                "system":     CLAUDE_SYSTEM_PROMPT,
                "messages":   [{"role": "user", "content": user_message}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["content"][0]["text"].strip()

        # JSON aus Antwort extrahieren (falls doch Markdown-Blöcke)
        if "```" in content:
            content = re.sub(r'```(?:json)?\s*', '', content).strip()

        result = json.loads(content)
        findings = [{"level": "open", "text": f} for f in result.get("findings", [])]
        summary  = result.get("summary", "")
        return findings, summary

    except Exception as e:
        print(f"    WARNUNG: Claude-Aufruf fehlgeschlagen ({e}) — Fallback auf leere Bewertung")
        return [], "Bewertung nicht verfügbar (AI-Fehler)."


# ── HTML-Bericht erstellen ────────────────────────────────────────────────────
def build_report(evaluated):
    now        = datetime.now().strftime("%d.%m.%Y %H:%M")
    total      = len(evaluated)
    open_count = sum(1 for e in evaluated if e["verdict"] == "Offen")
    ok_count   = sum(1 for e in evaluated if e["verdict"] == "OK")

    def verdict_info(verdict):
        return {"Offen": ("!", "cat-m"), "OK": ("OK", "cat-s")}.get(verdict, ("!", "cat-m"))

    cards_html = ""
    for e in evaluated:
        name         = e["asset"].get("name", "Unbekannt")
        asset_id     = e["asset"].get("id", "")
        collibra_url = f"{COLLIBRA_HOST}/asset/{asset_id}"
        findings     = e["findings"]
        summary      = e["summary"]
        char, cat_cls = verdict_info(e["verdict"])
        search_text  = name.lower()

        # Personenbezug-Tags
        tags_html = ""
        direct   = strip_html(str(e["attributes"].get("Contains direct Personal Data",   ""))).lower()
        indirect = strip_html(str(e["attributes"].get("Contains indirect Personal Data", ""))).lower()
        german   = strip_html(str(e["attributes"].get("German Employee Data",            ""))).lower()
        perf     = strip_html(str(e["attributes"].get("Intends Performance Control",     ""))).lower()
        domain   = strip_html(str(e["attributes"].get("Domain", "")))

        if direct   in ("ja", "true", "yes"): tags_html += '<span class="meta-tag tag-red">Direkter Personenbezug</span>'
        if indirect in ("ja", "true", "yes"): tags_html += '<span class="meta-tag tag-orange">Indirekter Personenbezug</span>'
        if german   in ("ja", "true", "yes"): tags_html += '<span class="meta-tag tag-orange">German Employee Data</span>'
        if perf     in ("ja", "true", "yes"): tags_html += '<span class="meta-tag tag-red">Leistungskontrolle</span>'
        if domain:                             tags_html += f'<span class="meta-tag">{domain}</span>'

        # Bewertungs-Block
        open_items = [f for f in findings if f["level"] == "open"]
        if open_items:
            findings_html = '<div class="finding-group"><div class="finding-group-title open-title">Zu ergänzen / prüfen</div>'
            for f in open_items:
                findings_html += f'<div class="finding-item finding-open">{f["text"]}</div>'
            findings_html += '</div>'
        else:
            findings_html = '<div class="finding-item finding-ok">Alles vollständig — keine offenen Punkte.</div>'

        # Attribut-Tabelle
        attr_rows = ""
        for field in ATTRIBUTE_ORDER:
            val      = e["attributes"].get(field, "")
            is_empty = field_is_empty(val)
            row_cls  = ' class="attr-missing"' if (is_empty and field in REQUIRED_FIELDS) else ""
            if isinstance(val, bool):
                val_display = "Ja" if val else "Nein"
            elif val and isinstance(val, str) and val.strip().startswith("<"):
                val_display = f'<div class="attr-richtext">{val}</div>'
            elif val and str(val).strip():
                val_display = str(val)
            else:
                val_display = "<span class='empty'>—</span>"
            attr_rows += f'<tr{row_cls}><td class="attr-key">{field}</td><td class="attr-val">{val_display}</td></tr>'

        # data-findings für Filter-Buttons
        findings_data = " | ".join(f["text"].lower() for f in findings)

        cards_html += f'''
<div class="case-card" data-search="{search_text}" data-findings="{findings_data}">
  <div class="case-header" onclick="toggleCase(this)">
    <div class="cat-badge {cat_cls}">{char}</div>
    <div class="case-title-block">
      <div class="case-title">{name}</div>
      <div class="case-summary">{summary}</div>
      <div class="meta-tags">{tags_html}</div>
    </div>
    <a class="collibra-link" href="{collibra_url}" target="_blank" onclick="event.stopPropagation()">Collibra &#x2197;</a>
    <span class="chevron">&#9654;</span>
  </div>
  <div class="case-body">
    <div class="body-section">
      <div class="body-section-title">Bewertung</div>
      {findings_html}
    </div>
    <div class="body-section">
      <div class="body-section-title">Attribute</div>
      <table class="attr-table">{attr_rows}</table>
    </div>
  </div>
</div>'''

    return f'''<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MARCO — Purpose of Use Review — {now}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #f1f4f8; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 14px; color: #1a1a2e; }}
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 24px 32px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }}
  .header-left h1 {{ color: #fff; font-size: 20px; font-weight: 700; margin-bottom: 10px; }}
  .badges {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .badge {{ padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
  .badge-total {{ background: rgba(255,255,255,0.15); color: #fff; }}
  .badge-ok  {{ background: #22c55e20; color: #4ade80; border: 1px solid #22c55e40; }}
  .badge-m   {{ background: #f59e0b20; color: #fbbf24; border: 1px solid #f59e0b40; }}
  .search-wrap {{ position: relative; }}
  .search-wrap input {{ background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 8px 14px 8px 36px; color: #fff; font-size: 13px; width: 260px; outline: none; }}
  .search-wrap input::placeholder {{ color: rgba(255,255,255,0.5); }}
  .search-wrap svg {{ position: absolute; left: 10px; top: 50%; transform: translateY(-50%); opacity: 0.5; }}
  .section-title {{ font-size: 13px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; padding: 24px 32px 8px; }}
  .case-card {{ background: #fff; border-radius: 12px; margin: 0 24px 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); overflow: hidden; }}
  .case-header {{ display: flex; align-items: center; gap: 14px; padding: 16px 20px; cursor: pointer; user-select: none; }}
  .case-header:hover {{ background: #f8fafc; }}
  .cat-badge {{ min-width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 13px; flex-shrink: 0; }}
  .cat-s {{ background: #dcfce7; color: #15803d; }}
  .cat-m {{ background: #fef9c3; color: #92400e; }}
  .case-title-block {{ flex: 1; min-width: 0; }}
  .case-title {{ font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .meta-tags {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }}
  .meta-tag {{ font-size: 11px; color: #475569; background: #f8fafc; border: 1px solid #e2e8f0; padding: 2px 8px; border-radius: 4px; }}
  .tag-red    {{ background: #fee2e2; border-color: #fca5a5; color: #991b1b; }}
  .tag-orange {{ background: #fef9c3; border-color: #fde68a; color: #92400e; }}
  .case-summary {{ font-size: 12px; color: #475569; margin-top: 3px; font-style: italic; }}
  .collibra-link {{ font-size: 12px; color: #3b82f6; text-decoration: none; padding: 4px 8px; border-radius: 4px; white-space: nowrap; }}
  .collibra-link:hover {{ background: #dbeafe; }}
  .chevron {{ font-size: 12px; color: #94a3b8; transition: transform 0.2s; flex-shrink: 0; }}
  .case-card.open .chevron {{ transform: rotate(90deg); }}
  .case-body {{ display: none; padding: 0 20px 20px; border-top: 1px solid #f1f5f9; }}
  .case-card.open .case-body {{ display: block; }}
  .body-section {{ margin-top: 16px; }}
  .body-section-title {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: #374151; margin-bottom: 8px; }}
  .finding-group {{ margin-bottom: 10px; }}
  .finding-group-title {{ font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 4px; }}
  .open-title {{ color: #92400e; }}
  .finding-item {{ font-size: 13px; padding: 6px 12px; border-radius: 6px; margin-bottom: 4px; }}
  .finding-open {{ background: #fef9c3; border-left: 3px solid #f59e0b; color: #92400e; }}
  .finding-ok   {{ background: #dcfce7; border-left: 3px solid #22c55e; color: #15803d; }}
  .attr-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  .attr-table .attr-key {{ font-weight: 600; color: #374151; padding: 4px 8px 4px 0; vertical-align: top; width: 45%; }}
  .attr-table .attr-val {{ color: #1e293b; padding: 4px 0; vertical-align: top; }}
  .attr-table tr + tr td {{ border-top: 1px solid #e0e7ef; }}
  .attr-table .attr-missing td {{ background: #fee2e2; }}
  .attr-table .empty {{ color: #94a3b8; }}
  .attr-richtext {{ font-size: 12px; color: #1e293b; line-height: 1.5; }}
  .attr-richtext p {{ margin: 0 0 4px 0; }}
  .filter-bar {{ padding: 12px 32px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; border-bottom: 1px solid #e2e8f0; background: #fff; }}
  .filter-label {{ font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-right: 4px; }}
  .filter-btn {{ padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; border: 1.5px solid #e2e8f0; background: #fff; color: #475569; cursor: pointer; transition: all 0.15s; }}
  .filter-btn:hover {{ border-color: #94a3b8; background: #f8fafc; }}
  .filter-btn.active {{ background: #1a1a2e; color: #fff; border-color: #1a1a2e; }}
</style>
</head>
<body>
<div class="header">
  <div class="header-left">
    <h1>MARCO — Purpose of Use Review</h1>
    <div class="badges">
      <span class="badge badge-total">{total} Cases</span>
      <span class="badge badge-m">Offen: {open_count}</span>
      <span class="badge badge-ok">OK: {ok_count}</span>
    </div>
  </div>
  <div class="search-wrap">
    <svg width="16" height="16" fill="none" stroke="#fff" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
    <input type="text" id="searchInput" placeholder="Suche nach Case-Name, Domain ..." oninput="filterCases()">
  </div>
</div>
<div class="section-title">In Review By Domain — {now}</div>
<div class="filter-bar">
  <span class="filter-label">Filter:</span>
  <button class="filter-btn active" onclick="setFilter(this, '')">Alle</button>
  <button class="filter-btn" onclick="setFilter(this, 'pet')">Data Download / PET</button>
  <button class="filter-btn" onclick="setFilter(this, 'lvk')">LVK / German Employee</button>
  <button class="filter-btn" onclick="setFilter(this, 'authorization')">Authorization</button>
  <button class="filter-btn" onclick="setFilter(this, 'pflichtfeld')">Pflichtfeld leer</button>
  <button class="filter-btn" onclick="setFilter(this, 'user group')">User Group</button>
</div>
{cards_html if cards_html else '<p style="color:#999;padding:24px 32px;">Keine Cases mit Status &quot;In Review By Domain&quot; gefunden.</p>'}
<div style="height:40px;"></div>
<script>
let activeFilter = '';
function toggleCase(h) {{ h.parentElement.classList.toggle("open"); }}
function setFilter(btn, kw) {{
  activeFilter = kw;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}
function filterCases() {{ applyFilters(); }}
function applyFilters() {{
  const q = document.getElementById("searchInput").value.toLowerCase();
  document.querySelectorAll(".case-card").forEach(card => {{
    const s = (card.dataset.search + " " + card.innerText).toLowerCase();
    const f = (card.dataset.findings || "").toLowerCase();
    card.style.display = (q===''||s.includes(q)) && (activeFilter===''||f.includes(activeFilter)) ? "" : "none";
  }});
}}
</script>
</body>
</html>'''


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print("=== MARCO — Purpose of Use Review ===\n")

    # Collibra-Verbindung prüfen
    session = build_session()
    test = session.get(f"{COLLIBRA_HOST}/rest/2.0/users/current")
    if test.status_code == 401:
        print("FEHLER: Collibra-Session abgelaufen (401).")
        print("Neue JSESSIONID in marco_config.py eintragen:")
        print("  Edge → F12 → Console → document.cookie → JSESSIONID kopieren")
        sys.exit(1)
    elif test.status_code != 200:
        print(f"FEHLER: Collibra API nicht erreichbar (Status {test.status_code}).")
        sys.exit(1)
    print(f"Collibra: eingeloggt als {test.json().get('userName', '?')}")

    # Cases laden
    print(f"\nLade '{STATUS_IN_REVIEW}'-Cases...")
    assets = get_assets_by_status(session, STATUS_IN_REVIEW)
    print(f"  -> {len(assets)} Cases gefunden\n")

    if not assets:
        print("Keine Cases gefunden.")
        sys.exit(0)

    # Attribute laden + Claude-Bewertung pro Case
    print(f"Bewerte Cases mit Claude ({AI_MODEL}) ...")
    evaluated = []
    for i, asset in enumerate(assets, 1):
        name  = asset.get("name", asset["id"])
        print(f"  [{i}/{len(assets)}] {name}")
        attrs    = get_attributes(session, asset["id"])
        findings, summary = evaluate_with_claude(name, attrs)
        verdict  = "Offen" if findings else "OK"
        evaluated.append({
            "asset":      asset,
            "attributes": attrs,
            "findings":   findings,
            "summary":    summary,
            "verdict":    verdict,
        })

    # Offen-Cases zuerst
    evaluated.sort(key=lambda e: 0 if e["verdict"] == "Offen" else 1)

    # Bericht erstellen
    print("\nErstelle HTML-Bericht...")
    html = build_report(evaluated)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    open_n = sum(1 for e in evaluated if e["verdict"] == "Offen")
    ok_n   = sum(1 for e in evaluated if e["verdict"] == "OK")
    print(f"\nErgebnis: {open_n} offen, {ok_n} OK")
    print(f"Bericht:  {REPORT_PATH}")
    print("\nFertig!")


if __name__ == "__main__":
    main()
