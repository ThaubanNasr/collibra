"""
Collibra - Purpose of Use Downloader
Laedt alle Approved Purpose-of-Use Assets herunter, speichert je eine HTML-Datei
pro Asset (benannt nach dem Asset-Titel) und erstellt eine kombinierte PDF.
"""

import os
import re
import sys
import requests

# ── Konfiguration ─────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR    = os.path.join(BASE_DIR, "PurposeOfUse_HTML")
PDF_OUTPUT    = os.path.join(BASE_DIR, "Purpose of Use.pdf")
COLLIBRA_HOST = "https://sap.collibra.com"

JSESSIONID        = "DEINE-JSESSIONID-HIER"  # Aus Edge: F12 → Console → document.cookie
APPROVED_STATUSES = ["Approved", "Preliminarily Approved"]

# Reihenfolge der Attribute in der HTML-Ausgabe
ATTRIBUTE_ORDER = [
    "Purpose",
    "Beschreibung",
    "Authorization",
    "Authorization (German)",
    "User Group",
    "Domain",
    "Data Downloading Allowed",
    "Data Forwarding Allowed",
    "Contains direct Personal Data",
    "Contains indirect Personal Data",
    "German Employee Data",
    "Intends Performance Control",
]

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── Dateiname bereinigen ──────────────────────────────────────────────────────
def safe_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    return name[:200]


# ── Session aufbauen ──────────────────────────────────────────────────────────
def build_session() -> requests.Session:
    session = requests.Session()
    session.cookies.set("DGC_DISCLAIMER_COOKIE", "true",       domain="sap.collibra.com")
    session.cookies.set("JSESSIONID",            JSESSIONID,   domain="sap.collibra.com")
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept":     "application/json",
    })
    return session


# ── Alle Approved POU-Assets abrufen ─────────────────────────────────────────
def get_approved_pou_assets(session: requests.Session) -> list:
    all_assets = []
    offset = 0
    limit  = 50

    print("Lade alle Purpose-of-Use Assets...")
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

    # Clientseitig nach Status filtern
    filtered = [a for a in all_assets
                if a.get("status", {}).get("name", "") in APPROVED_STATUSES]

    status_counts = {}
    for a in filtered:
        s = a.get("status", {}).get("name", "")
        status_counts[s] = status_counts.get(s, 0) + 1
    for s, c in status_counts.items():
        print(f"  {c:3d} x {s}")
    print(f"\nGesamt: {len(filtered)} Assets (von {len(all_assets)} total).\n")
    return filtered


# ── Attribute eines Assets abrufen ───────────────────────────────────────────
def get_attributes(session: requests.Session, asset_id: str) -> dict:
    resp = session.get(
        f"{COLLIBRA_HOST}/rest/2.0/attributes",
        params={"assetId": asset_id, "limit": 50}
    )
    resp.raise_for_status()
    result = {}
    for attr in resp.json().get("results", []):
        name  = attr["type"]["name"]
        value = attr.get("value", "")
        result[name] = value
    return result


# ── HTML-Seite fuer ein Asset erstellen ──────────────────────────────────────
def build_html(title: str, attributes: dict) -> str:
    rows = ""
    for attr_name in ATTRIBUTE_ORDER:
        if attr_name in attributes:
            value = attributes[attr_name]
            # Boolean-Werte leserlich darstellen
            if isinstance(value, bool):
                value = "Ja" if value else "Nein"
            else:
                value = str(value)
            rows += f"""
            <tr>
                <th>{attr_name}</th>
                <td>{value}</td>
            </tr>"""

    # Restliche Attribute die nicht in ATTRIBUTE_ORDER sind
    for attr_name, value in attributes.items():
        if attr_name not in ATTRIBUTE_ORDER:
            if isinstance(value, bool):
                value = "Ja" if value else "Nein"
            rows += f"""
            <tr>
                <th>{attr_name}</th>
                <td>{value}</td>
            </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: Arial, sans-serif; font-size: 11pt; margin: 30px; }}
  h1   {{ color: #007bff; font-size: 14pt; border-bottom: 2px solid #007bff; padding-bottom: 8px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
  th {{ background: #f0f4ff; text-align: left; padding: 8px 12px; width: 220px;
        border: 1px solid #ccd; font-weight: bold; vertical-align: top; }}
  td {{ padding: 8px 12px; border: 1px solid #ccd; vertical-align: top; }}
</style>
</head>
<body>
<h1>{title}</h1>
<table>{rows}
</table>
</body>
</html>"""


