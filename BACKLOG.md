# Backlog

> **UX-Leitlinie:** So einfach wie möglich. Kein überladenes UI. Besser als alle anderen Apps. Layouts testen, ausprobieren, verwerfen, umbauen — bis Nutzer sagen: "Das ist durchdacht, das sieht geil aus."

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
- [ ] Audio-Setup sendet falsche Device-Kennung (`AudioStep.svelte:21`)

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
- [ ] Placeholder "Die drei ???, Folge 1" als i18n-Key (`wizard:145`, `CardStep:139`)
- [x] ~20 unbenutzte Keys identifiziert (player.now_playing, library.search, wizard.select_track etc.) — behalten für geplante Features (Suche, Track-Auswahl, OverlayFS-UI)

## Test-Coverage (2026-03-29)
- [x] MockMPDClient erstellt (`tests/mock_mpd.py`) — simuliert python-mpd2 async Interface
- [x] PlayerService Tests: 21 Tests (Playback, Volume, Seek, Shuffle, Repeat, Outputs, Disconnected)
- [x] PlaybackDispatcher Tests: 10 Tests (Folder, Stream, Podcast, Playlist, Command, Gestures, Resume)
- [x] TimerService Tests: 6 Tests (Sleep Timer, Volume Enforcement, Resume)
- [x] Router-Integrationstests: 12 Tests (Auth-Middleware, Path Traversal, Rate Limiting, Validation, Sensitive Keys)

## v0.2.0-beta — Nächste Schritte
- [ ] Hardware-Resilience: Graceful Degradation wenn Hardware fehlt/falsch
- [ ] Figuren-UI + Einstellungen + System-Seite testen und fixen
- [ ] Captive Portal / Setup-Wizard Ersteinrichtungs-Flow
- [ ] SD-Karte >= 16 GB, Install-Script End-to-End testen
- [ ] Pi-Test mit echter Hardware (RFID, Gyro)
- [ ] Performance-Optimierung für Pi Zero W (siehe Architektur-Audit unten)
- [ ] README.md mit Installationsanleitung für Endnutzer
- [ ] Hardcoded Strings → i18n
- [ ] Error-Boundaries und User-freundliche Fehlermeldungen

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
- [ ] Loading-Heuristik fragil: Explizites Flag statt duration/elapsed Berechnung (`player_service.py`) — funktioniert aktuell für normale Fälle, explizites Flag wäre robuster
- [x] scan_waiters Leak: finally-Block für Future-Cleanup bei Request-Abbruch (`card_service.py:260`)

## Setup-Wizard
- [ ] Audio Test-Button (Sound abspielen zum Prüfen)
- [ ] WiFi Passwort-Toggle (Auge-Icon)
- [ ] OnOffShim-Erkennung, GPIO-Buttons (Lautstärke, An/Aus)
- [ ] Hilfe/Troubleshooting als Popup aus Git-Docs laden

## Prio 1 — Kernfunktionen
- [ ] Sleep-Timer mit Fade-Out: Lautstärke sanft runterfahren statt abrupt stoppen
- [ ] Auto-Fallback auf AP-Modus: Wenn bekanntes WLAN nicht erreichbar (z.B. Box bei Oma, im Auto), nach Timeout automatisch eigenen AP aufspannen. Handy kann sich verbinden und Box wieder steuern/neues WLAN konfigurieren. Musik spielt offline weiter, nur App-Zugriff wäre sonst verloren

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
