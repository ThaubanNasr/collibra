"""
MARCO — Metadata Audit and Review for Compliance Operations
Bewertet alle "In Review by Domain"-Cases regelbasiert anhand von
Approved/Rejected/Information-Required-Cases als Referenz.
Gibt einen lokalen HTML-Bericht aus.
"""

import os
import re
import sys
import requests
from datetime import datetime

# ── Konfiguration ─────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
_today        = datetime.now().strftime("%Y-%m-%d")
REPORT_PATH   = os.path.join(BASE_DIR, f"marco_{_today}.html")
COLLIBRA_HOST = "https://sap.collibra.com"

JSESSIONID = "5ecaf59f-dc3f-456e-8006-6eb5288e3d5b"  # Aus Edge: F12 → Console → document.cookie

# Status-Namen exakt wie in Collibra
STATUS_IN_REVIEW = "In Review By Domain"

# Pflichtfelder — müssen ausgefüllt sein
REQUIRED_FIELDS = [
    "Purpose",
    "Beschreibung",
    "Authorization",
    "Authorization (German)",
    "User Group",
    "Domain",
]

# Boolean-Felder — müssen explizit gesetzt sein (Ja oder Nein)
BOOLEAN_FIELDS = [
    "Data Downloading Allowed",
    "Data Forwarding Allowed",
    "Contains direct Personal Data",
    "Contains indirect Personal Data",
    "German Employee Data",
    "Intends Performance Control",
]

# Felder die bei Personenbezug besondere Aufmerksamkeit brauchen
PERSONAL_DATA_FIELDS = [
    "Contains direct Personal Data",
    "Contains indirect Personal Data",
    "German Employee Data",
    "Intends Performance Control",
]

ATTRIBUTE_ORDER = REQUIRED_FIELDS + BOOLEAN_FIELDS


# ── Session aufbauen ──────────────────────────────────────────────────────────
def build_session() -> requests.Session:
    session = requests.Session()
    session.cookies.set("DGC_DISCLAIMER_COOKIE", "true",     domain="sap.collibra.com")
    session.cookies.set("JSESSIONID",            JSESSIONID, domain="sap.collibra.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json",
    })
    return session


# ── Alle POU-Assets einer bestimmten Status-Gruppe abrufen ────────────────────
def get_assets_by_status(session, status_name):
    all_assets = []
    offset = 0
    limit  = 50
    while True:
        resp = session.get(
            f"{COLLIBRA_HOST}/rest/2.0/assets",
            params={
                "typePublicIds": "PurposeOfUse_C",
                "limit":         limit,
                "offset":        offset,
            }
        )
        resp.raise_for_status()
        data  = resp.json()
        batch = data.get("results", [])
        all_assets.extend(batch)
        if len(all_assets) >= data["total"] or not batch:
            break
        offset += limit

    return [a for a in all_assets
            if a.get("status", {}).get("name", "") == status_name]


# ── Attribute eines Assets abrufen ───────────────────────────────────────────
def get_attributes(session, asset_id):
    resp = session.get(
        f"{COLLIBRA_HOST}/rest/2.0/attributes",
        params={"assetId": asset_id, "limit": 100}
    )
    resp.raise_for_status()
    result = {}
    for attr in resp.json().get("results", []):
        name  = attr["type"]["name"]
        value = attr.get("value", "")
        result[name] = value
    return result


