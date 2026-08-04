# Collibra Tools — MARCO & PurposeOfUseExport

## Verzeichnisstruktur

```
Collibra/
├── MARCO/                          ← Review-Tool (In Review By Domain)
│   ├── marco.py                    ← Hauptskript
│   ├── marco.bat                   ← Starter
│   ├── marco_config.py             ← Konfiguration (nicht im Git, lokal anlegen)
│   ├── marco_config.example.py     ← Vorlage für Kollegen
│   └── knowledge_base_distilled.json ← Destillierte Wissensbasis für Claude
│
├── PurposeOfUseExport/             ← Export aller Approved Cases als HTML + PDF
│   ├── download_purpose_of_use.py
│   └── export.bat
│
├── README.md
└── .gitignore
```

---

## MARCO — Wie es funktioniert

**MARCO** (Metadata Audit and Review for Compliance Operations) bewertet alle
"In Review By Domain"-Cases vor dem Gang zum Betriebsrat.

### Ablauf

1. Python lädt alle Cases mit Status **"In Review By Domain"** aus Collibra via REST API
2. Pro Case werden alle 12 Felder (Purpose, Beschreibung, Authorization usw.) an **Claude** geschickt
3. Claude kennt die Betriebsrats-Anforderungen aus dem System-Prompt + Wissensbasis und gibt strukturiertes JSON zurück (`findings` + `summary`)
4. Python baut daraus den **HTML-Report** (`marco_DATUM.html`)

### Wissensbasis (`knowledge_base_distilled.json`)

Wurde einmalig aus **682 echten Betriebsrats-Kommentaren** (Rejected, Information Required, Approved) destilliert:
- Häufige Ablehnungsgründe
- Typische Mängel
- Beispiele was bei genehmigten Cases gut war
- Wichtige Hinweise aus dem Prozess

Claude liest diese Wissensbasis bei jedem Case-Aufruf als Teil des System-Prompts.

### Konfiguration (`marco_config.py`)

```python
JSESSIONID = "xxxx-xxxx-xxxx"   # aus Collibra (Strg+Shift+I → Console → document.cookie)
AI_API_KEY  = "xxxx-xxxx-xxxx"  # aus dem Hyperspace AI Proxy (Hai)
AI_BASE_URL = "http://localhost:6655"
AI_MODEL    = "claude-sonnet-4-6"
```

**Starten:** `MARCO\marco.bat`

### Collibra API

| Was | Wert |
|---|---|
| Host | `https://sap.collibra.com` |
| Asset-Typ | `PurposeOfUse_C` |
| Status | `In Review By Domain` |
| Assets-Endpunkt | `/rest/2.0/assets` |
| Attribute-Endpunkt | `/rest/2.0/attributes?assetId=<id>` |
| Auth-Test | `/rest/2.0/users/current` |

### SAP AI Proxy (Hai)

| Was | Wert |
|---|---|
| Base URL | `http://localhost:6655` |
| Endpunkt | `/anthropic/v1/messages` |
| Auth | `x-api-key` Header |
| Modell | `claude-sonnet-4-6` |

### HTML-Bericht

- Eine **Card pro Case**, aufklappbar
- Badge `!` (gelb) = offene Punkte, `OK` (grün) = vollständig
- **Sortierung:** Offen-Cases zuerst
- **Filter-Buttons:** PET, LVK, Authorization, Pflichtfeld, User Group
- **Suchfeld** nach Case-Name
- **Direktlink** zum Asset in Collibra
- **Personenbezug-Tags:** rot = direkter Bezug/Leistungskontrolle, orange = indirekter Bezug/German Employee Data

### Felder die geprüft werden

**Pflichtfelder** (müssen ausgefüllt sein):
Purpose, Beschreibung, Authorization, Authorization (German), User Group, Domain

**Boolean-Felder** (müssen Ja oder Nein sein):
Data Downloading Allowed, Data Forwarding Allowed, Contains direct Personal Data,
Contains indirect Personal Data, German Employee Data, Intends Performance Control

### Technischer Stack

- Python 3.14 (Aufruf mit `py`)
- `requests` für Collibra API + AI Proxy
- Kein `anthropic`-Paket nötig — direkte HTTP-Requests an den Hai Proxy

---

## PurposeOfUseExport — Wie es funktioniert

Lädt die originale `Purpose of Use.html`-Attachment jedes **Approved**-Cases aus Collibra herunter,
benennt sie nach dem Asset-Namen um und fügt alle zu einer PDF zusammen.

**Starten:** `PurposeOfUseExport\export.bat`

Konfiguration: `JSESSIONID` direkt in `download_purpose_of_use.py` eintragen.

**Technischer Stack:** `requests`, `reportlab`
(WeasyPrint nicht nutzbar auf diesem Windows — fehlt `libgobject`)

---

## Authentifizierung (JSESSIONID)

Collibra nutzt SSO — kein Passwort möglich.

**JSESSIONID holen:**
1. Edge öffnen, bei `https://sap.collibra.com` einloggen
2. **Strg + Shift + I** → Tab **Console**
3. `document.cookie` → Enter
4. `JSESSIONID=xxxx-...` kopieren

Bei **401-Fehler** → JSESSIONID abgelaufen, neu holen.

---

## Workflow / Status-Übersicht

| Status | Bedeutung |
|---|---|
| `In Review By Domain` | MARCO prüft diese Cases |
| `Approved` | Genehmigt |
| `Rejected` | Abgelehnt |
| `Information Required` | Mängel — Kommentare zeigen was fehlt |
| `In Review By Works Council` | Bereits beim Betriebsrat |
| `Preliminarily Approved` | Vorläufig genehmigt |
