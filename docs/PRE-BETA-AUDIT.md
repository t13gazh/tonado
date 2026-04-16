# Pre-Beta-Audit — v0.2.1-alpha → Beta

**Stand:** 2026-04-16 | **Ziel:** Vollständige Bestandsaufnahme vor Beta-Freigabe
**Scope:** 4 parallele Audits (Test-Coverage, Dokumentation, API/Security, Annahmen/Hardware)
**Inhalt:** Was ist verifiziert getestet vs. nur angenommen? Welche Lücken blockieren Beta?

---

## Executive Summary

- **Code:** 19 Services (3.879 LOC), 10 Router (1.740 LOC), 104 Endpoints
- **Tests:** 17 Test-Dateien (1.935 LOC, ~127 Tests) — aber **6 Services ohne Tests**, **Router-Coverage 15%**, **0 Integration-Tests**
- **Live-Hardware-Validierung:** nur Pi 3B+ (2026-04-02). **Captive Portal / First-Boot nie mit nicht-technischer Zielgruppe getestet**
- **Dokumentation:** ARCHITEKTUR.md (veraltet, 8 statt 20 Services), ROADMAP.md (v0.2.x nicht erwähnt), 3 Audit-Snapshots nicht archiviert, CONTRIBUTING.md / SECURITY.md / UPDATE.md / BACKUP.md fehlen

**Top-5-Beta-Blocker:**
1. **Auth-Öffnung bei "kein PIN gesetzt"** → System komplett offen im LAN
2. **`X-Real-IP` nicht gelesen hinter nginx** → Rate-Limit globalisiert, Brute-Force-Schutz defekt
3. **`/api/player/play-folder` Path-Traversal** (kein `_safe_path`-Check)
4. **Captive-Portal-Flow E2E nie live getestet** auf frischer SD + First-Boot
5. **Update-Mechanismus ohne Lock, Rollback unvollständig** bei pip-Fehler + 0 Tests

---

## KRITISCH — Beta-Blocker

### K1 — Auth-Öffnung ohne PIN
**Datei:** `core/services/auth_service.py:139-141`
`check_access` gibt `True` zurück wenn `_pin_cache[tier]=False`. Pi ohne gesetzten Parent-PIN ist damit im LAN voll offen — auch `/system/restart`, `/system/update/apply`, `/system/overlay/*`. Setup-Complete erzwingt aktuell keine PIN-Setzung.
**Fix:** Beim Setup-Complete PIN-Setzung erzwingen (mindestens Parent-PIN). Alternativ: `check_access` auf sinnvoll-sichere Defaults ohne PIN.

### K2 — `X-Real-IP` hinter nginx nicht gelesen
**Datei:** `core/routers/auth.py:36-60`
Nginx (in `system/install.sh` konfiguriert) proxyt lokal, alle Requests haben `request.client.host = 127.0.0.1`. Das Rate-Limit-Bucket ist damit **global**, nicht pro User-IP. Ein einzelner User kann alle anderen aussperren (5 Versuche → 60s global).
**Fix:** `X-Real-IP` / `X-Forwarded-For` auslesen (nur bei Trusted-Proxy, z.B. 127.0.0.1 als Peer). Nginx-Config setzt Header bereits korrekt.

### K3 — Path-Traversal in `/api/player/play-folder`
**Datei:** `core/routers/player.py:180`
`PlayFolderRequest.path` ist freier String, geht direkt an `player.play_folder(path)` → MPD. Library-Router nutzt `_safe_path`, Player nicht.
**Fix:** Gleichen `_safe_path`-Check wie in Library anwenden, oder Pfad gegen `library.list_folders()` whitelisten.

