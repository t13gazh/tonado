# Backlog

> **UX-Leitlinie:** So einfach wie möglich. Kein überladenes UI. Besser als alle anderen Apps. Layouts testen, ausprobieren, verwerfen, umbauen — bis Nutzer sagen: "Das ist durchdacht, das sieht geil aus."

> **Pre-Beta-Audit (2026-04-16 → 2026-04-17):** Phase 1 (Security), Phase 2 (Update), Phase 3 (Test-Coverage), Phase 5 (Doku) ✅ erledigt. Alle 10 MITTEL-Findings (M1–M10) ✅. K8 Gyro-Tilt ✅ (Kopplung an `card.remove_pauses`). H5 ✅ (Install-Marker + Force-Flag + apt-Retry + cmdline-Fix + HIFIBERRY_OVERLAY). H9 ✅ (Klon-Versionen, HID-Filter, stabiler Fingerprint). Offen: K5-Live-E2E (Pi-Hardware), K4 Captive-Portal-First-Boot. Details: [`docs/PRE-BETA-AUDIT.md`](docs/PRE-BETA-AUDIT.md).

## Pre-Beta-Audit (abgearbeitet 2026-04-17)

**KRITISCH:**
- [x] K1 Setup-Complete erzwingt Eltern-PIN (AuthService-Seal + Wizard PIN_SETUP-Step, Commits 5366ebe + 287c321)
- [x] K2 X-Real-IP / X-Forwarded-For hinter nginx (Commit ac1fd09)
- [x] K3 Path-Validation auf `/api/player/play-folder` (Commit 64b1c2f)
- [x] K5 `/update/apply` Lock + pip-Rollback + Tests + `/update/check` PARENT-gated (Commit 27f1585) — Live-E2E auf Pi steht noch aus
- [x] K6 Captive-Portal WPA2 + Auto-Timeout (Commit 975edcd)
- [x] K7 Hardware-Watchdog deaktiviert bis systemd-Ticker da ist (Commit df3cc09)
- [ ] K4 Captive-Portal-First-Boot E2E auf 3 SD-Images — braucht Hardware
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
- [ ] H8 Pi-Kompatibilitätsmatrix in README (Commit e67766f) — ✅ auf Doku-Seite; Live-Tests auf Zero W / 4 / 5 offen
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


## Offene Bugs

- [ ] **Browser-Audio bricht bei Stream-Wechsel ab.** Wenn Browser-Audio aktiv ist und man den Radio-Stream oder die Musik wechselt, kommt kein Audio mehr im Browser. Erst nach manuellem Deaktivieren/Aktivieren wieder Ton. Bisherige Fix-Versuche (Retry-Chain, Reload-Delay 2.5s, alten Stream sofort stoppen, same-URI Detection) haben nicht geholfen. Root Cause ist tiefer — vermutlich muss der gesamte Ansatz (HTML Audio Element auf Streaming-Proxy) überdacht werden. Mögliche Alternative: WebAudio API oder Server-Sent Events für Stream-Status.

## Security-Audit (2026-03-29) — VOR Beta fixen

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

## v0.2.0-beta — Nächste Schritte
- [x] Hardware-Resilience: Graceful Degradation wenn Hardware fehlt/falsch
- [x] Figuren-UI + Einstellungen + System-Seite testen und fixen (Pi 3B+ Live-Test bestanden)
- [ ] Captive Portal / Setup-Wizard Ersteinrichtungs-Flow
- [ ] SD-Karte >= 16 GB, Install-Script End-to-End testen
- [x] Pi-Test mit echter Hardware (RFID, Gyro, Buttons — Pi 3B+)
- [ ] Performance-Optimierung für Pi Zero W (siehe Architektur-Audit unten)
- [x] README.md mit Installationsanleitung für Endnutzer
- [ ] Hardcoded Strings → i18n
- [x] Error-Boundaries und User-freundliche Fehlermeldungen

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

