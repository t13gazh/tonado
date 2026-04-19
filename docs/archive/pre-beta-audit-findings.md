# Pre-Beta-Audit — Findings-Historie

> Dies ist die Historie des Pre-Beta-Audits (Frühjahr 2026). Alle Items sind erledigt oder verschoben.
> Aktive Arbeit steht in [`../../BACKLOG.md`](../../BACKLOG.md). Der ausführliche Audit-Bericht mit Findings und Fix-Begründungen liegt in [`PRE-BETA-AUDIT.md`](PRE-BETA-AUDIT.md).

**Pre-Beta-Audit (2026-04-16 → 2026-04-17):** Phase 1 (Security), Phase 2 (Update), Phase 3 (Test-Coverage), Phase 5 (Doku) erledigt. Alle 10 MITTEL-Findings (M1–M10) erledigt. K8 Gyro-Tilt erledigt (Kopplung an `card.remove_pauses`). H5 erledigt (Install-Marker + Force-Flag + apt-Retry + cmdline-Fix + HIFIBERRY_OVERLAY). H9 erledigt (Klon-Versionen, HID-Filter, stabiler Fingerprint). Offen für Beta-Freigabe: K5-Live-E2E (Pi-Hardware), K4 Captive-Portal-First-Boot.

## Pre-Beta-Audit (abgearbeitet 2026-04-17)

**KRITISCH:**
- [x] K1 Setup-Complete erzwingt Eltern-PIN (AuthService-Seal + Wizard PIN_SETUP-Step, Commits 5366ebe + 287c321)
- [x] K2 X-Real-IP / X-Forwarded-For hinter nginx (Commit ac1fd09)
- [x] K3 Path-Validation auf `/api/player/play-folder` (Commit 64b1c2f)
- [x] K5 `/update/apply` Lock + pip-Rollback + Tests + `/update/check` PARENT-gated (Commit 27f1585) — Live-E2E auf Pi steht noch aus
- [x] K6 Captive-Portal WPA2 + Auto-Timeout (Commit 975edcd)
- [x] K7 Hardware-Watchdog deaktiviert bis systemd-Ticker da ist (Commit df3cc09)
- [ ] K4 Captive-Portal-First-Boot E2E auf 3 SD-Images — braucht Hardware (bleibt offen für Beta-Freigabe)
- [x] K8 Gyro Tilt-forward/back an `card.remove_pauses` gekoppelt: Spielt-weiter-Modus = Volume, Pausiert-Modus = Play/Pause + Stop. Doku + Code + Tests angepasst.

**HOCH:**
- [x] H1 Tier-Checks auf `/sleep-timer`, `/player/outputs`, `/buttons/scan|test` (Commit 7f8c6aa)
- [x] H2 Globales Rate-Limit (100/min write, 5/min upload) (Commit f4c793b)
- [x] H3 `str(e)` in HTTPException bereinigt (streams.py, system.py, Commit 01db72d)
- [x] H4 OverlayFS hinter explizitem Config-Opt-in (Commit 193b679)
- [x] H6 Service-Tests (playlist, button, websocket, gyro-service, Commit 3a93b07)
- [x] H7 Auth-Matrix-Test (Commit 77f2c4b)
- [x] H10 WebSocket Connection-Limit (Commit 193b679)
- [x] H11 Doku aktualisiert (ARCHITEKTUR, ROADMAP, BACKLOG, Audit-Archiv, Commit e67766f)
- [x] H12 CONTRIBUTING.md, SECURITY.md, docs/UPDATE.md, docs/BACKUP.md (Commit e67766f)
- [x] H5 Install-Script Idempotenz + Marker-Datei: `/var/lib/tonado/install.done` wird nur am Ende geschrieben (kein Short-Circuit bei partial failure), `--force`/`--reinstall` für bewusste Re-Runs, apt-Retry 3× bei flakiger Verbindung, cmdline.txt nur Zeile 1 (keine Multi-Line-Korruption mehr), `HIFIBERRY_OVERLAY` als Env-Variable für Amp2/DAC+, uninstall.sh räumt Marker weg.
- [ ] H8 Pi-Kompatibilitätsmatrix in README (Commit e67766f) — Doku erledigt; Live-Tests auf Zero W / 4 / 5 offen
- [x] H9 Hardware-Detection härten: RC522-Klon-Versionen (0x88, 0xB2) akzeptiert, USB-HID filtert Tastatur/Maus/Gamepad/etc. anhand HID_NAME, Fingerprint ignoriert ALSA-Card-Nummern (hw:0 ↔ hw:1 Swap ist kein Hardware-Wechsel mehr).