# ── HTML-Tags entfernen ───────────────────────────────────────────────────────
def strip_html(text):
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = (text.replace('&nbsp;', ' ').replace('&amp;', '&')
                .replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"'))
    return text.strip()


def field_is_empty(value):
    if value is None:
        return True
    clean = strip_html(str(value)).strip()
    return clean == "" or clean.lower() in ("none", "null")


# ── Regelbasierte Bewertung eines Cases ──────────────────────────────────────
def evaluate_case(asset, attributes):
    findings = []

    def err(text):  findings.append({"level": "open", "text": text})
    def warn(text): findings.append({"level": "open", "text": text})
    def info(text): findings.append({"level": "open", "text": text})

    # Hilfswerte
    purpose_text = strip_html(str(attributes.get("Purpose",        "")))
    desc_text    = strip_html(str(attributes.get("Beschreibung",   "")))
    auth_en      = strip_html(str(attributes.get("Authorization",  "")))
    auth_de      = strip_html(str(attributes.get("Authorization (German)", "")))
    user_group   = strip_html(str(attributes.get("User Group",     "")))
    domain       = strip_html(str(attributes.get("Domain",         "")))

    direct   = strip_html(str(attributes.get("Contains direct Personal Data",   ""))).lower()
    indirect = strip_html(str(attributes.get("Contains indirect Personal Data", ""))).lower()
    german   = strip_html(str(attributes.get("German Employee Data",            ""))).lower()
    perf     = strip_html(str(attributes.get("Intends Performance Control",     ""))).lower()
    download = strip_html(str(attributes.get("Data Downloading Allowed",        ""))).lower()
    forward  = strip_html(str(attributes.get("Data Forwarding Allowed",         ""))).lower()

    has_personal = direct in ("ja", "true", "yes") or indirect in ("ja", "true", "yes")
    is_german    = german  in ("ja", "true", "yes")
    is_perf      = perf    in ("ja", "true", "yes")
    is_download  = download in ("ja", "true", "yes")
    is_forward   = forward  in ("ja", "true", "yes")

    all_text = (purpose_text + " " + desc_text + " " + auth_en + " " + auth_de).lower()

    # ── 1. Pflichtfelder ─────────────────────────────────────────────────────
    for field in REQUIRED_FIELDS:
        if field_is_empty(attributes.get(field)):
            err(f'Pflichtfeld "{field}" ist leer.')

    # ── 2. Boolean-Felder müssen gesetzt sein ────────────────────────────────
    for field in BOOLEAN_FIELDS:
        val = attributes.get(field)
        if val is None or strip_html(str(val)).strip() == "":
            err(f'"{field}" ist nicht gesetzt — muss explizit Ja oder Nein sein.')

    # ── 3. Personenbezug-Konsistenz ──────────────────────────────────────────
    if has_personal:
        if not is_german and german == "":
            warn('"German Employee Data" muss explizit gesetzt sein, da personenbezogene Daten vorhanden sind.')
        if perf == "":
            warn('"Intends Performance Control" muss explizit gesetzt sein, da personenbezogene Daten vorhanden sind.')

    # ── 4. German Employee Data = Ja → LVK-Schutz muss beschrieben sein ─────
    if is_german:
        if perf == "":
            err('"German Employee Data" ist Ja — "Intends Performance Control" muss angegeben werden.')
        # Muss erläutert sein wie LVK verhindert wird
        lvk_keywords = ["leistung", "lvk", "performance control", "verhaltenskontrolle",
                        "performance management", "nicht zur leistung", "not for performance"]
        if not any(kw in all_text for kw in lvk_keywords):
            warn('German Employee Data = Ja — bitte im Purpose/Beschreibung erläutern wie Leistungs- und Verhaltenskontrolle (LVK) verhindert wird.')

    # ── 5. Data Download = Ja → PET-Eintrag + Löschkonzept + Begründung ───────
    if is_download:
        pet_keywords = ["pet", "pet entry", "pet-eintrag", "privacy exception"]
        has_pet = any(kw in all_text for kw in pet_keywords)
        if not has_pet:
            err('Data Downloading = Ja — ein PET-Eintrag ist erforderlich. Bitte im Purpose/Beschreibung auf den PET-Eintrag verweisen.')
        else:
            # Nur prüfen wenn PET vorhanden — Löschkonzept steht normalerweise im PET,
            # muss aber auch im PoU erwähnt sein (häufiger Ablehnungsgrund, 30x in Wissensbasis)
            retention_keywords = ["lösch", "loeschkonzept", "löschkonzept", "retention", "aufbewahrung",
                                  "delete", "deletion", "aufbewahrungs", "frist", "archiv"]
            if not any(kw in all_text for kw in retention_keywords):
                err('Data Downloading = Ja — Löschkonzept fehlt. Bitte im Purpose/Beschreibung beschreiben wie sichergestellt wird, dass heruntergeladene Daten nach Nutzung gelöscht werden.')
        # Zweck des Downloads muss beschrieben sein
        download_reason_keywords = ["download", "herunterladen", "export", "backup", "präsentation",
                                    "offline", "audit", "sicherung"]
        if not any(kw in all_text for kw in download_reason_keywords):
            warn('Data Downloading = Ja — der Zweck des Downloads ist nicht im Purpose/Beschreibung erklärt.')

    # ── 6. Data Forwarding = Ja → Begründung erforderlich ───────────────────
    if is_forward:
        forward_reason_keywords = ["weiterleitung", "forwarding", "weitergabe", "teilen", "share",
                                   "external", "extern", "dritte", "third party"]
        if not any(kw in all_text for kw in forward_reason_keywords):
            warn('Data Forwarding = Ja — der Zweck der Datenweitergabe ist nicht im Purpose/Beschreibung erklärt.')

    # ── 7. Authorization muss verständlich beschrieben sein ─────────────────
    if auth_en or auth_de:
        auth_text = (auth_en + " " + auth_de).lower()
        # Nur Rollenname ohne Erklärung (z.B. nur "ZAUTH:00 CRMS06")
        if len(auth_text) < 20:
            warn('Authorization wirkt sehr kurz — bitte genauer beschreiben wie Zugriff beantragt wird und wer Zugriff erhält.')
        # Keine Beschreibung wie man Zugriff bekommt
        access_keywords = ["request", "beantragen", "arm", "shop", "bereich", "space",
                           "antrag", "approval", "raise", "role", "rolle", "zugriff",
                           "access", "zauth", "permission", "berechtigung", "t.yx0"]
        if not any(kw in auth_text for kw in access_keywords):
            warn('Authorization: Es ist nicht beschrieben wie Benutzer Zugriff beantragen können.')

    # ── 8. User Group nicht zu vage ──────────────────────────────────────────
    vague_terms = ["colleagues", "kollegen", "mitarbeiter", "employees", "users", "alle", "everyone"]
    if user_group:
        ug_lower = user_group.lower().strip()
        if any(vg == ug_lower for vg in vague_terms) or len(user_group) < 10 or "," not in ug_lower:
            warn(f'User Group zu vage ("{user_group}") — bitte konkrete Rollen angeben, z.B. "Carfleet Manager, Fleet Administrators".')

    # ── 9. Mindestlänge Purpose / Beschreibung ───────────────────────────────
    if purpose_text and len(purpose_text) < 50:
        warn(f'"Purpose" ist sehr kurz ({len(purpose_text)} Zeichen) — bitte ausführlicher beschreiben.')
    if desc_text and len(desc_text) < 80:
        warn(f'"Beschreibung" ist sehr kurz ({len(desc_text)} Zeichen) — bitte ausführlicher beschreiben.')

    # ── 10. Authorization (German) muss vorhanden sein ───────────────────────
    if auth_en and not auth_de:
        warn('"Authorization" ist angegeben, aber "Authorization (German)" fehlt.')

    # ── 11. Intends Performance Control = Ja → muss erklärt sein ────────────
    if is_perf:
        perf_explain_kw = ["nur direkte", "only direct", "aggregiert", "aggregated",
                           "nicht einzeln", "not individual", "manager", "vorgesetzte"]
        if not any(kw in all_text for kw in perf_explain_kw):
            warn('"Intends Performance Control" ist Ja — bitte im Purpose erläutern dass nur direkte Vorgesetzte Einzeldaten sehen, höhere Ebenen nur aggregierte Daten.')

    # ── 12. Gesamtbewertung ──────────────────────────────────────────────────
    if findings:
        verdict = "Offen"
        verdict_color = "#f59e0b"
    else:
        verdict = "OK"
        verdict_color = "#22c55e"

    return {
        "verdict":       verdict,
        "verdict_color": verdict_color,
        "findings":      findings,
    }


# ── Wissensbasis aus Rejected + Info-Required Kommentaren aufbauen ────────────
# (entfernt — Regeln sind fest in evaluate_case() kodiert)


# ── Datum formatieren ─────────────────────────────────────────────────────────
def fmt_date(val):
    if val and isinstance(val, (int, float)):
        try:
            return datetime.fromtimestamp(val / 1000).strftime("%d.%m.%Y %H:%M")
        except Exception:
            pass
    return str(val) if val else ""


# ── HTML-Bericht im IUCR-Stil erstellen ──────────────────────────────────────
def build_report(in_review_cases):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    evaluated = []
    for case in in_review_cases:
        result = evaluate_case(case["asset"], case["attributes"])
        evaluated.append({**case, **result})

    # Statistik
    total    = len(evaluated)
    open_count = sum(1 for e in evaluated if e["verdict"] == "Offen")
    ok_count   = sum(1 for e in evaluated if e["verdict"] == "OK")

    # Sortieren: Offen zuerst, dann OK
    evaluated.sort(key=lambda e: 0 if e["verdict"] == "Offen" else 1)

    # Verdict → Kurzzeichen + CSS-Klasse (analog S/M/L)
    def verdict_info(verdict):
        return {
            "Offen": ("!", "cat-m", "badge-m"),
            "OK":    ("OK","cat-s", "badge-s"),
        }.get(verdict, ("!", "cat-m", "badge-m"))

    # ── Cards HTML ────────────────────────────────────────────────────────────
    cards_html = ""
    for idx, e in enumerate(evaluated):
        name     = e["asset"].get("name", "Unbekannt")
        asset_id = e["asset"].get("id", "")
        collibra_url = f"{COLLIBRA_HOST}/asset/{asset_id}"
        findings = e["findings"]
        char, cat_cls, _ = verdict_info(e["verdict"])

        # Suchtext für JS-Filter
        search_text = name.lower()

        # Personenbezug-Tags
        tags_html = ""
        direct   = strip_html(str(e["attributes"].get("Contains direct Personal Data",   ""))).lower()
        indirect = strip_html(str(e["attributes"].get("Contains indirect Personal Data", ""))).lower()
        german   = strip_html(str(e["attributes"].get("German Employee Data",            ""))).lower()
        perf     = strip_html(str(e["attributes"].get("Intends Performance Control",     ""))).lower()
        domain   = strip_html(str(e["attributes"].get("Domain", "")))

        if direct in ("ja","true","yes"):
            tags_html += '<span class="meta-tag tag-red">Direkter Personenbezug</span>'
        if indirect in ("ja","true","yes"):
            tags_html += '<span class="meta-tag tag-orange">Indirekter Personenbezug</span>'
        if german in ("ja","true","yes"):
            tags_html += '<span class="meta-tag tag-orange">German Employee Data</span>'
        if perf in ("ja","true","yes"):
            tags_html += '<span class="meta-tag tag-red">Leistungskontrolle</span>'
        if domain:
            tags_html += f'<span class="meta-tag">{domain}</span>'

        # 1-Satz Zusammenfassung
        open_items = [f for f in findings if f["level"] == "open"]
        if not open_items:
            summary = "Alle Felder vollständig — bereit für den Betriebsrat."
        elif len(open_items) == 1:
            summary = open_items[0]["text"][:100] + ("..." if len(open_items[0]["text"]) > 100 else "")
        else:
            topics = []
            if any("pet" in f["text"].lower() or "löschkonzept" in f["text"].lower() for f in open_items):
                topics.append("PET-Eintrag/Löschkonzept fehlt")
            if any("german employee" in f["text"].lower() or "lvk" in f["text"].lower() for f in open_items):
                topics.append("LVK nicht erklärt")
            if any("authorization" in f["text"].lower() for f in open_items):
                topics.append("Authorization unklar")
            if any("pflichtfeld" in f["text"].lower() for f in open_items):
                topics.append("Pflichtfeld leer")
            if any("user group" in f["text"].lower() for f in open_items):
                topics.append("User Group vage")
            if not topics:
                topics = [open_items[0]["text"][:60] + "..."]
            summary = f'{len(open_items)} offene Punkte: {", ".join(topics)}.'

        # Bewertungs-Items
        findings_items = ""
        if open_items:
            findings_items += '<div class="finding-group"><div class="finding-group-title open-title">Zu ergänzen / prüfen</div>'
            for f in open_items:
                findings_items += f'<div class="finding-item finding-open">{f["text"]}</div>'
            findings_items += '</div>'
        else:
            findings_items = '<div class="finding-item finding-ok">Alles vollständig — keine offenen Punkte.</div>'

        # Attribute-Tabelle
        attr_rows = ""
        for field in ATTRIBUTE_ORDER:
            val = e["attributes"].get(field, "")
            is_empty = field_is_empty(val)
            row_cls = ' class="attr-missing"' if (is_empty and field in REQUIRED_FIELDS) else ""
            if isinstance(val, bool):
                val_display = "Ja" if val else "Nein"
            elif val and isinstance(val, str) and val.strip().startswith("<"):
                val_display = f'<div class="attr-richtext">{val}</div>'
            elif val and str(val).strip():
                val_display = str(val)
            else:
                val_display = "<span class='empty'>—</span>"
            attr_rows += f'<tr{row_cls}><td class="attr-key">{field}</td><td class="attr-val">{val_display}</td></tr>'

        cards_html += f'''
<div class="case-card" data-search="{search_text}" data-findings="{" | ".join(f["text"].lower() for f in findings)}">
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
      {findings_items}
    </div>
    <div class="body-section">
      <div class="body-section-title">Attribute</div>
      <table class="attr-table">{attr_rows}</table>
    </div>
  </div>
</div>'''

    # ── Komplettes HTML ───────────────────────────────────────────────────────
    return f'''<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Purpose of Use — Review Bericht — {now}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #f1f4f8; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 14px; color: #1a1a2e; }}

  /* HEADER */
  .header {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 24px 32px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }}
  .header-left h1 {{ color: #fff; font-size: 20px; font-weight: 700; margin-bottom: 10px; }}
  .badges {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .badge {{ padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; }}
  .badge-total {{ background: rgba(255,255,255,0.15); color: #fff; }}
  .badge-ok  {{ background: #22c55e20; color: #4ade80; border: 1px solid #22c55e40; }}
  .badge-m   {{ background: #f59e0b20; color: #fbbf24; border: 1px solid #f59e0b40; }}
  .badge-l   {{ background: #ef444420; color: #f87171; border: 1px solid #ef444440; }}
  .search-wrap {{ position: relative; }}
  .search-wrap input {{ background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; padding: 8px 14px 8px 36px; color: #fff; font-size: 13px; width: 260px; outline: none; }}
  .search-wrap input::placeholder {{ color: rgba(255,255,255,0.5); }}
  .search-wrap svg {{ position: absolute; left: 10px; top: 50%; transform: translateY(-50%); opacity: 0.5; }}

  /* SECTION */
  .section-title {{ font-size: 13px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; padding: 24px 32px 8px; }}

  /* CASE CARD */
  .case-card {{ background: #fff; border-radius: 12px; margin: 0 24px 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); overflow: hidden; }}
  .case-header {{ display: flex; align-items: center; gap: 14px; padding: 16px 20px; cursor: pointer; user-select: none; }}
  .case-header:hover {{ background: #f8fafc; }}
  .cat-badge {{ min-width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 13px; flex-shrink: 0; }}
  .cat-s  {{ background: #dcfce7; color: #15803d; }}
  .cat-m  {{ background: #fef9c3; color: #92400e; }}
  .cat-l  {{ background: #fee2e2; color: #991b1b; }}
  .case-title-block {{ flex: 1; min-width: 0; }}
  .case-title {{ font-weight: 600; font-size: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .meta-tags {{ display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px; }}
  .meta-tag {{ font-size: 11px; color: #475569; background: #f8fafc; border: 1px solid #e2e8f0; padding: 2px 8px; border-radius: 4px; }}
  .tag-red    {{ background: #fee2e2; border-color: #fca5a5; color: #991b1b; }}
  .tag-orange {{ background: #fef9c3; border-color: #fde68a; color: #92400e; }}
  .case-summary {{ font-size: 12px; color: #475569; margin-top: 3px; font-style: italic; }}
  .collibra-link:hover {{ background: #dbeafe; }}
  .chevron {{ font-size: 12px; color: #94a3b8; transition: transform 0.2s; flex-shrink: 0; }}
  .case-card.open .chevron {{ transform: rotate(90deg); }}

  /* BODY */
  .case-body {{ display: none; padding: 0 20px 20px; border-top: 1px solid #f1f5f9; }}
  .case-card.open .case-body {{ display: block; }}
  .body-section {{ margin-top: 16px; }}
  .body-section-title {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; color: #374151; margin-bottom: 8px; }}

  /* FINDINGS */
  .finding-group {{ margin-bottom: 10px; }}
  .finding-group-title {{ font-size: 11px; font-weight: 700; text-transform: uppercase; margin-bottom: 4px; }}
  .open-title {{ color: #92400e; }}
  .finding-item {{ font-size: 13px; padding: 6px 12px; border-radius: 6px; margin-bottom: 4px; }}
  .finding-open {{ background: #fef9c3; border-left: 3px solid #f59e0b; color: #92400e; }}
  .finding-ok   {{ background: #dcfce7; border-left: 3px solid #22c55e; color: #15803d; }}

  /* 2-col grid */
  .info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 16px; }}
  @media (max-width: 700px) {{ .info-grid {{ grid-template-columns: 1fr; }} }}
  .info-card {{ border-radius: 8px; padding: 14px; }}
  .info-card-blue   {{ border: 1.5px solid #3b82f6; background: #eff6ff; }}
  .info-card-purple {{ border: 1.5px solid #8b5cf6; background: #f5f3ff; }}
  .info-card h4 {{ font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: 10px; }}
  .info-card-blue h4   {{ color: #1d4ed8; }}
  .info-card-purple h4 {{ color: #6d28d9; }}

  /* ATTRIBUTE TABLE */
  .attr-table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
  .attr-table .attr-key {{ font-weight: 600; color: #374151; padding: 4px 8px 4px 0; vertical-align: top; width: 45%; }}
  .attr-table .attr-val {{ color: #1e293b; padding: 4px 0; vertical-align: top; }}
  .attr-table tr + tr td {{ border-top: 1px solid #e0e7ef; }}
  .attr-table .attr-missing .attr-key,
  .attr-table .attr-missing .attr-val {{ background: #fee2e2; }}
  .attr-table .empty {{ color: #94a3b8; }}
  .attr-richtext {{ font-size: 12px; color: #1e293b; line-height: 1.5; }}
  .attr-richtext p {{ margin: 0 0 4px 0; }}
  .attr-richtext b, .attr-richtext strong {{ font-weight: 600; }}

  /* FILTER BUTTONS */
  .filter-bar {{ padding: 12px 32px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; border-bottom: 1px solid #e2e8f0; background: #fff; }}
  .filter-label {{ font-size: 12px; font-weight: 700; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-right: 4px; }}
  .filter-btn {{ padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; border: 1.5px solid #e2e8f0; background: #fff; color: #475569; cursor: pointer; transition: all 0.15s; }}
  .filter-btn:hover {{ border-color: #94a3b8; background: #f8fafc; }}
  .filter-btn.active {{ background: #1a1a2e; color: #fff; border-color: #1a1a2e; }}

  /* COMMENTS */
  .comment-item {{ margin-bottom: 10px; }}
  .comment-meta {{ font-size: 11px; color: #64748b; margin-bottom: 3px; }}
  .comment-text {{ font-size: 12px; color: #1e293b; background: #f8fafc; border-left: 3px solid #8b5cf6; padding: 6px 10px; border-radius: 4px; white-space: pre-wrap; }}
</style>
</head>
<body>

<div class="header">
  <div class="header-left">
    <h1>Purpose of Use — Review Bericht</h1>
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
  <button class="filter-btn" onclick="setFilter(this, 'data downloading')">Data Download / PET / Löschkonzept</button>
  <button class="filter-btn" onclick="setFilter(this, 'german employee')">German Employee / LVK</button>
  <button class="filter-btn" onclick="setFilter(this, 'authorization')">Authorization</button>
  <button class="filter-btn" onclick="setFilter(this, 'pflichtfeld')">Pflichtfeld leer</button>
  <button class="filter-btn" onclick="setFilter(this, 'user group')">User Group vage</button>
  <button class="filter-btn" onclick="setFilter(this, 'kurz')">Beschreibung kurz</button>
</div>

{cards_html if cards_html else '<p style="color:#999;padding:24px 32px;">Keine Cases mit Status &quot;In Review By Domain&quot; gefunden.</p>'}

<div style="height:40px;"></div>

<script>
let activeFilter = '';

function toggleCase(header) {{
  header.parentElement.classList.toggle("open");
}}

function setFilter(btn, keyword) {{
  activeFilter = keyword;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}

function filterCases() {{
  applyFilters();
}}

function applyFilters() {{
  const q = document.getElementById("searchInput").value.toLowerCase();
  document.querySelectorAll(".case-card").forEach(card => {{
    const searchText = (card.dataset.search + " " + card.innerText).toLowerCase();
    const findingsText = (card.dataset.findings || "").toLowerCase();
    const matchSearch  = q === '' || searchText.includes(q);
    const matchFilter  = activeFilter === '' || findingsText.includes(activeFilter);
    card.style.display = (matchSearch && matchFilter) ? "" : "none";
  }});
}}
</script>
</body>
</html>'''


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print("=== Collibra Purpose of Use – Review Tool ===\n")

    session = build_session()

    # Verbindung testen
    test = session.get(f"{COLLIBRA_HOST}/rest/2.0/users/current")
    if test.status_code == 401:
        print("FEHLER: Session abgelaufen (401).")
        print("Bitte neue JSESSIONID aus Edge DevTools (F12 > Console > document.cookie) holen.")
        sys.exit(1)
    elif test.status_code != 200:
        print(f"FEHLER: API nicht erreichbar (Status {test.status_code}).")
        sys.exit(1)

    user = test.json().get("userName", "unbekannt")
    print(f"Eingeloggt als: {user}\n")

    # Assets pro Status abrufen (ohne Kommentare)
    def load_group(status):
        print(f"Lade '{status}'-Cases...")
        assets = get_assets_by_status(session, status)
        print(f"  -> {len(assets)} Cases gefunden")
        cases = []
        for i, asset in enumerate(assets, 1):
            aid  = asset["id"]
            name = asset.get("name", aid)
            print(f"  [{i}/{len(assets)}] {name}")
            attrs = get_attributes(session, aid)
            cases.append({"asset": asset, "attributes": attrs})
        return cases

    in_review_cases = load_group(STATUS_IN_REVIEW)

    print("\nErstelle HTML-Bericht...")
    html = build_report(in_review_cases)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nBericht gespeichert: {REPORT_PATH}")
    print("Bitte im Browser oeffnen.")
    print("\nFertig!")


if __name__ == "__main__":
    main()
