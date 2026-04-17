# Tonado Architektur

## Überblick

Tonado folgt einer **Service-Architektur**: Unabhängige Python-Services kommunizieren über einen internen Event-Bus. Das Frontend ist eine statische PWA, die über REST und WebSocket mit dem Backend spricht.

```
                 SMARTPHONE (Browser/PWA)
                 +---------------------------+
                 |  Tonado Web-App            |
                 |  Svelte 5 + Tailwind       |
                 |  Mobile-First, Offline-PWA |
                 +-------------+-------------+
                               |
                    REST API   |   WebSocket (Echtzeit)
                               |
                 +-------------v-------------+
                 |         Nginx              |
                 |  Static Files + Reverse    |
                 |  Proxy + WebSocket Upgrade |
                 +-------------+-------------+
                               |
                 +-------------v-----------------+
                 |  Tonado Core (FastAPI/Uvicorn) |
                 |                                |
                 |  ┌─────────────────────────┐   |
                 |  │     Event Bus            │   |
                 |  │  (asyncio, in-process)   │   |
                 |  └──┬──┬──┬──┬──┬──┬──┬────┘   |
                 |     │  │  │  │  │  │  │         |
                 |  ┌──v──v──v──v──v──v──v────┐   |
                 |  │ Player    │ Card        │   |
                 |  │ Service   │ Service     │   |
                 |  │ (MPD)     │ (RFID)      │   |
                 |  ├───────────┼─────────────┤   |
                 |  │ Library   │ Stream      │   |
                 |  │ Service   │ Service     │   |
                 |  │ (Files)   │ (Radio/Pod) │   |
                 |  ├───────────┼─────────────┤   |
                 |  │ Gyro      │ Config      │   |
                 |  │ Service   │ Service     │   |
                 |  │ (MPU6050) │ (SQLite)    │   |
                 |  ├───────────┼─────────────┤   |
                 |  │ Hardware  │ Auth        │   |
                 |  │ Wizard    │ Service     │   |
                 |  │ (Detect)  │ (PIN/JWT)   │   |
                 |  └───────────┴─────────────┘   |
                 +---+-----+-----+-----+-----+---+
                     |     |     |     |     |
                     v     v     v     v     v
                   MPD   RFID  GPIO  I2C   SQLite
                  :6600  SPI   Pins  Bus    WAL
```

## Services im Überblick (Stand 2026-04-17)

Tonado hat aktuell 20 Python-Services/Layer. Die wichtigsten acht sind unten detailliert, der Rest folgt in der Kurzübersicht.

| Service | LOC | Zweck |
|---------|-----|-------|
| `event_bus` | ~55 | In-process Publish/Subscribe für asynchrone Service-Kommunikation |
| `config_service` | ~135 | SQLite-basierte Key-Value-Konfiguration mit Type-Inference |
| `auth_service` | ~180 | PIN-Hash, JWT-Tokens, Tier-Auth, Setup-Seal |
| `player_service` | ~400 | MPD-Steuerung (Play/Seek/Volume/Outputs) via python-mpd2 |
| `card_service` | ~270 | RFID-Scan-Loop, Mapping, 2s-Cooldown, Resume-Position |
| `library_service` | ~210 | Media-Ordner verwalten, Upload-Pfade, Cover-Art, Dauer |
| `stream_service` | ~330 | Radio + Podcasts (RSS), httpx-basiert mit SSRF-Schutz |
| `playlist_service` | ~190 | User-Playlists quer über Library/Streams/Podcasts |
| `timer_service` | ~260 | Sleep-Timer, Volume-Enforcement, Idle-Loop, Resume-Save |
| `system_service` | ~400 | `/update/*`, Restart/Shutdown/Reboot, Backup-Export, OverlayFS |
| `backup_service` | ~210 | Export/Import von Config + Cards + Playlists als JSON |
| `gyro_service` | ~310 | MPU6050-Polling, Gesture-Dispatch, Kalibrierung |
| `button_service` | ~200 | GPIO-Button-Scanning (Setup) + Runtime-Listener |
| `wifi_service` | ~340 | NetworkManager-Wrapper (Scan, Connect, Status) |
| `setup_wizard` | ~230 | First-Boot-State-Machine, Hardware-Fingerprint |
| `captive_portal` | ~200 | hostapd/dnsmasq-Orchestrierung für AP-Setup-Modus |
| `hardware_detector` | ~95 | Kombiniert RFID/Audio/Gyro/Pi-Detection in `HardwareProfile` |
| `websocket_hub` | ~110 | WebSocket-Fanout für Echtzeit-Events (State, Karten, Gesten) |
| `playback_dispatcher` | ~150 | Mappt Karten/Gesten/Buttons auf konkrete Player-Aktionen |
| `base_service` | ~25 | Start/Stop-Lifecycle-Mixin für alle oben genannten |

