# Collibra – Purpose of Use Downloader

## Use Case

In Collibra (SAP-Instanz: https://sap.collibra.com) gibt es Assets vom Typ **"Purpose Of Use"**.
Der Inhalt steckt **nicht** als Dateianhang, sondern als **Attribute** direkt im Asset (z.B. Purpose, Authorization, Beschreibung usw.).

### Ziel

1. Alle **Approved** "Purpose Of Use"-Assets aus Collibra abrufen (REST API).
2. Die Attribute jedes Assets auslesen und als **HTML-Datei** speichern — benannt nach dem **Asset-Titel**.
3. Alle HTML-Dateien in `PurposeOfUse_HTML\` ablegen.
4. Alle HTML-Dateien zu einer einzigen **`Purpose of Use.pdf`** zusammenführen.

## Dateien

| Datei/Ordner | Beschreibung |
|---|---|
| `download_purpose_of_use.py` | Hauptskript: API-Abruf + HTML-Erstellung + PDF |
| `PurposeOfUse_HTML\` | Zielordner — je eine HTML-Datei pro Asset (336 Stück) |
| `Purpose of Use.pdf` | Kombinierte PDF aller Approved Cases |

## Authentifizierung

- Collibra nutzt **SSO** — kein Benutzername/Passwort möglich, kein Basic Auth.
- Die Session läuft über eine **JSESSIONID** aus dem Edge-Browser.
- Die JSESSIONID steht hart im Skript (Zeile mit `JSESSIONID = "..."`).

### JSESSIONID erneuern (wenn 401-Fehler)

1. Edge öffnen, bei `https://sap.collibra.com` einloggen
2. `F12` → Tab **Console** → eingeben: `document.cookie` → Enter
3. Aus der Ausgabe `JSESSIONID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` kopieren
4. Im Skript `download_purpose_of_use.py` Zeile `JSESSIONID = "..."` aktualisieren

**Benutzer:** `tareq.daoud-ghadieh@sap.com`

## Collibra API — wichtige Details

| Was | Wert |
|---|---|
| Host | `https://sap.collibra.com` |
| Asset-Typ `publicId` | `PurposeOfUse_C` (nicht "Purpose Of Use"!) |
| Status-Filter | `Approved` |
| Benutzer-Endpunkt | `/rest/2.0/users/current` |
| Assets-Endpunkt | `/rest/2.0/assets` |
| Attribute-Endpunkt | `/rest/2.0/attributes?assetId=<id>` |
| Auth-Test | `/rest/2.0/auth/current` → gibt 404, stattdessen `/rest/2.0/users/current` nutzen |

## Attribute im Asset (Reihenfolge in der HTML/PDF)

1. Purpose
2. Beschreibung
3. Authorization
4. Authorization (German)
5. User Group
6. Domain
7. Data Downloading Allowed
8. Data Forwarding Allowed
9. Contains direct Personal Data
10. Contains indirect Personal Data
11. German Employee Data
12. Intends Performance Control

## Technischer Stack

- **Python:** 3.14 (Aufruf mit `py`, nicht `python`)
- **PDF-Erstellung:** `reportlab` (WeasyPrint funktioniert auf diesem Windows nicht — fehlt `libgobject`)
- **Pakete:** `requests`, `reportlab`
- Installiert unter: `C:\Users\I777951\AppData\Local\Python\pythoncore-3.14-64\`

## Skript ausführen

```
py "C:\Users\I777951\WoCCo\Collibra\download_purpose_of_use.py"
```

Bei 401-Fehler → JSESSIONID erneuern (siehe oben).

## Ablauf des Skripts

1. Session mit JSESSIONID aufbauen, Login via `/rest/2.0/users/current` prüfen
2. Alle Approved `PurposeOfUse_C`-Assets seitenweise laden (50 pro Request)
3. Für jedes Asset: Attribute abrufen → HTML-Datei erstellen → in `PurposeOfUse_HTML\` speichern
4. Alle HTML-Dateien mit `reportlab` zu `Purpose of Use.pdf` zusammenführen

---

# Collibra – Purpose of Use Review Tool

## Use Case

Vor dem Gang zum Betriebsrat werden alle Cases mit Status **"In Review By Domain"** automatisch bewertet.
Das Tool prüft ob Informationen fehlen, Personenbezug korrekt gekennzeichnet ist, und ob der Case inhaltlich vollständig wirkt.

## Workflow / Status-Übersicht

| Status | Bedeutung |
|---|---|
| `In Review By Domain` | Wir prüfen den Case — Ziel dieses Tools |
| `Approved` | Gute Beispiele — vollständige, korrekte Cases |
| `Rejected` | Schlechte Beispiele — dürfen nicht genutzt werden |
| `Information Required` | Mängel wurden festgestellt — Kommentare zeigen was fehlt |
| `In Review By Works Council` | Bereits beim Betriebsrat |
| `Preliminarily Approved` | Vorläufig genehmigt |

## Dateien

| Datei | Beschreibung |
|---|---|
| `review_tool.py` | Hauptskript: API-Abruf + Bewertung + HTML-Bericht |
| `review_report.html` | Ausgabe: Bericht aller "In Review By Domain"-Cases |
| `review_knowledge_base.json` | Wissensbasis: Kommentare aus Rejected + Info Required |

## Skript ausführen

```
py "C:\Users\I777951\WoCCo\Collibra\review_tool.py"
```

## Collibra API — Besonderheiten

| Was | Wert |
|---|---|
| Status-Namen | Exakt: `In Review By Domain`, `Approved`, `Rejected`, `Information Required` (Groß/Kleinschreibung!) |
| Kommentar-Endpunkt | `/rest/2.0/comments` — ignoriert `assetId`-Parameter, gibt ALLE ~8892 Kommentare zurück |
| Kommentar-Zuordnung | Über `baseResource.id` im Kommentar-Objekt filtern (nicht über API-Parameter) |
| System-Kommentare | `"system": true` → überspringen (automatisch generierte Workflow-Nachrichten) |

## Ablauf des Review Tools

1. Session aufbauen, Login prüfen
2. Alle 4 Status-Gruppen laden (Assets + Attribute, keine Kommentare pro Asset)
3. Alle Kommentare **einmalig** laden (`limit=500`, paginiert) → Index `asset_id → [kommentare]` aufbauen
4. Wissensbasis aus Rejected + Information Required Kommentaren erstellen → `review_knowledge_base.json`
5. Jeden "In Review By Domain"-Case regelbasiert bewerten
6. HTML-Bericht generieren

## Bewertungsregeln

### Pflichtfelder (Fehler wenn leer)
- Purpose
- Beschreibung
- Authorization
- Authorization (German)
- User Group
- Domain

### Boolean-Felder (Fehler wenn nicht gesetzt)
- Data Downloading Allowed
- Data Forwarding Allowed
- Contains direct Personal Data
- Contains indirect Personal Data
- German Employee Data
- Intends Performance Control

### Logik-Regeln

**Personenbezug**
- Personenbezug (direkt oder indirekt = Ja) → German Employee Data und Intends Performance Control müssen explizit gesetzt sein (Warnung)
- German Employee Data = Ja → Intends Performance Control **muss** angegeben sein (Fehler)
- German Employee Data = Ja → Purpose/Beschreibung muss erläutern wie LVK (Leistungs- und Verhaltenskontrolle) verhindert wird — Keywords: "leistung", "lvk", "performance control", "verhaltenskontrolle" (Warnung)
- Intends Performance Control = Ja → Purpose muss erläutern dass nur direkte Vorgesetzte Einzeldaten sehen, höhere Ebenen nur aggregierte Daten (Warnung)

**Data Download & Forwarding**
- Data Downloading = Ja → **PET-Eintrag zwingend erforderlich** — muss im Purpose/Beschreibung erwähnt sein, Keywords: "pet", "pet entry", "pet-eintrag", "privacy exception" (Fehler)
- Data Downloading = Ja + PET vorhanden → **Löschkonzept zwingend erforderlich** — wird nur geprüft wenn PET gefunden wurde (ohne PET erübrigt sich die Prüfung), Keywords: "lösch", "löschkonzept", "retention", "aufbewahrung", "delete", "deletion", "frist", "archiv" (Fehler) — 30x in Wissensbasis
- Data Downloading = Ja → Zweck des Downloads muss beschrieben sein — Keywords: "download", "herunterladen", "export", "backup", "präsentation", "offline", "audit" (Warnung)
- Data Forwarding = Ja → Zweck der Datenweitergabe muss beschrieben sein — Keywords: "weiterleitung", "forwarding", "weitergabe", "teilen", "external", "dritte" (Warnung)

**Authorization**
- Authorization sehr kurz (< 20 Zeichen) → wahrscheinlich nur Rollenname ohne Erklärung (Warnung)
- Authorization beschreibt nicht wie Zugriff beantragt wird — Keywords: `request`, `beantragen`, `arm`, `shop`, `bereich`, `space`, `antrag`, `approval`, `raise`, `role`, `rolle`, `zugriff`, `access`, `zauth`, `permission`, `berechtigung`, `t.yx0` (Warnung wenn kein einziges Keyword vorkommt)
- Hintergrund: Viele Cases schreiben nur den Rollennamen (z.B. `ZAUTH CRMS:06`) ohne zu erklären wie Benutzer den Zugriff beantragen. Das ist nicht ausreichend. Cases mit ARM-Prozess, Shop-Link oder ähnlichem sind in Ordnung.
- Authorization (German) fehlt obwohl Authorization (English) vorhanden (Warnung)

**User Group**
- User Group zu vage (z.B. nur "colleagues", "mitarbeiter", "employees", "users") → konkrete Rollen benennen (Warnung)
- User Group sehr kurz (< 10 Zeichen) (Warnung)

**Textqualität**
- Purpose < 50 Zeichen → Warnung (zu kurz)
- Beschreibung < 80 Zeichen → Warnung (zu kurz)

### Wissensbasis (aus Rejected + Info Required Kommentaren)
- Alle Kommentare von Rejected- und Information-Required-Cases werden einmalig geladen
- Bestätigungs-Kommentare werden gefiltert: "i hereby confirm", "looks good", "automatically generated", "good to go", "technischer check", "zugestimmt bis"
- Ergebnis: `review_knowledge_base.json` mit 351 Einträgen — dient als Referenz für zukünftige Regelverbesserungen

### Häufige Ablehnungsgründe (aus Wissensbasis abgeleitet)
- Berechtigungen nur als Rollencode (z.B. "CRMS06") ohne Erklärung was das bedeutet
- LVK-Möglichkeit erkannt aber kein Schutzkonzept beschrieben
- Data Download erlaubt aber kein PET-Eintrag vorhanden
- Personenbezug-Felder falsch/unvollständig — z.B. Opportunity ID oder Profit Center als indirekter MA-Bezug nicht gekennzeichnet
- Feldliste im PoU stimmt nicht mit tatsächlichen Feldern überein
- User Group zu vage ("colleagues" nicht ausreichend)

### Verdict-Stufen
| Stufe | Zeichen | Farbe | Bedeutung |
|---|---|---|---|
| Offen | `!` | gelb | Es gibt Punkte die noch ergänzt oder geprüft werden müssen |
| OK | `OK` | grün | Alles vollständig, keine offenen Punkte |

Es gibt **keine Unterscheidung** mehr zwischen Fehler und Warnung — alle Prüfpunkte sind gleichwertig und werden unter **"Zu ergänzen / prüfen"** angezeigt. Ziel ist dass der Bearbeiter weiß was noch fehlt oder geklärt werden muss, nicht eine Gewichtung.

### Attribut-Darstellung in der HTML
- Attributwerte kommen aus der API als **roher HTML-Code** (Collibra Rich-Text-Editor: `<p>`, `<span style="...">`, `<b>` etc.)
- Felder die mit `<` beginnen → direkt als HTML rendern (`<div class="attr-richtext">`) — sieht dann genauso aus wie in Collibra
- Felder ohne HTML (Boolean, kurze Strings) → als Plaintext anzeigen
- Für die **Bewertungslogik** (Keyword-Suche in `evaluate_case`) weiterhin `strip_html()` verwenden — sonst matchen Keywords nicht

## Filter-Leiste im HTML-Bericht

Oberhalb der Cards gibt es Filter-Buttons die Cases nach Problemtyp filtern. Filter und Suchfeld funktionieren kombiniert. Die Filterung läuft über das `data-findings`-Attribut jeder Card (enthält alle Meldungstexte in Kleinschreibung).

| Button | Keyword-Suche in data-findings | Bedeutung |
|---|---|---|
| Alle | — | Alle Cases anzeigen |
| Data Download / PET / Löschkonzept | `data downloading` | Download erlaubt aber PET-Eintrag, Löschkonzept oder Zweck fehlt |
| German Employee / LVK | `german employee` | German Employee = Ja aber LVK-Schutz nicht erklärt |
| Authorization | `authorization` | Unklare oder fehlende Authorization-Beschreibung |
| Pflichtfeld leer | `pflichtfeld` | Mindestens ein Pflichtfeld ist leer |
| User Group vage | `user group` | User Group zu vage beschrieben |
| Beschreibung kurz | `kurz` | Purpose oder Beschreibung zu kurz |

**Hinweis:** Buttons die aktuell keine Cases treffen bleiben trotzdem sichtbar — für zukünftige Cases wenn neue Meldungen dazukommen.

## HTML-Bericht Aufbau (IUCR-Stil)

- **Header:** Dunkler Gradient-Header (`#1a1a2e → #16213e`) mit Badges (Gesamt / Offen / OK / Referenz-Zahlen) + Suchfeld
- **Filter-Leiste:** Buttons zum Filtern nach Problemtyp (siehe oben)
- **Cards:** Eine Card pro Case, aufklappbar per Klick (Chevron dreht sich)
  - **Badge:** `!` (gelb) = Offen, `OK` (grün) = vollständig
  - **1-Satz Zusammenfassung:** Direkt sichtbar ohne aufklappen — z.B. "3 offene Punkte: PET-Eintrag fehlt, LVK nicht erklärt." oder "Alle Felder vollständig — bereit für den Betriebsrat."
  - **Tags:** Personenbezug-Tags (rot = direkter Bezug/Leistungskontrolle, orange = indirekter Bezug/German Employee Data), Domain
  - **Collibra-Link:** Direktlink zum Asset in Collibra
  - **Bewertungs-Block:** Alle Prüfpunkte unter "Zu ergänzen / prüfen" (gelb)
  - **Attribut-Tabelle:** Alle Felder mit originalem Collibra-Inhalt (HTML gerendert), fehlende Pflichtfelder rot hinterlegt
- **Sortierung:** Offen-Cases zuerst, dann OK
- **Kein Kommentar-Abschnitt** in den Cards
- **Kein Fortschrittsbalken** — war immer 12/12 da Boolean-Felder fast immer gesetzt sind, bringt keinen Mehrwert