## Setup-Wizard
- [x] Audio Test-Button (Sound abspielen zum Prüfen)
- [x] WiFi Passwort-Toggle (Auge-Icon)
- [x] GPIO-Button-Erkennung (interaktiver Scan im Wizard)
- [ ] Status-LED Steuerung via ButtonService (GPIO 23, Blinkmuster für Boot/Play/Error)
- [x] Gyro-Gesten: phonie-gyro Algorithmus portiert, Kalibrierung mit Achsen-Mapping implementiert
- [x] OnOff SHIM (Kernel-Overlays: GPIO 17=Button, GPIO 4=Power-Off, getestet auf Pi 3B+)
- [ ] Hilfe/Troubleshooting als Popup aus Git-Docs laden

## Prio 1 — Kernfunktionen
- [x] Sleep-Timer mit Fade-Out: Lautstärke sanft runterfahren statt abrupt stoppen
- [x] Auto-Fallback auf AP-Modus: `ConnectivityMonitor`-Service pollt WLAN-Status, startet nach Timeout automatisch das bestehende Captive Portal als Rettungs-AP. Owner-Flag (`setup`/`auto`/`manual`) verhindert dass Monitor fremdgestartete Portale anfasst. State-Machine mit Boot-Grace, Double-Check, Post-Recovery-Cooldown, Circuit-Breaker. Eltern-UI in `/settings` mit Toggle, AP-Credentials, QR-Code zum Ausdrucken (WIFI:-URI-Scheme). Backend-Tests (11 neue State-Machine-Tests, 2 Owner-Flag-Tests für das Portal), Frontend-Build grün. Live-Test auf Pi-Hardware offen.

## Prio 2 — Differenzierung
- [ ] Sprachaufnahme in der Web-App: Figur/Karte auflegen → App erkennt sie → direkt besprechen (MediaRecorder API). Physische Geste + Aufnahme verknüpft = einprägsamer als nachträgliches Zuordnen
- [ ] Offline-Modus: Box trennt Internet-WLAN, spannt eigenes AP auf. App zeigt Offline-Status, Streaming-Features (Radio, Podcasts) werden visuell deaktiviert. Lokale Musik + Figuren funktionieren weiter. Datenschutz-Feature für bewusste Eltern — kein Datenverkehr nach außen
- [ ] WLAN-Verwaltung in Einstellungen: Verfügbare Netze scannen, neues WLAN hinzufügen, zwischen gespeicherten Netzen wechseln. Unabhängig vom Offline-Modus — normales Netzwerk-Management über die App
- [ ] Dateien/Ordner von der Box herunterladen (Use Case: Musik vom Handy hochgeladen, lokal gelöscht, am Laptop wieder holen)
- [ ] Figur verloren = kein Problem: Content ist an ID gebunden, einfach neue Karte beschreiben und gleichen Inhalt zuordnen. In App klar kommunizieren

## Prio 2.5 — Update-System ausbauen
- [ ] Update via GitHub Releases API: Statt git pull — Release-Archiv herunterladen, Semver-Vergleich mit lokaler Version. Kein Git auf Endnutzer-Pi nötig. Aktuell: git-basiertes Update in system_service.py (check_update/apply_update)
- [ ] Changelog in der App anzeigen: Release Notes aus GitHub vor Installation zeigen
- [ ] Update-Fortschrittsanzeige: Download + Installation mit visuellem Feedback
- [ ] Update-Rollback: Alte Version als Fallback behalten, bei Boot-Failure automatisch zurück
- [ ] Checksum-Validierung: SHA256 aus Release prüfen vor Installation
- [ ] USB-Stick-Update: Release-Archiv auf Stick → Box erkennt beim Einstecken, Offline-Update möglich