### K4 — Captive-Portal-Flow nie E2E live getestet
**Befund:** `core/services/captive_portal.py` hat **null Tests**. Der Flow (Pi aus Karton → AP aufspannen → User verbindet → WiFi einrichten → Neustart → Tonado läuft) wurde auf **keinem frischen Pi** mit **keiner nicht-technischen Zielperson** durchgespielt. NetworkManager-Koexistenz ungeklärt, `country_code` nicht gesetzt, Open-AP ohne Passwort, kein Auto-Timeout.
**Fix:** Drei frische SD-Images (Pi 3B+, Pi Zero W, Pi 4) `curl | bash`-installieren und den kompletten First-Boot-Flow vom AP-Join bis zum ersten Karten-Play durchspielen. Dokumentieren was tatsächlich passiert.

### K5 — Update-Mechanismus ungetestet + Lock fehlt + Rollback unvollständig
**Datei:** `core/services/system_service.py:140-285`
- **Null Unit-Tests** (`test_system_service.py` existiert nicht)
- Kein asyncio-Lock: paralleler `apply_update` → git-Chaos
- Rollback nach pip-Install-Fehler: `git reset` nur auf Code, aber **installierte Dependencies bleiben auf neuer Version** → Import-Fehler beim Restart
- `git reset --hard HEAD` verwirft uncommittete Änderungen stillschweigend
- Keine DB-Migration-Logik für Schema-Evolution
- `/update/check` ist public und triggert `git fetch` (DoS-Vektor)
**Fix:** Test-Suite (Happy Path, Netz weg, pip-Fehler, Rollback-Verifikation, parallel-Aufruf). `asyncio.Lock` einführen. Nach pip-Rollback altes pyproject nochmal installieren. Live-Test auf Pi (Dummy-Commit → Update → Verifikation).

### K6 — Captive-Portal-AP ohne Passwort
**Datei:** `core/services/captive_portal.py`
AP "Tonado-Setup" ist offen. Angreifer im Funk-Umkreis kann während Setup WiFi-Credentials abfangen/setzen, Audio-Output ändern, Hardware-Detection triggern. Setup-Endpoints bis `complete=True` völlig offen.
**Fix:** WPA2 mit Pi-spezifischem Default-Passwort (ausgedruckt im Install-Log o.ä.) ODER First-Boot-Time-Limit (z.B. 30 min Setup-Fenster).

### K7 — Watchdog aktiviert ohne systemd-Ticker
**Datei:** `system/install.sh` setzt `dtparam=watchdog=on`, `system_service._setup_watchdog` kommentiert nur "Configure systemd watchdog" — nicht implementiert. Hardware-Watchdog ist aktiv, wird nicht getickt → **Pi rebootet alle ~15s** sobald Watchdog-Gerät geöffnet wird. Latenter Bug, kann beim nächsten Boot-Event zuschlagen.
**Fix:** Watchdog aus `config.txt` entfernen ODER systemd-Ticker korrekt konfigurieren (`WatchdogSec=` in Unit-File).

### K8 — Gyro Tilt-forward/back Produkt-Diskrepanz
**Datei:** `core/services/gyro_service.py` GESTURE_ACTIONS vs. CLAUDE.md Produkt-Entscheidung
CLAUDE.md (verbindlich): "Kippen vor/zurück = Volume". Code: `TILT_FORWARD=play_pause, TILT_BACK=stop`. Volume geht nur über Buttons/App. **Product-Entscheidung bleibt unumgesetzt.**
**Fix:** Product-Owner-Entscheidung einholen (Volume vs. play_pause). Code anpassen oder CLAUDE.md aktualisieren.

---

## HOCH — vor Beta adressieren

### H1 — Tier-Konsistenz auf 4 Endpoints
- `POST/DELETE /api/auth/sleep-timer` (auth.py:155, 164) — jeder kann Sleep-Timer setzen
- `POST /api/player/outputs/{id}` (player.py:98) — jeder kann Audio-Output umschalten
- `POST /api/playlists/{id}/play` (playlists.py:94) — inkonsistent zum Rest (andere Playlist-Endpoints sind PARENT)
- `POST /api/buttons/scan/*`, `POST /api/buttons/test/*` (buttons.py:106-178) — jeder kann GPIO belegen / Button-Config scannen