Tests: 221 grün (Stand 2026-04-17). Hardware-Services laufen auf Windows/Mac im Mock-Modus, damit die Suite auch ohne Pi grün bleibt.

## Services im Detail

### Player Service
- **Aufgabe:** Audio-Wiedergabe steuern (Play, Pause, Skip, Volume, Seek)
- **Kommunikation:** Direkt mit MPD via `python-mpd2` (async)
- **Events:** Publiziert Player-State-Changes auf den Event-Bus
- **Kein subprocess**, kein Shell-Script. Direkter MPD-Socket.

### Card Service
- **Aufgabe:** RFID-Karten erkennen, Card-to-Content Mapping verwalten
- **Hardware:** RC522 (SPI via `spidev`), PN532 (I2C via `smbus2`), USB HID
- **Auto-Detection:** Beim Start prüfen welcher Reader angeschlossen ist
- **Events:** Publiziert `card_scanned(card_id)` → Player Service reagiert

### Library Service
- **Aufgabe:** Audio-Bibliothek verwalten (Browse, Search, Upload)
- **Storage:** `~/tonado/media/` — Ordner = Album, `cover.jpg` pro Ordner
- **Upload:** Chunked Upload via tus-Protokoll (resumierbar)
- **Metadata:** Ordnername ist Titel. Kein ID3-Parsing (bewusste Entscheidung).

### Stream Service
- **Aufgabe:** Internetradio, Podcasts (RSS), ARD Audiothek Streams
- **Podcast:** RSS-Feed parsen, neue Folgen automatisch downloaden
- **Radio:** URL-basiert, vorkonfigurierter Katalog deutscher Kindersender
- **MPD:** Streams werden als MPD-Playlist-Einträge behandelt

### Gyro Service
- **Aufgabe:** MPU6050 Gyro-Sensor auslesen, Gesten erkennen
- **Gesten:** Kippen links/rechts = Skip, Schütteln = Shuffle. Kippen vor/zurück ist an `card.remove_pauses` gekoppelt:
  - Spielt-weiter-Modus (Default, Magnet-Figuren): vor/zurück = Volume +/−
  - Pausiert-beim-Abnehmen-Modus (normale Karten): vor/zurück = Play/Pause / Stop
