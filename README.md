# Collibra Tools

Interne SAP-Tools rund um Collibra (Purpose of Use Assets).

---

## MARCO
**Metadata Audit and Review for Compliance Operations**

Automatisierte Vorprüfung von *Purpose of Use*-Cases bevor sie an den Betriebsrat weitergeleitet werden.

**Starten:**
```
MARCO\marco.bat
```

Lädt alle Cases mit Status **"In Review By Domain"** aus Collibra, prüft sie regelbasiert gegen Betriebsrats-Anforderungen und erstellt einen interaktiven HTML-Bericht (`review_report.html`).

**Was wird geprüft:**
- Pflichtfelder ausgefüllt (Purpose, Beschreibung, Authorization, User Group, Domain)
- Boolean-Felder explizit gesetzt (Download, Forwarding, Personenbezug usw.)
- Bei Data Downloading = Ja: PET-Eintrag vorhanden, Löschkonzept beschrieben, Zweck erklärt
- Bei German Employee Data = Ja: LVK-Schutzkonzept beschrieben
- Authorization verständlich (kein reiner Rollencode, Antragsprozess beschrieben)
- User Group konkret (nicht nur "colleagues" oder "employees")

Die Regeln wurden aus **242 echten Betriebsrats-Kommentaren** abgeleitet.

---

## PurposeOfUseExport

Export aller **Approved** Purpose-of-Use-Cases als HTML-Dateien und kombinierte PDF.

**Starten:**
```
PurposeOfUseExport\export.bat
```

Erstellt je eine HTML-Datei pro Case in `PurposeOfUseExport\PurposeOfUse_HTML\` und eine kombinierte `Purpose of Use.pdf`.

---

## Authentifizierung

Beide Tools nutzen eine **JSESSIONID** aus dem Edge-Browser (SSO).

**JSESSIONID holen:**
1. Edge öffnen, bei `https://sap.collibra.com` einloggen
2. `F12` → Tab **Console** → `document.cookie` → Enter
3. `JSESSIONID=xxxx-...` kopieren
4. Im jeweiligen Skript bei `JSESSIONID = "DEINE-JSESSIONID-HIER"` eintragen

Bei **401-Fehler** → JSESSIONID abgelaufen, erneuern wie oben.

---

## Voraussetzungen

- Python 3.x (Aufruf mit `py`)
- `pip install requests reportlab`