**MITTEL:**
- [x] M1 ConfigSetRequest.value Whitelist (Commit 891b188)
- [x] M2 Library-Filename via `Path(..).name` (Commit 9d0bf0c + aba670b Windows-Backslashes)
- [x] M3 JWT 4h + Secret-Rotation bei PIN-Change (Commit 3b1e757)
- [x] M4 Nginx-Security-Header für Static-Assets (Commit caff1bf, install.sh)
- [x] M5 `/system/info` + `/health` LAN-Metadaten maskiert (Commit 980cf03)
- [x] M6 Backup-Import: Size-Cap, cover_path, version, audio.* skip (Commit 2d9bddc)
- [x] M7 RFID-Cooldown live-reconfigurierbar (Commit 9d0bf0c)
- [x] M8 AuthService-Start-Failure bricht Boot ab (Commit 9d0bf0c)
- [x] M9 Card-Cooldown 2s Test (Commit 77f2c4b + f971400 Direkt-Test)
- [x] M10 Auth-Matrix-Test (Commit 77f2c4b)

**Pre-existing Failures gefixt (Commit aa79c94):** test_stream_service, test_gyro, test_playback_dispatcher — Test-Suite komplett grün (222 Tests).

## Security-Audit (2026-03-29) — vor erster Alpha

### KRITISCH
- [x] XXE in RSS-Parsing: `defusedxml.ElementTree.fromstring()` statt `xml.etree` (`stream_service.py:290`)
- [x] SSRF-Schutz: `validate_url()` Utility blockt interne IPs + prüft DNS (`core/utils/url.py`)
- [x] Rate-Limiting auf Login: 5 Fehlversuche → 60s Lockout (`auth.py:21`)
- [x] Backup-Export filtert Secrets + Auth nötig (PARENT für Export, EXPERT für Import)

### HOCH — Auth auf schreibenden Endpoints
- [x] Library PUT/POST/DELETE: `require_tier(PARENT)` (`library.py:72-103`)
- [x] Cards POST/PUT/DELETE: `require_tier(PARENT)` (`cards.py:28-65`)
- [x] Streams POST/DELETE + Refresh: `require_tier(PARENT)` (`streams.py:32-67, 111`)
- [x] Playlists POST/PUT/DELETE: `require_tier(PARENT)` (`playlists.py:32-69`)
- [x] Setup-Endpoints nach Completion gesperrt (`setup.py:27-88`)
- [x] SSRF: URL-Whitelist http/https, Blacklist interne IPs (`stream_service.py`, `player_service.py`)

### MITTEL
- [x] Security-Header Middleware (nosniff, X-Frame-Options, Referrer-Policy, Permissions-Policy)
- [x] JWT iss/aud Claims (iss=tonado, aud=tonado-api, validiert bei Decode)
- [x] Backup-Import Schema-Validierung (Pflichtfelder, Typen, max 5 Fehler gemeldet)
- [x] Error-Details nicht an Client zurückgeben (generischer 500-Handler)
- [x] WebSocket Origin-Prüfung (LAN-only, private IPs + .local)
- [x] Auth-Failure Logging (IP + Versuchszähler)

## E2E Flow-Audit (2026-03-29) — HOCH-Prio Fixes

- [x] API-Client: Backend-Fehlermeldungen aus JSON-Body lesen statt generisch (`api.ts:89`)
- [x] Card-Scan-Loop: AbortController bei Navigation (`card-scan.svelte.ts:39`)
- [x] Podcast-Play Race Condition: await togglePodcast() vor playEpisode (`PodcastTab.svelte:101`)
- [x] Settings saveSetting/sleepTimer ohne try/catch (`settings/+page.svelte:87, 166`)
- [x] Playlist-Löschung ohne Bestätigung (`PlaylistTab.svelte:37`)
- [x] Seek-Promise Error-Handling (seekOverride friert ein) (`+page.svelte:97`)
- [x] Audio-Setup sendet MPD-Output-Namen statt falschem `hw:${id}` (`AudioStep.svelte:21`)

## Accessibility-Audit (2026-03-29)

### KRITISCH
- [x] Modal Focus-Trapping + `role="dialog"` + Escape-Handler (`cards/+page.svelte`)
- [x] Seek-Bar als Slider mit Keyboard-Support + ARIA-Attribute (`+page.svelte`)