### H2 — Rate-Limit nur auf /login
Upload (500 MB!), Scan, Update-Check, Podcast-Add, `/cards/scan/wait` (Long-Poll) alle ungebremst. DoS-Vektor. slowapi oder eigenes Middleware global (z.B. 100 req/min), Upload strenger (5/min).

### H3 — `str(e)` in HTTPException-Details umgeht Sanitizer
**Mehrere:** `streams.py:90`, `system.py:166,252,266,280,387`, `setup.py:111`
Exception-Strings landen beim Client (Stacktrace, httpx-URL, File-Paths, SQL). Der globale Handler in `main.py:321` greift nur bei unhandled Exceptions, nicht bei `HTTPException(500, str(e))`.
**Fix:** Intern loggen, user-facing generische Meldung.

### H4 — OverlayFS-Daten-Verlust-Falle
**Datei:** `core/services/system_service.py` + Config-Pfade
`$CONFIG_DIR` und `$MEDIA_DIR` liegen unter `/home/$USER/tonado/` — bei aktivem Overlay im RAM-Upper-Layer. **Nach Reboot: alle Config-Writes + alle Uploads weg.** API-Endpoints existieren, kein UI-Toggle (UX-Audit SY01 offen), keine Tests, keine Warnung.
**Fix für Beta:** OverlayFS im UI **nicht freischalten**. Als "Experimental" markieren oder post-Beta implementieren. Alternativ: Bind-Mounts für `/home/$USER/tonado/config` + `/home/$USER/tonado/media` in tmpfs-Upper rausnehmen (persistent halten).

### H5 — Install-Script nicht re-run-safe
**Datei:** `system/install.sh`
- `sed -i 's/$/ ipv6.disable=1/'` hängt bei jedem Run erneut an falls grep-Check leer → cmdline.txt-Korruption (muss einzeilig bleiben)
- Partial-Failure ohne Recovery (config.txt teils geschrieben, systemd-Unit fehlt noch)
- HifiBerry hardcoded auf `hifiberry-dac` (DAC-Variante), Amp2/DAC+ falsch konfiguriert
- Pi-Modell-Check lässt "unknown" weiterlaufen (2B/A+/B+ ohne WiFi bekommen hostapd ohne Nutzen)
- `apt-get update -qq` ohne Retry → schwache Verbindung bricht Install ab
**Fix:** Idempotenz konsequent (Marker-Datei `/var/lib/tonado/install.done`, grep-Checks robuster), HifiBerry-Variante abfragen oder dokumentieren, apt-Retry-Loop.

### H6 — Test-Coverage-Lücken bei 6 Services
**Komplett ungetestet:** `system_service` (378 LOC), `button_service` (202 LOC), `captive_portal` (167 LOC), `playlist_service` (189 LOC), `websocket_hub` (109 LOC), `gyro_service` (Service-Schicht — nur GestureDetector-Algorithmus getestet).
**Fix-Reihenfolge:** system_service → playlist_service → button_service → captive_portal → websocket_hub → gyro_service-Service-Layer.

### H7 — Router-Coverage bei 15%
**80 Endpoints, ~12 im Test aufgerufen.** Player (15 Endpoints), Gyro-Calibration (6 Endpoints), Buttons (10 Endpoints), Setup (12 Endpoints) komplett ungetestet auf HTTP-Ebene.
**Fix:** Parametrisierter Auth-Matrix-Test (alle geschützten Endpoints × Tier) deckt mit ~1 Test 40+ Endpoints ab.