# ── HTML-Text aus Tags bereinigen ─────────────────────────────────────────────
def strip_html(text: str) -> str:
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<li[^>]*>', '• ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&') \
               .replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    return text.strip()


# ── HTML-Dateien zu PDF zusammenfuehren ───────────────────────────────────────
def merge_html_to_pdf(html_files: list, pdf_path: str):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle, PageBreak)
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    print("\nErstelle PDF mit ReportLab...")

    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle("title", parent=styles["Heading1"],
                                 fontSize=13, textColor=colors.HexColor("#007bff"),
                                 spaceAfter=6)
    style_key   = ParagraphStyle("key",   parent=styles["Normal"],
                                 fontSize=9, fontName="Helvetica-Bold")
    style_val   = ParagraphStyle("val",   parent=styles["Normal"],
                                 fontSize=9, leading=12)

    story = []

    for idx, (title, filepath) in enumerate(html_files):
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # Tabellenzeilen aus HTML extrahieren
        rows_raw = re.findall(
            r'<tr[^>]*>.*?<th[^>]*>(.*?)</th>.*?<td[^>]*>(.*?)</td>.*?</tr>',
            content, re.DOTALL | re.IGNORECASE
        )

        story.append(Paragraph(title, style_title))

        if rows_raw:
            table_data = []
            for key_html, val_html in rows_raw:
                key_text = strip_html(key_html)
                val_text = strip_html(val_html)
                # Sehr lange Texte kuerzen damit sie auf eine Seite passen
                if len(val_text) > 2000:
                    val_text = val_text[:2000] + " ..."
                table_data.append([
                    Paragraph(key_text, style_key),
                    Paragraph(val_text, style_val),
                ])

            tbl = Table(table_data, colWidths=[4.5*cm, 12*cm], repeatRows=0, splitByRow=True)
            tbl.setStyle(TableStyle([
                ("BACKGROUND",  (0, 0), (0, -1), colors.HexColor("#f0f4ff")),
                ("GRID",        (0, 0), (-1, -1), 0.5, colors.HexColor("#ccdddd")),
                ("VALIGN",      (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING",  (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",(0,0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(tbl)
        else:
            story.append(Paragraph("(Keine Attribute gefunden)", style_val))

        if idx < len(html_files) - 1:
            story.append(PageBreak())

    doc.build(story)
    print(f"PDF erstellt: {pdf_path}")


# ── Hauptprogramm ─────────────────────────────────────────────────────────────
def main():
    print("=== Collibra Purpose of Use Downloader ===\n")

    session = build_session()

    # Verbindung testen
    test = session.get(f"{COLLIBRA_HOST}/rest/2.0/users/current")
    if test.status_code == 401:
        print("FEHLER: Session abgelaufen (401).")
        print("Bitte neue JSESSIONID aus Edge DevTools (F12 > Console > document.cookie) kopieren")
        print("und im Skript bei JSESSIONID = '...' eintragen.")
        sys.exit(1)
    elif test.status_code != 200:
        print(f"FEHLER: API nicht erreichbar (Status {test.status_code}).")
        sys.exit(1)

    user = test.json().get("userName", "unbekannt")
    print(f"Eingeloggt als: {user}\n")

    # Assets abrufen
    assets = get_approved_pou_assets(session)
    if not assets:
        print("Keine Approved Assets gefunden.")
        sys.exit(0)

    # HTML-Dateien erstellen
    downloaded = []
    errors     = []

    for i, asset in enumerate(assets, 1):
        asset_name = asset.get("name", f"Asset_{i}")
        asset_id   = asset["id"]
        print(f"[{i}/{len(assets)}] {asset_name}")

        try:
            attributes = get_attributes(session, asset_id)
            html_content = build_html(asset_name, attributes)
            filename = safe_filename(asset_name) + ".html"
            filepath = os.path.join(OUTPUT_DIR, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_content)

            print(f"  -> Gespeichert: {filename}")
            downloaded.append((asset_name, filepath))

        except Exception as e:
            print(f"  -> FEHLER: {e}")
            errors.append((asset_name, str(e)))

    # Zusammenfassung
    print(f"\n{'='*50}")
    print(f"Erstellt:    {len(downloaded)} HTML-Dateien")
    print(f"Fehler:      {len(errors)}")
    print(f"Speicherort: {OUTPUT_DIR}")

    if errors:
        print("\nFehler-Liste:")
        for name, err in errors:
            print(f"  - {name}: {err}")

    # PDF erstellen
    if downloaded:
        merge_html_to_pdf(downloaded, PDF_OUTPUT)

    print("\nFertig!")


if __name__ == "__main__":
    main()