- **Konfigurierbar:** Sensitivity-Profile (sanft/normal/wild) über Web-UI
- **Events:** Publiziert `gesture_detected(gesture, action)` → PlaybackDispatcher führt Aktion aus
- **Basiert auf:** phonie-gyro Logik (https://github.com/t13gazh/phonie-gyro)

### Config Service
- **Aufgabe:** Alle Einstellungen zentral verwalten
- **Storage:** SQLite mit WAL-Modus (überlebt Stromausfälle)
- **Schema:** Key-Value mit Typisierung und Defaults
- **Keine Flat-Files.** Eine Datenbank für alles.

### Hardware Wizard
- **Aufgabe:** Beim ersten Boot und auf Anfrage Hardware erkennen
- **Erkennt:** Pi-Modell, RFID-Reader (SPI/I2C/USB), Audio-Output, Gyro, GPIO-Belegung
- **UI:** Web-basierter Schritt-für-Schritt-Wizard
- **Kein SSH, kein Terminal.** Alles im Browser.

### Auth Service
- **Aufgabe:** PIN-basierte Zugriffskontrolle
- **Drei Tiers:**
  - **Offen:** Player-Ansicht, keine PIN nötig
  - **Eltern:** Bibliothek, Karten, Uploads, Einstellungen — PIN geschützt
  - **Experte:** Hardware, System, WiFi, Debug — separate PIN
- **Implementierung:** PBKDF2-Hash für PINs, JWT-Token mit Tier-Claims

## Event-Bus

Leichtgewichtiger In-Process Event-Bus (asyncio). Kein externer Message-Broker (kein Redis, kein ZMQ — zu schwer für Pi Zero W).

```python
# Beispiel: RFID-Karte löst Wiedergabe aus
card_service.on("card_scanned") → event_bus → player_service.play(card_mapping)

# Beispiel: Kind drückt GPIO-Button
gpio_service.on("button_press", "next") → event_bus → player_service.next()

# Beispiel: MPD State Change → WebSocket Push
player_service.on("state_changed") → event_bus → websocket_hub.broadcast(state)
```

## Datenmodell

### SQLite Schema (Kern)

```sql
-- Card-to-Content Mapping
CREATE TABLE cards (
    card_id TEXT PRIMARY KEY,     -- RFID UID
    name TEXT,                    -- "Die drei ???, Folge 1"
    content_type TEXT NOT NULL,   -- 'folder', 'stream', 'podcast', 'command'
    content_path TEXT NOT NULL,   -- Pfad, URL oder Kommando
    cover_path TEXT,              -- Cover-Art Pfad
    resume_position INTEGER DEFAULT 0,  -- Sekunden (Hörbuch-Fortschritt)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Konfiguration
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    type TEXT DEFAULT 'string'   -- 'string', 'int', 'bool', 'json'
);

-- Podcast-Feeds
CREATE TABLE podcasts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    feed_url TEXT NOT NULL,
    last_checked TIMESTAMP,
    auto_download BOOLEAN DEFAULT 1
);
```

## Filesystem-Layout (auf dem Pi)

```
/opt/tonado/                    # Anwendung
├── core/                       # Python Backend
│   ├── main.py                 # FastAPI Entry Point
│   ├── services/               # Alle Services
│   ├── routers/                # API-Routen
│   └── schemas/                # Pydantic Models
├── web/                        # Frontend Build (statisch)
├── config/                     # tonado.db (SQLite)
└── logs/                       # → tmpfs (RAM)

~/tonado/                       # User-Daten
├── media/                      # Audio-Bibliothek
│   ├── Die drei Fragezeichen/
│   │   ├── cover.jpg
│   │   ├── track01.mp3
│   │   └── track02.mp3
│   └── Bibi Blocksberg/
│       └── ...
└── podcasts/                   # Heruntergeladene Podcast-Folgen
```

## Sicherheit

- **Kein `shell=True`** — nirgendwo, niemals
- **Kein `subprocess` für Player-Befehle** — MPD direkt via Socket
- **Input-Validierung** an jeder API-Grenze
- **PIN-Hashing** mit PBKDF2 (stdlib, kein C-Compiler nötig)
- **JWT-Tokens** mit kurzer Laufzeit
- **Read-Only Root-Filesystem** im Produktivbetrieb (OverlayFS)

## Performance-Ziele

| Metrik | Ziel | Grund |
|--------|------|-------|
| Frontend Bundle | < 150 KB gzipped | Pi Zero W Browser-Limit |
| API Response | < 200 ms | Gefühlte Sofort-Reaktion |
| RFID → Play | < 1 Sekunde | Kind erwartet sofortige Reaktion |
| WebSocket Latency | < 500 ms | Echtzeit-Gefühl auf dem Smartphone |
| RAM-Verbrauch Total | < 300 MB | Pi Zero W hat 512 MB |
| Boot bis spielbereit | < 30 Sekunden | Kinder sind ungeduldig |