### H8 — Pi 4/5 nie getestet, Pi Zero W seit Alpha nicht mehr
- Pi 5 hat anderen GPIO-Controller (RP1) — gpiod v2 sollte abstrahieren, aber nicht verifiziert
- Pi Zero W (512 MB RAM): nginx-Upload-Limit 500 MB → OOM-Kill bei großen Uploads (nginx puffert komplett vor Proxy-Pass)
- ARMv6 (Pi Zero W): aiosqlite hat kein Wheel → Source-Build dauert 30+ Min (nicht dokumentiert)
**Fix:** Kompatibilitätsmatrix explizit in README: "Beta getestet: Pi 3B+. Experimentell: Zero W, Zero 2 W. Ungetestet: Pi 4/5." Auf Pi Zero W: nginx `client_max_body_size` reduzieren, Swap in Install.

### H9 — Hardware-Detection-Fragilität
**Datei:** `core/hardware/detect.py`
- RC522-Versions-Check nur 0x91/0x92 (Klone mit 0x88/0xB2 unterstützt ≠ 0)
- USB-HID: alles unter `/dev/hidraw*` als RFID angenommen → Tastatur/Maus wird falsch-positiv erkannt
- PN532 nur I2C (UART/SPI-Varianten ignoriert)
- Hardware-Fingerprint: Audio-Devices-Reihenfolge ändert sich → `hardware_changed=True` obwohl nichts geändert
**Fix:** USB-HID per VID/PID whitelisten, RC522-Klone-Versions akzeptieren, Fingerprint stabiler gestalten.

### H10 — WebSocket ohne Auth, ohne Connection-Limit
**Datei:** `core/main.py:385`, `core/services/websocket_hub.py`
Origin-Check vorhanden, aber `origin=None` erlaubt (CLI-Tools → offen). Jeder im LAN bekommt Echtzeit `card_scanned`-Events mit IDs. Kein Max-Connection-Limit → Pi Zero W OOM-Risiko.
**Fix:** First-Message-Auth (JWT als ersten Frame), Max-Connections (z.B. 20).

### H11 — Dokumentation veraltet
- `docs/ARCHITEKTUR.md`: 8 statt 20 Services, fehlt Button/Backup/Playlist/Timer/System/WiFi/CaptivePortal/WebSocketHub
- `docs/ROADMAP.md`: v0.2.x-Fortschritt nicht erwähnt, kein Meilenstein 1.5 "Beta-Readiness"
- `docs/entwicklung.md`: Tech-Stack unvollständig, Release-Workflow (Frontend lokal bauen, build committen, Update-Mechanismus) fehlt
- `docs/installation.md:3`: broken anchor `#installation` (Anker heißt `#schnellstart` in README)
- `docs/AUDIT-2026-03-28.md`, `PERFORMANCE-2026-03-28.md`, `UX-AUDIT-2026-03-28.md`: alle Findings erledigt, wirken wie offene Issue-Tracker → archivieren
- `BACKLOG.md`: erledigte Punkte noch offen (Figuren-UI, Update-Dialog-Teilergebnis)
**Fix:** Siehe Teil "Doku-Updates" unten.

### H12 — Fehlende Doku vor Beta
- **`CONTRIBUTING.md`** (README lädt zu Beiträgen ein, aber keine Guidelines)
- **`SECURITY.md`** (CVE-Reporting-Pfad für externe Tester)
- **`docs/UPDATE.md`** (zentrales Endnutzer-Feature, nirgends erklärt)
- **`docs/BACKUP.md`** (Export/Import-Flow, Was-wird-exportiert, Hardware-Kompatibilität)
- **README.md:** "Known Issues" Absatz (Browser-Audio-Bug transparent erwähnen)

---

## MITTEL — Beta-dokumentiert OK

### M1 — ConfigSetRequest.value ohne Whitelist
`value: Any` für beliebige Keys. Ein Parent-User kann `player.mpd_host="evil.com"` setzen. Key-Whitelist + Typ-Validation pro Key (post-Beta).

### M2 — Library-Filename-Sanitization schwach
`file.filename.replace("/", "_")` → lässt `..mp3`, Null-Bytes, Unicode-Tricks durch. `Path(file.filename).name` verwenden.