## Prio 3 — Wertvolle Erweiterungen
- [ ] Box-Name: Im Setup Wizard festlegen, in Einstellungen nachträglich änderbar. Default "Tonado". Ändert mDNS-Hostname (z.B. `meinebox.local`) und Netzwerk-Discovery-Name
- [ ] Farbschema: Farbthema der Web-App in den Einstellungen änderbar. Personalisierung der Box-Oberfläche (z.B. Lieblingsfarbe des Kindes)
- [ ] Radio/Podcast-Katalog: Durchsuchbarer Katalog öffentlich-rechtlicher Sender und Podcasts (ARD Audiothek, Deutschlandfunk etc.). Direkt in der App browsen und hinzufügen statt URLs manuell recherchieren und einfügen
- [ ] Stream-Gesundheitscheck: Mitgelieferte Kinder-Radiosender/Podcasts regelmäßig auf Erreichbarkeit prüfen. URLs können sich ändern — automatisch updaten (via curated Liste aus Repo/Release) oder zum Löschen markieren und Nutzer hinweisen. Gilt auch für manuell hinzugefügte Streams
- [ ] Kategorien/Tags für Bibliothek: Inhalte mit Stimmungen/Anlässen taggen (z.B. Einschlafen, Lieblingshörbuch, Weihnachten, Geburtstag). Schnellzugriff statt durch lange Ordnerlisten scrollen. Muss einfach bleiben — Konzept recherchieren, was für Eltern praktisch ist ohne zu überladen
- [ ] Figur direkt aus Bibliothek verknüpfen: Beim Browsen in der Bibliothek direkt eine Figur/Karte zuordnen können, ohne den Umweg über den Figuren-Wizard
- [ ] Content an mehrere Figuren binden: Gleiches Hörbuch auf zwei oder mehr Karten — z.B. eine fürs Kinderzimmer, eine fürs Auto
- [ ] Vollbackup inkl. Content: Optional alle Audiodateien ins Backup einschließen (nicht nur Config + Kartenzuordnung). Restore muss alles wiederherstellen können. Offene Frage: Merge-Strategie bei Konflikten (bestehende Daten vs. Backup-Daten)
- [ ] Mehrsprachigkeit der Web-App: i18n aktivieren (Grundstruktur ist vorbereitet), Sprachwahl bei Ersteinrichtung und später in Einstellungen änderbar. Deutsch als Default, Englisch als erste Zweitsprache
- [ ] Klopf-Modus als Alternative zu Kipp-Gesten: Accelerometer des MPU6050 für Klopf-Erkennung nutzen (1x, 2x, 3x klopfen = verschiedene Aktionen, ggf. Richtung unterscheidbar). In Einstellungen umschaltbar zwischen Kipp-Modus und Klopf-Modus
- [ ] Gyro-Gesten individuell zuweisbar: Jede der 5 Gesten (Kippen L/R/V/Z, Schütteln) frei mit einer Aktion (Skip, Volume, Play/Pause, Stop, Shuffle, keine) belegbar. Defaults folgen weiter der K8-Kopplung an `card.remove_pauses`. UI als "Erweitert"-Sektion unter Gyro-Einstellungen, damit der Standard-Nutzer nicht überfordert wird.
- [ ] Startup/Shutdown-Sound: Konfigurierbarer Sound beim Hoch- und Herunterfahren, aktivierbar/deaktivierbar in Einstellungen. Eigene Sounds hochladbar. Standard-Sounds mitliefern (lizenzfrei, z.B. von freesound.org/CC0)
- [ ] Kindersicherung für physische Tasten: Lautstärke-Tasten / Skip-Tasten deaktivierbar über App
- [ ] Lautstärke-Schritte: Konfigurierbare Schrittgröße für physische Lautstärke-Knöpfe. Idealerweise intelligent berechnet basierend auf aktuellem Level (unten feinere Schritte, oben gröbere) statt linear
- [ ] Eltern-Dashboard: Übersicht was heute/diese Woche gehört wurde, wie lange. Nutzungsstatistik pro Kind/Figur
- [ ] DRM-freier Import: Klar kommunizieren welche Formate unterstützt werden (MP3, FLAC, OGG, WAV). Hinweis bei DRM-geschützten Dateien
- [ ] Bibliothek sortieren: Drag & Drop für eigene Sortierung + Umschalten zwischen Sortieroptionen (alphabetisch, zuletzt hinzugefügt, Spieldauer)
- [ ] Bibliothek verwalten: Titel innerhalb von Ordnern/Playlists löschen, zwischen Ordnern verschieben, Reihenfolge per Drag & Drop ändern
- [ ] Titel aus Ordner direkt einer Playlist hinzufügen (Kontextmenü / "Zu Playlist hinzufügen")
- [ ] Suche: Freitext über alle Titel, Ordner, Playlists. Schnell finden ohne langes Scrollen
- [ ] Filter: Nach Typ (Musik, Hörbuch, Podcast), nach Figur-Zuordnung (zugeordnet/frei)
- [ ] Playlist aus mehreren Ordnern zusammenstellen: Quick-Add — durch Bibliothek browsen, Titel antippen = hinzugefügt. So einfach wie möglich
- [ ] Warteschlange / "Als nächstes": Spontan einen Titel einschieben ohne Playlist zu ändern
- [ ] Cover-Art: ID3-Tags auslesen und Cover anzeigen. Fallback: Auto-Generierung (Farbe + Initiale) oder eigenes Bild hochladen
- [ ] Ordner umbenennen: Alle Referenzen (cards.content_path, playlist_items) aktualisieren
- [ ] Playlist umbenennen: Backend existiert (rename_playlist()), Frontend-UI fehlt
- [ ] Verknüpfungen über IDs statt Pfade: Ordner-Rename darf keine Zuordnungen zerstören
- [ ] Sleep Timer Countdown im Player: Hinweis + verbleibende Zeit in der Player-Ansicht
- [ ] Metadaten bearbeiten: Titel/Album/Interpret in der App korrigieren
- [ ] Batch-Upload: Mehrere Dateien gleichzeitig hochladen mit Fortschrittsanzeige
- [ ] Ordner hochladen: Ganzes Album auf einmal, Ordnerstruktur beibehalten

