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

```bash
cp .env.example .env
# .env ausfüllen: PHOTOPRISM_URL, PHOTOPRISM_CLIENT_ID/SECRET, MISTRAL_API_KEY
docker compose up -d --build
```

PhotoPrism-Zugangsdaten: Lege unter **Settings → Applications** in
PhotoPrism einen OAuth-Client an (Scopes: `photos`, `metadata`, `download`)
und trage `PHOTOPRISM_CLIENT_ID`/`PHOTOPRISM_CLIENT_SECRET` ein. Alternativ
funktioniert auch `PHOTOPRISM_USERNAME`/`PHOTOPRISM_PASSWORD`.

Mistral-API-Key: [console.mistral.ai](https://console.mistral.ai/).

### Lokal ohne Docker

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python -m pp_mistral.main --once --dry-run
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