### M3 — JWT-Config
- 24h Token-Lifetime (Kinder-Gerät: 2-4h reicht)
- Kein Refresh, keine Revocation bei PIN-Change → neuer JWT-Secret bei `set_pin` wäre eine-Zeile-Fix
- Kein Logout-Endpoint (Frontend-Only-Logout derzeit)

### M4 — Nginx liefert statische Assets ohne Security-Header
FastAPI-Middleware setzt Header für /api, /ws. SPA-Assets unter `/` laufen durch Nginx ohne CSP/X-Frame-Options. Nginx-Config um `add_header` ergänzen.

### M5 — `/api/system/info` + `/api/system/health` leaken LAN-Metadaten
Hostname, IP, SSID, RAM, OverlayFS-Status. Im Familien-LAN akzeptabel. Inkonsistent zum Rest des System-Routers (meist EXPERT). IP/SSID maskieren oder PARENT erzwingen.

### M6 — Backup Version/Hardware-Compat
- `version: "1"` nur auf `isinstance(str)` geprüft — Backup aus zukünftiger Version importiert ohne Warnung
- `cover_path` nicht gegen Path-Traversal geprüft (nur `content_path`)
- Cross-Box-Import überschreibt `audio.device=hw:1` auf inkompatiblem Audio-Gerät → Stille
- Kein Size-Limit beim Import (500-MB-JSON möglich)

### M7 — RFID-Cooldown nicht live-reconfigurierbar
`card.rescan_cooldown` per Config setzbar, aber `CardService.__init__` nimmt Wert nur beim Start. Änderung erst nach Restart wirksam. Event-Subscriber auf Config-Change oder Property-Read.

### M8 — Service-Startup: `return_exceptions=True` bei Auth
Wenn AuthService-Start fehlschlägt, läuft Server weiter OHNE Auth. `get_auth_service` liest `app.state.auth_service` → Exception statt Service → Attribute-Error beim ersten Request. Defensive-Check nötig.

### M9 — Card-Cooldown 2s ungetestet
Kern-Produkt-Verhalten (CLAUDE.md), kein Test. `test_card_scanned_event` nutzt 0.1s-Cooldown. Realistischer Test mit 2s-Cooldown erforderlich.

### M10 — Auth-Middleware-Matrix ungetestet
`test_routers.py` testet 1 EXPERT-Endpoint (restart) und wenige PARENT. 40+ `require_tier`-Aufrufe ohne Test — wenn jemand einen Call vergisst, bleibt es unbemerkt.

---

## NIEDRIG / NICE-TO-HAVE (Post-Beta)

- CODE_OF_CONDUCT.md, docs/TROUBLESHOOTING.md, docs/API.md
- WebSocket-First-Message-Auth
- WebSocket-Connection-Limit
- JWT-Token-Lifetime konfigurierbar
- Backup inkl. Media-Files (optional, große Archive)
- Hardware-Detection UART/SPI-PN532
- Player Retry-Loop bei MPD-Startup-Failure
- RFID Different-Card-Debounce 50-100ms

---

## Test-Coverage-Matrix (Ist-Zustand)

