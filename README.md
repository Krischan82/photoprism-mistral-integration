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

### Deployment in einem `docker/compose|configs|volumes|logs`-Layout

Wenn du deine Stacks nach dem Schema

```
docker/
  compose/
  configs/
  volumes/
  logs/
```

organisierst, leg diesen Service unter `docker/compose/photoprism-mistral/`
ab:

```bash
mkdir -p docker/compose/photoprism-mistral
git clone -b claude/project-analysis-odx6md \
  https://github.com/Krischan82/photoprism-mistral-integration.git \
  docker/compose/photoprism-mistral
cd docker/compose/photoprism-mistral

cp .env.example .env
# .env ausfüllen (siehe oben) - LOG_DIR steht per Default schon auf
# ../../logs/photoprism-mistral, also docker/logs/photoprism-mistral

mkdir -p ../../logs/photoprism-mistral

docker compose up -d --build
```

`docker-compose.yml` mountet `${LOG_DIR}` nach `/app/logs` im Container und
der Service schreibt zusätzlich zur Konsolenausgabe eine rotierende
Logdatei dorthin (`LOG_FILE=/app/logs/photoprism-mistral.log`, max. 5 MB ×
3 Dateien). Ein eigener Eintrag unter `docker/configs/` oder
`docker/volumes/` ist für dieses (zustandslose) Tool nicht nötig – es
persistiert selbst nichts außer den Logs.

Da PhotoPrism bei dir auf einer **anderen Maschine** im selben Netzwerk
läuft, reicht `PHOTOPRISM_URL=http://<photoprism-host>:2342` in der `.env`.
Der Container läuft standardmäßig mit `network_mode: host` (nur Linux) –
damit hat er dieselbe Netzwerksicht wie der Docker-Host selbst, was LAN-
Erreichbarkeit garantiert und Docker-Bridge/Firewall-Probleme umgeht. Falls
PhotoPrism später als Container auf denselben Docker-Host zieht, kannst du
stattdessen den auskommentierten `networks:`-Block in `docker-compose.yml`
aktivieren und den Netzwerknamen per `docker network ls` nachschlagen.

#### Troubleshooting: "Connection timeout" zu PhotoPrism

Wenn `--random` mit einem Timeout beim Verbinden zu `PHOTOPRISM_URL`
fehlschlägt, ist das (fast immer) kein Bug im Tool, sondern ein
Netzwerk-Problem:

1. Vom **Docker-Host** (nicht aus dem Container) testen:
   `curl -v http://<photoprism-ip>:2342`
2. Funktioniert das, aber der Container kommt trotz `network_mode: host`
   nicht durch: IP/Port in `.env` prüfen, und ob eine Firewall/VPN auf dem
   Host gezielt Docker-Traffic blockt.
3. Funktioniert schon der Host-`curl` nicht: liegt außerhalb von Docker –
   IP/Port falsch, PhotoPrism lauscht nur auf `127.0.0.1` statt `0.0.0.0`,
   oder eine Firewall zwischen den beiden Maschinen blockt generell.

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

Bilder werden über den Thumbnail-Endpunkt (`GET /api/v1/t/:hash/:token/:size`)
geladen, nicht über `photos/:uid/dl` – letzterer verlangt eine eigene
Download-Berechtigung/Scope und lieferte in der Praxis einen 403, obwohl
Login und Foto-Liste einwandfrei funktionierten. Da wir das Bild ohnehin
selbst verkleinern, reicht ein Thumbnail; schlägt das fehl, fällt das Tool
automatisch auf `photos/:uid/dl` zurück.

Falls Updates in deiner PhotoPrism-Version nicht ankommen: `LOG_LEVEL=DEBUG`
setzen und/oder `--dry-run` nutzen, um den generierten Patch zu inspizieren,
und bei Bedarf die Feldnamen in `sync.py` (`_current_description`,
`_current_keywords`, `_has_location`, `build_patch`) an deine Version
anpassen.

## Konfiguration

Siehe [`.env.example`](.env.example) für alle Variablen (Feature-Toggles,
Batch-Größe, Sync-Intervall, `OVERWRITE_EXISTING`, etc.).
