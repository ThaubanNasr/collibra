# Collibra Tools

Interne SAP-Tools rund um Collibra (Purpose of Use Assets).

---

## Für Kollegen — Schnellstart

### 1. Repo klonen
```
git clone https://github.com/ThaubanNasr/collibra.git
```

### 2. Konfigurationsdatei anlegen
Die Datei `MARCO\marco_config.example.py` kopieren und als `MARCO\marco_config.py` speichern.  
Dann zwei Werte eintragen:

```python
JSESSIONID = "xxxx-xxxx-xxxx"   # aus Collibra (siehe unten)
AI_API_KEY  = "xxxx-xxxx-xxxx"  # aus dem Hyperspace AI Proxy
```

### 3. JSESSIONID und AI_API_KEY holen

**JSESSIONID** (aus Collibra):
1. Edge öffnen, bei `https://sap.collibra.com` einloggen
2. **`Strg + Shift + I`** → Tab **Console**
3. `document.cookie` eingeben → Enter
4. Den Wert `JSESSIONID=xxxx-xxxx-...` kopieren und in `marco_config.py` eintragen

Bei **401-Fehler** → JSESSIONID abgelaufen, einfach neu holen (Schritt 2–4 wiederholen).

**AI_API_KEY** (aus dem Hyperspace Hai Proxy):
- Das Hai Proxy Tray-Icon in der Windows-Taskleiste öffnen
- Den API Key dort kopieren und in `marco_config.py` eintragen
- Der Proxy muss laufen wenn MARCO gestartet wird

### 4. Starten
```
MARCO\marco.bat
```
Nach dem Durchlauf liegt der Bericht als `marco_DATUM.html` im `MARCO\`-Ordner — Datei im Browser öffnen.

---

## MARCO
**Metadata Audit and Review for Compliance Operations**

Automatisierte Vorprüfung von *Purpose of Use*-Cases bevor sie an den Betriebsrat weitergeleitet werden.

Lädt alle Cases mit Status **"In Review By Domain"** aus Collibra, bewertet sie mit Claude (SAP AI Proxy) und erstellt einen interaktiven HTML-Bericht.

**Was wird geprüft:**
- Pflichtfelder ausgefüllt (Purpose, Beschreibung, Authorization, User Group, Domain)
- Boolean-Felder explizit gesetzt (Download, Forwarding, Personenbezug usw.)
- Bei Data Downloading = Ja: PET-Eintrag vorhanden, Löschkonzept beschrieben, Zweck erklärt
- Bei German Employee Data = Ja: LVK-Schutzkonzept beschrieben
- Authorization verständlich (kein reiner Rollencode, Antragsprozess beschrieben)
- User Group konkret (nicht nur "colleagues" oder "employees")

---

## PurposeOfUseExport

Export aller **Approved** Purpose-of-Use-Cases als HTML-Dateien und kombinierte PDF.

**Starten:**
```
PurposeOfUseExport\export.bat
```

Erstellt je eine HTML-Datei pro Case in `PurposeOfUseExport\PurposeOfUse_HTML\` und eine kombinierte `Purpose of Use.pdf`.

---

## Voraussetzungen

- Python 3.x (Aufruf mit `py`)
- `pip install requests reportlab`