- [ ] SD-Karten-Portabilität: SD-Karte zwischen verschiedenen Pi-Modellen wechselbar (z.B. auf Pi Zero W vorbereiten, in Pi 3B+ stecken). Hardware-Wizard erkennt neue Hardware beim Boot und rekonfiguriert automatisch (Audio-Output, RFID-Interface etc.)

## Architektur-Refactorings (aus Senior-Review 2026-04-17, Post-Beta)
- [ ] **InputRouter extrahieren** — GyroService kennt aktuell `card.remove_pauses` (K8-Kopplung) und mappt Gesten auf Playback-Actions selbst. Sobald Buttons, Doppeltipp-RFID oder zukünftige Eingaben dieselbe Kontext-Logik brauchen, duplizierts sich. Sauberer: Gyro emittiert neutrale Gesten (`tilt_forward`, `shake`), ein `InputRouter`/`PlaybackDispatcher` konsumiert alle Input-Quellen und entscheidet kontextabhängig. Macht außerdem das Prio-3-Item "Gyro-Gesten individuell zuweisbar" trivial — nur Dispatcher-Config.
- [ ] **ConfigKeyRegistry als Single Source of Truth** — Heute gibt es drei Orte, die über Config-Keys entscheiden: `config_whitelist.py` (public writable), `backup_service._RESTORE_CONFIG_SKIP_PREFIXES` (backup-ignore), `gyro_service._on_config_changed` (watcher). Keine Stelle kennt die anderen. Vorschlag: Ein zentrales Registry pro Key mit Metadaten (public-writable, backup-policy, watchers, type, range). Whitelist/Skip/Subscription leiten sich daraus ab, Compiler hilft beim Hinzufügen neuer Keys.
- [ ] **Response-Schema-Policy statt Feld-Blanking** — M5 maskiert LAN-Metadaten heute händisch (`d["hostname"] = ""`). Skaliert nicht. Sauberer: Zwei Pydantic-Modelle (`SystemInfoPublic` vs. `SystemInfoFull`), Router wählt Modell per Tier. Grenze dokumentiert sich im Schema statt im Handler. Gilt auch für `/system/hardware` und künftige Diagnose-Endpoints.
- [ ] **JWT-Rotation: Token-in-Response bei PIN-Change** — Aktuell evictet `set_pin()` alle Sessions inklusive der gerade aktiven Wizard-Session. Heute durch Bootstrap-Pass mitigiert, aber fragil. Besser: `set_pin()` gibt optional ein frisches Token zurück; Router reicht es in der Response durch. Client-seitige Session-Recovery wird trivial, Invariante „PIN-Change evictet alles" bleibt explizit.
- [x] **Rate-Limit auf /api/system/restore und /api/auth/login** — Login 5/min, Restore 3/min als eigene Buckets in der bestehenden `RateLimitMiddleware`. Schützt die PBKDF2-CPU-Last und 10 MB-JSON-Parse auf Pi Zero W auch bei richtig-PIN-Hammering. Tests: 2 neue, Bucket-Isolation verifiziert.

