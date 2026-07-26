# photoprism-mistral-integration

AI-gestützte Fotoanreicherung für [PhotoPrism](https://www.photoprism.app/) über
[Mistral AI](https://mistral.ai/)'s Vision-Modelle (Pixtral).

Der Service durchsucht deine PhotoPrism-Bibliothek nach Fotos, denen
Beschreibung, Keywords oder GPS-Koordinaten fehlen, lässt Mistral das Bild
analysieren und schreibt die Ergebnisse zurück nach PhotoPrism.

## Funktionen

- **Automatische Bildbeschreibungen** – 1–2 Sätze Klartext pro Foto.
- **Automatische Keywords/Tags** – 5–12 Stichworte, ergänzt bestehende
  Keywords statt sie zu überschreiben (konfigurierbar).
- **Geolokations-Schätzung** – wenn ein Foto **keine** GPS-Daten hat, prüft
  Mistral, ob im Bild selbst Hinweise auf einen Ort sichtbar sind
  (Wahrzeichen, Beschilderung, Architektur etc.). Nur bei mittlerer/hoher
  Modell-Konfidenz wird der genannte Ort per
  [OpenStreetMap Nominatim](https://nominatim.org/) in echte Koordinaten
  umgewandelt – **die KI liefert nie direkt Koordinaten**, nur einen
  Ortsnamen, der gegen einen echten Geocoding-Dienst validiert wird. Foto­s
  mit geschätztem Standort werden zusätzlich mit dem Keyword
  `ai:location-guess` markiert, damit du sie in PhotoPrism leicht wiederfinden
  und prüfen kannst.
- Bestehende Werte werden standardmäßig **nie überschrieben**
  (`OVERWRITE_EXISTING=false`).
- `--dry-run` zeigt an, was geändert würde, ohne zu schreiben.
- **Bildverkleinerung** – jedes Foto wird vor dem Versand an Mistral auf
  max. `IMAGE_MAX_DIMENSION` Pixel (längste Kante, Standard 1024) verkleinert
  und als JPEG re-encodiert, um Tokens/Kosten zu sparen.
- **Laufend neue Fotos**: Der Dauerbetrieb (`docker compose up -d`, kein
  `--once`) prüft alle `SYNC_INTERVAL_SECONDS` (Standard 1h) die Bibliothek
  und verarbeitet alles, was noch Beschreibung/Keywords/Standort vermissen
  lässt – das schließt neu hinzugefügte Fotos automatisch mit ein, ohne
  dass eine gesonderte "neu"-Erkennung nötig ist.

## Architektur

```
src/pp_mistral/
  config.py            Einstellungen aus Umgebungsvariablen
  photoprism_client.py Minimaler REST-Client für PhotoPrism
  mistral_client.py    Mistral Vision Chat-Completions-Client
  geocode.py            Ortsname -> Koordinaten via Nominatim
  sync.py               Orchestrierung: welche Fotos, welcher Patch
  main.py               CLI-Einstiegspunkt (einmalig oder Dauerbetrieb)
```

## Setup

> Alle Zugangsdaten (PhotoPrism-URL/-Credentials, Mistral-API-Key) gehören
> in eine **lokale** `.env`-Datei auf dem Rechner, auf dem du diesen
> Container startest – nicht in einen Chat oder ins Repo committen.

```bash
cp .env.example .env
```

`.env` ausfüllen:

- `PHOTOPRISM_URL` – z.B. `http://192.168.1.50:2342` (IP/Hostname + Port
  deiner PhotoPrism-Instanz im lokalen Netz).
- `PHOTOPRISM_CLIENT_ID` / `PHOTOPRISM_CLIENT_SECRET` – erstelle dazu in
  PhotoPrism unter **Settings → Applications** einen OAuth-Client mit den
  Scopes `photos`, `metadata`, `download`. Alternativ geht auch
  `PHOTOPRISM_USERNAME`/`PHOTOPRISM_PASSWORD`.
- `MISTRAL_API_KEY` – von [console.mistral.ai](https://console.mistral.ai/).

```bash
docker compose up -d --build
```

### Testen mit einem Zufallsfoto

Bevor du das Tool auf die ganze Bibliothek loslässt, kannst du gezielt ein
einzelnes zufälliges Foto testen:

```bash
docker compose run --rm photoprism-mistral python -m pp_mistral.main --random
```

Das lädt ein zufälliges Foto, verkleinert es, schickt es an Mistral und
druckt Beschreibung/Keywords/Standort-Vermutung sowie die aktuellen
PhotoPrism-Werte – **ohne** etwas zu speichern. Erst mit `--write` wird das
Ergebnis tatsächlich in PhotoPrism gespeichert:

```bash
docker compose run --rm photoprism-mistral python -m pp_mistral.main --random --write
```

### Lokal ohne Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m pp_mistral.main --random
```

### Tests

```bash
pip install pytest
pytest
```

## Wichtiger Hinweis zur PhotoPrism-API

PhotoPrism veröffentlicht keine stabile, versionierte API-Spezifikation.
Dieses Projekt nutzt die Endpunkte `GET/PUT /api/v1/photos/:uid`,
`GET /api/v1/photos` (Liste) und `GET /api/v1/photos/:uid/dl` (Vorschau) sowie
`POST /api/v1/oauth/token` bzw. `POST /api/v1/session` zur Authentifizierung.
Updates erfolgen bewusst per **Read-Modify-Write** (ganzen Datensatz holen,
Feld ändern, ganzen Datensatz zurückschreiben) statt per angenommenem
Partial-Update-Schema – das ist robuster gegenüber Versionsunterschieden,
weil unbekannte Zusatzfelder vom Server ignoriert werden.

Falls Updates in deiner PhotoPrism-Version nicht ankommen: `LOG_LEVEL=DEBUG`
setzen und/oder `--dry-run` nutzen, um den generierten Patch zu inspizieren,
und bei Bedarf die Feldnamen in `sync.py` (`_current_description`,
`_current_keywords`, `_has_location`, `build_patch`) an deine Version
anpassen.

## Konfiguration

Siehe [`.env.example`](.env.example) für alle Variablen (Feature-Toggles,
Batch-Größe, Sync-Intervall, `OVERWRITE_EXISTING`, etc.).