### HOCH
- [x] Globaler Focus-visible Style in `app.css`
- [x] Toast `aria-live="polite"` (`settings/+page.svelte`)
- [x] Kontrast text-muted aufgehellt (#9393a8 → #a0a0b8)
- [x] Touch-Targets vergrößert (Edit/Delete Buttons min 44px)
- [x] SVGs in Navigation `aria-hidden="true"`

## i18n-Audit (2026-03-29) — Minimal
- [x] Placeholder "Die drei ???, Folge 1" als i18n-Key (`wizard.name_placeholder`)
- [x] ~20 unbenutzte Keys identifiziert (player.now_playing, library.search, wizard.select_track etc.) — behalten für geplante Features (Suche, Track-Auswahl, OverlayFS-UI)

## Test-Coverage (2026-03-29)
- [x] MockMPDClient erstellt (`tests/mock_mpd.py`) — simuliert python-mpd2 async Interface
- [x] PlayerService Tests: 21 Tests (Playback, Volume, Seek, Shuffle, Repeat, Outputs, Disconnected)
- [x] PlaybackDispatcher Tests: 10 Tests (Folder, Stream, Podcast, Playlist, Command, Gestures, Resume)
- [x] TimerService Tests: 6 Tests (Sleep Timer, Volume Enforcement, Resume)
- [x] Router-Integrationstests: 12 Tests (Auth-Middleware, Path Traversal, Rate Limiting, Validation, Sensitive Keys)

## Architektur-Audit (2026-03-29)

### KRITISCH
- [x] Sequentieller Startup: Services mit `asyncio.gather()` in 4 Gruppen parallel (`main.py`)
- [x] 1Hz EventBus-Spam: `_elapsed_loop` prüft `has_listeners`, max_volume gecached + Event-Invalidierung

### WARNUNG
- [x] Sync Library-IO: `list_folders()` läuft via `run_in_executor` im Thread-Pool
- [x] Unvollständiger Shutdown: Alle 17 Services werden in korrekter Reihenfolge gestoppt (`main.py`)
- [x] RSS-Parsing nutzt httpx (nicht urllib)
- [x] PlaylistItem.content_type nutzt ContentType Enum
- [x] WebSocket-Disconnect Cleanup: `try/finally` mit `hub.disconnect()` (`main.py`)
- [x] Config-API mit Auth: PUT/DELETE erfordert PARENT-Tier (`config.py`)

### VERBESSERUNG
- [x] Loading-Heuristik: Explizites `loading`-Flag statt fragiler Heuristik — gesetzt bei Track-Wechsel, gelöscht bei erstem MPD-Play-Status
- [x] scan_waiters Leak: finally-Block für Future-Cleanup bei Request-Abbruch (`card_service.py:260`)

## Setup-Wizard (erledigt)
- [x] Audio Test-Button (Sound abspielen zum Prüfen)
- [x] WiFi Passwort-Toggle (Auge-Icon)
- [x] GPIO-Button-Erkennung (interaktiver Scan im Wizard)
- [x] Gyro-Gesten: phonie-gyro Algorithmus portiert, Kalibrierung mit Achsen-Mapping implementiert
- [x] OnOff SHIM (Kernel-Overlays: GPIO 17=Button, GPIO 4=Power-Off, getestet auf Pi 3B+)

Offene Setup-Wizard-Punkte sind in den aktiven Backlog übergegangen (`../../BACKLOG.md`).

## v0.2.0-beta-Meilenstein (abgeschlossene Punkte)
- [x] Hardware-Resilience: Graceful Degradation wenn Hardware fehlt/falsch
- [x] Figuren-UI + Einstellungen + System-Seite testen und fixen (Pi 3B+ Live-Test bestanden)
- [x] Pi-Test mit echter Hardware (RFID, Gyro, Buttons — Pi 3B+)
- [x] README.md mit Installationsanleitung für Endnutzer
- [x] Error-Boundaries und User-freundliche Fehlermeldungen

Offene Beta-Blocker (Captive Portal First-Boot, Install-Script E2E, Pi Zero W Performance, Hardcoded Strings → i18n) sind in den aktiven Backlog übergegangen.

## Architektur-Refactoring (erledigt)
- [x] Rate-Limit auf /api/system/restore und /api/auth/login — Login 5/min, Restore 3/min als eigene Buckets in der `RateLimitMiddleware`. Schützt PBKDF2-CPU-Last und 10 MB-JSON-Parse auf Pi Zero W auch bei richtig-PIN-Hammering. Tests: 2 neue, Bucket-Isolation verifiziert.

Weitere offene Architektur-Refactorings stehen im aktiven Backlog.