| Service | LOC | Tests | Abgedeckt | Bewertung |
|---|---|---|---|---|
| event_bus | 54 | 5 | in-proc komplett | OK |
| config_service | 136 | 10 | CRUD + Typen | OK |
| auth_service | 165 | 12 | PIN, Login, Tokens, Tier | WARN (Expiry/Rotation fehlt) |
| library_service | 207 | 6 | CRUD + disk_usage | WARN (traversal/permissions) |
| player_service | 403 | 21 | Playback + Volume + Stream | OK (toggle+reload ungetestet) |
| card_service | 268 | 4 | CRUD + scan-event | WARN (Cooldown 2s, Debounce) |
| stream_service | 327 | 5 | Seeding + CRUD | KRITISCH (RSS-Parsing, SSRF, httpx-Mock fehlt) |
| timer_service | 258 | 11 | Sleep, Volume, Resume | WARN (_idle_loop ungetestet) |
| wifi_service | 339 | 4 | nur Mock-Modus | KRITISCH (nmcli-Pfad 95% unabgedeckt) |
| setup_wizard | 224 | 5 | State-Progression | WARN (hardware_changed, Fingerprint) |
| hardware_detector | 94 | 2 | detect_all Mock | WARN (redetect, health) |
| backup_service | 210 | 5 | Roundtrip + Schema | WARN (Disk-Errors, Fuzzy-Match) |
| gyro_service | 312 | 9 (nur Algo) | Gesture-Detection | KRITISCH (Service-Schicht 0) |
| **system_service** | **378** | **0** | — | **KRITISCH** |
| **button_service** | **202** | **0** | — | **KRITISCH** |
| **captive_portal** | **167** | **0** | — | **KRITISCH** |
| **playlist_service** | **189** | **0** | — | **KRITISCH** |
| **websocket_hub** | **109** | **0** | — | **KRITISCH** |

**Router-Coverage:** 80 Endpoints, ~12 im Test aufgerufen (15%). Player (15), Gyro-Calibration (6), Buttons (10), Setup (12) komplett HTTP-ungetestet.

**Integration-Tests:** 0. Alle Hardware-Pfade gemockt. Kein Test gegen echte MPD, GPIO, SPI/I2C, nmcli, git, hostapd, dnsmasq.

---

## "Angenommen getestet — aber nicht wirklich"

- **Player robust** (21 Tests sehen viel aus) — aber `toggle()` mit Stream-Reload (Changelog-Feature!), `_sync_state`-Error, Mixer-fehlt-Pfad ungetestet
- **Card-Cooldown 2s funktioniert** — kein Test mit realistischem Wert (0.1s in Tests)
- **Auth-Middleware schützt** — nur 6 Endpoints auf 403 getestet, 40+ require_tier-Pfade ohne Test
- **Rate-Limit-Logik** — 5-Attempts-Test existiert, aber Reset-Timing, Pre-IP-Tracking, Erfolg-nach-Expire nicht abgedeckt
- **Wizard-Rerun-Safety** — nur Step-Persistence getestet, nicht `_hardware_changed`-Dirty-Flag
- **Setup-Flow** — State-Progression getestet, aber der komplette First-Boot (AP → WiFi → Reboot → Player) nie
- **Gyro-Algorithmus** — phonie-gyro-Port angenommen, aber Output-Pairing mit Referenz-Daten nicht verifiziert
- **Hardware-Wizard** — Pi 3B+ bestanden, andere Hardware-Kombinationen (PN532, USB-Reader, DAC+) nur theoretisch
- **Backup-Restore Cross-Box** — Roundtrip auf gleicher Box OK, anderer Pi nie getestet
- **Install-Script** — einmal auf Pi 3B+ grün, Re-Run + Partial-Failure + andere Pi-Modelle ungetestet
- **OverlayFS** — API da, nie Power-Loss-Test, Konfig-Verlust-Risiko ignoriert
- **Update-Mechanismus** — 0 Tests, Rollback unvollständig, Happy Path angenommen

---

## Doku-Updates vor Beta (Zusammenfassung)

**Must-fix:**
1. `docs/ARCHITEKTUR.md` — Service-Liste auf 20 Services erweitern, Diagramm aktualisieren
2. `docs/ROADMAP.md` — Meilenstein 1.5 "Beta-Readiness (v0.2.x)" einfügen
3. `BACKLOG.md` — erledigte Items `[x]` abhaken (Figuren-UI, Update-Dialog), Audit-Findings aus diesem Dokument übernehmen
4. `CONTRIBUTING.md` + `SECURITY.md` im Root anlegen
5. `docs/AUDIT-2026-03-28.md` + `PERFORMANCE-2026-03-28.md` + `UX-AUDIT-2026-03-28.md` archivieren (Banner oder `docs/archive/`)
6. `docs/installation.md:3` — Broken Anchor `#installation` → `#schnellstart`