## Migrations-Wizard
- [ ] Phoniebox v2/v3 Daten und Karten-Zuordnungen zu Tonado migrieren
- [ ] Audio-Dateien (Symlinks), Karten-Mapping, Hardware-Config, Playlisten
- [ ] Erkennung: /home/pi/RPi-Jukebox-RFID/ vorhanden? Version?
- [ ] Zeitpunkt: Nach v0.2.0-beta

## Prio 4 — Zukunft / Hardware-abhängig
- [ ] Aufnahme über Mikrofon am Pi: USB-Mikro oder I2S MEMS-Mikro (INMP441/SPH0645) anschließen, direkt an der Box aufnehmen statt über Handy-Browser. Karte auflegen + Knopf drücken = aufnehmen
- [ ] Bluetooth-Speaker-Modus: Box als normaler BT-Lautsprecher vom Handy nutzen. ⚠️ BT und WiFi teilen sich den Chip (Pi Zero W, 3B+), BT-Audio (A2DP) + WiFi gleichzeitig = Interferenzen/Stottern. Evtl. nur auf Pi 4/5 sinnvoll oder mit USB-BT-Dongle
- [ ] BT-Kopfhörer-Unterstützung: Kabellose Kopfhörer mit der Box koppeln. Separate Kopfhörer-Lautstärkegrenze (Gehörschutz). ⚠️ Gleiche HW-Einschränkung wie BT-Speaker. Braucht PulseAudio/PipeWire zwischen MPD und ALSA — verkompliziert Audio-Pipeline
- [ ] NFC-Smartphone-Interaktion: RFID-Reader erkennt Smartphone (NFC/HCE auf 13,56 MHz). Use Cases: (a) Ersteinrichtung ohne PIN — Handy auflegen = vertraut, physische Nähe als Auth, (b) Gastmodus — Besucherkind legt Handy auf → eingeschränkter Zugriff, (c) BT-Speaker/Streaming aktivieren — Handy auflegen schaltet Box in BT-Modus, (d) Handsfree-Steuerung durch physische Geste statt App. ⚠️ iPhone-HCE stark eingeschränkt, Android braucht native App (kein reines PWA)
- [ ] Multiroom / Sync-Play: Mehrere Boxen über LAN koppeln, gleichen Content synchron abspielen
- [ ] Nachtlicht-Steuerung: Falls LED angeschlossen (GPIO), Farbe/Helligkeit über App steuerbar
- [ ] Mehrere Boxen in einer App verwalten: Haushaltsmodus — eine App steuert mehrere Tonado-Boxen (z.B. Kinderzimmer + Wohnzimmer)
