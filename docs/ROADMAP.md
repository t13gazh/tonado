# Tonado — Roadmap

## Meilenstein 1: Funktionsfähige Musikbox

**Ziel:** Karte auflegen → Musik spielt. Eltern steuern vom Smartphone. Hardware-Wizard konfiguriert alles.

### Phase 1: Kern-Backend
> Nach dieser Phase: Tonado-Service läuft auf dem Pi, spielt Musik via MPD, erkennt RFID-Karten, reagiert auf Gyro-Gesten.

- Player Service (MPD direkt via python-mpd2 async)
- Card Service (RFID-Reader Auto-Detection: RC522/PN532/USB)
- Gyro Service (MPU6050 integriert)
- Config Service (SQLite WAL)
- Event Bus (asyncio, in-process)
- FastAPI Grundgerüst mit WebSocket Hub

### Phase 2: Hardware-Wizard & Setup
> Nach dieser Phase: Pi bootet, öffnet Captive Portal, Wizard erkennt Hardware, WiFi verbunden, System bereit.

- Captive Portal (hostapd + dnsmasq)
- Hardware Auto-Detection (Pi-Modell, RFID, Audio, Gyro, GPIO)
- WiFi-Konfiguration via Browser
- Erster-Boot-Erlebnis mit geführter Karten-Zuweisung
- systemd Service-Integration

### Phase 3: Web-App (Player & Bibliothek)
> Nach dieser Phase: Eltern öffnen App am Smartphone, sehen Player mit Cover Art, browsen Bibliothek, spielen Musik ab.

- Svelte 5 + SvelteKit Projekt (adapter-static)
- Player-Ansicht (Now Playing, Controls, Volume, Progress, Cover Art)
- Bibliothek (Cover-Grid, Liste, Suche, Filter)
- WebSocket-Integration (Echtzeit Player-State)
- i18n (Deutsch default, Englisch vorbereitet)
- Bundle-Budget: < 150 KB gzipped

### Phase 4: Karten-Management
> Nach dieser Phase: Eltern scannen Karte, wählen Inhalt, Karte ist sofort nutzbar. Card Wall zeigt alle Zuweisungen.

- Karten-Wizard (Scan → Auswahl → Fertig)
- Card Wall (alle Karten als Grid mit Covers)
- Karte bearbeiten / löschen
- Karte → Ordner, Stream-URL, oder System-Kommando

### Phase 5: Content & Streams
> Nach dieser Phase: Musik-Upload via Browser, Podcast-Feeds, Internetradio, ARD Audiothek-Streams nutzbar.

- File-Upload (Chunked, resumierbar, mit Fortschritt)
- Ordner-/Playlist-Verwaltung
- Cover-Art Zuweisung
- Stream Service (Internetradio URLs)
- Podcast-Feeds (RSS, Auto-Download)
- Vorkonfigurierter Katalog (deutsche Kindersender)

### Phase 6: Eltern-Einstellungen & Sicherheit
> Nach dieser Phase: PIN-geschützte Bereiche, Lautstärke-Limit, Einschlaftimer, Zugriffssteuerung aktiv.

- PIN-basierte Authentifizierung (Offen/Eltern/Experte)
- Maximale Lautstärke
- Einschlaftimer
- Startup-Volume
- Idle-Shutdown
- Hörbuch-Fortschritt pro Karte (Resume)

### Phase 7: System & Stabilität
> Nach dieser Phase: Updates via Web-App, Backup/Restore, Read-Only Filesystem, stabil im Dauerbetrieb.

- Update-Mechanismus (via Web-App, kein SSH)
- Backup/Export (Config + Karten-Zuweisungen)
- Restore/Import
- OverlayFS (Read-Only Root)
- Watchdog (Auto-Recovery bei Abstürzen)
- System-Info, Restart, Shutdown im Experten-Bereich

### Phase 8: PWA & Polish
> Nach dieser Phase: App zum Homescreen hinzufügen, Offline-fähig, Performance optimiert.

- Service Worker (Offline-Cache für App-Shell)
- PWA Manifest + Icons
- Performance-Optimierung (Pi Zero W Target)
- Accessibility-Audit ("Leichte Sprache")
- Dokumentation für Endanwender

## Meilenstein 2: Erweiterungen (Zukunft)

- Spotify Connect (Box als Receiver)
- AirPlay / Chromecast Receiver
- TeddyCloud / TAF-Kompatibilität
- BLE-Provisioning (WiFi-Setup via App)
- 3D-Druck-Gehäuse-Vorlagen
- LED-Ring Integration
- Display-Support (E-Ink oder kleines LCD)
- Community-Plugin-System
- Englische Dokumentation
- Pi-Image zum direkten Flashen (pi-gen)

## Prinzipien für die Umsetzung

1. **Jede Phase ist eigenständig testbar.** Nach Phase 1+2 funktioniert die Box über die Kommandozeile. Nach Phase 3 über den Browser.
2. **Pi Zero W ist immer der Performance-Test.** Wenn es dort läuft, läuft es überall.
3. **Keine Phase ohne Hardware-Validierung.** Code wird auf dem echten Pi getestet, nicht nur im Unit-Test.
4. **UX vor Features.** Lieber weniger Features die perfekt funktionieren als viele halbgare.