**Should-fix:**
7. `docs/entwicklung.md` — Tech-Stack synchronisieren, Release-Workflow dokumentieren
8. `docs/UPDATE.md` + `docs/BACKUP.md` als Endnutzer-Doku
9. `docs/hardware.md` — GPIO-Buttons-Sektion mit Auto-Scan
10. `README.md` — "Known Issues"-Absatz (Browser-Audio)
11. `docs/hardware.md` / README — Pi-Kompatibilitätsmatrix explizit ("Beta getestet: 3B+ / Experimentell: Zero W, Zero 2 W / Ungetestet: 4, 5")

**Nice-to-have:**
12. `docs/UI-GUIDELINES.md` — Datum auf 2026-04 refreshen
13. CODE_OF_CONDUCT.md, docs/TROUBLESHOOTING.md, docs/API.md post-Beta

---

## Abgeleitete TODO-Reihenfolge

### Phase 1 — Security-Härtung (1-2 Sessions)
1. K1 Setup-Complete erzwingt PIN-Setzung
2. K2 `X-Real-IP` hinter nginx lesen
3. K3 `/play-folder` Path-Validation
4. K6 Captive-Portal-AP WPA2 + Timeout
5. K7 Watchdog aus Install-Script raus bis systemd-Ticker da ist
6. H1 Tier-Checks auf `/sleep-timer`, `/player/outputs`, `/playlists/{id}/play`, `/buttons/scan|test`
7. H2 Globales Rate-Limit
8. H3 `str(e)` in HTTPException bereinigen

### Phase 2 — Update-Härtung (1 Session)
9. K5 Unit-Tests `test_system_service.py` (Happy Path + Fehlerpfade + Rollback)
10. K5 `asyncio.Lock` in SystemService
11. K5 pip-Rollback: altes pyproject nachinstallieren
12. K5 Live-E2E auf Pi (Dummy-Commit + kaputter Commit)

### Phase 3 — Test-Coverage (2-3 Sessions)
13. H6 `test_playlist_service.py`
14. H6 `test_button_service.py`
15. H6 `test_captive_portal.py`
16. H6 `test_websocket_hub.py`
17. H6 `test_gyro_service.py` (Service-Schicht zusätzlich)
18. H7 Parametrisierter Auth-Matrix-Test (alle geschützten Endpoints)
19. M9 Card-Cooldown 2s realistischer Test

### Phase 4 — Captive-Portal + Install E2E (1 Session + Hardware)
20. K4 Drei frische SD-Images (Pi 3B+, Pi Zero W, Pi 4): curl|bash → AP → WiFi → Wizard → Karte-Play
21. H5 Install-Script Idempotenz + Marker-Datei
22. H8 Pi-Kompatibilitätsmatrix + nginx client_max_body_size-Anpassung für Zero W

### Phase 5 — Doku + Aufräumen (0.5 Session)
23. H11/H12 Alle Doku-Updates (siehe Liste oben)
24. BACKLOG.md refresh (erledigte abhaken, neue Findings ein)

### Phase 6 — Product-Decisions
25. K8 Gyro Tilt-forward/back: Volume vs. play_pause klären

### Post-Beta (nicht Beta-blockierend)
- H4 OverlayFS vernünftig lösen oder als Experimental verstecken
- H9 Hardware-Detection härten (Klone, USB-HID VID/PID)
- H10 WebSocket-Auth + Connection-Limit
- M1-M10 alle nice-to-have Findings

---

**Ende Audit. Für Umsetzung neue Session öffnen und nach Phasen-Reihenfolge abarbeiten.**
