# Tonado — Roadmap

## Meilenstein 1: Funktionsfähige Musikbox ✓

**Ziel:** Karte auflegen → Musik spielt. Eltern steuern vom Smartphone. Hardware-Wizard konfiguriert alles.

**Status:** Alle 8 Phasen implementiert (2026-03-28). Läuft auf Pi Zero W mit RC522 RFID und HifiBerry MiniAmp.

### Phase 1: Kern-Backend ✓
> Nach dieser Phase: Tonado-Service läuft auf dem Pi, spielt Musik via MPD, erkennt RFID-Karten, reagiert auf Gyro-Gesten.

- Player Service (MPD direkt via python-mpd2 async)
- Card Service (RFID-Reader Auto-Detection: RC522/PN532/USB)
- Gyro Service (MPU6050 integriert)
- Config Service (SQLite WAL)
- Event Bus (asyncio, in-process)
- FastAPI Grundgerüst mit WebSocket Hub

### Phase 2: Hardware-Wizard & Setup ✓
> Nach dieser Phase: Pi bootet, öffnet Captive Portal, Wizard erkennt Hardware, WiFi verbunden, System bereit.

- Captive Portal (hostapd + dnsmasq)
- Hardware Auto-Detection (Pi-Modell, RFID, Audio, Gyro, GPIO)
- WiFi-Konfiguration via Browser
- Erster-Boot-Erlebnis mit geführter Karten-Zuweisung
- systemd Service-Integration

### Phase 3: Web-App (Player & Bibliothek) ✓
> Nach dieser Phase: Eltern öffnen App am Smartphone, sehen Player mit Cover Art, browsen Bibliothek, spielen Musik ab.

- Svelte 5 + SvelteKit Projekt (adapter-static)
- Player-Ansicht (Now Playing, Controls, Volume, Progress, Cover Art)
- Bibliothek (Cover-Grid, Liste, Suche, Filter)
- WebSocket-Integration (Echtzeit Player-State)
- i18n (Deutsch default, Englisch vorbereitet)
- Bundle-Budget: < 150 KB gzipped

### Phase 4: Karten-Management ✓
> Nach dieser Phase: Eltern scannen Karte, wählen Inhalt, Karte ist sofort nutzbar. Card Wall zeigt alle Zuweisungen.

- Karten-Wizard (Scan → Auswahl → Fertig)
- Card Wall (alle Karten als Grid mit Covers)
- Karte bearbeiten / löschen
- Karte → Ordner, Stream-URL, oder System-Kommando

### Phase 5: Content & Streams ✓
> Nach dieser Phase: Musik-Upload via Browser, Podcast-Feeds, Internetradio, ARD Audiothek-Streams nutzbar.

- File-Upload (Chunked, resumierbar, mit Fortschritt)
- Ordner-/Playlist-Verwaltung
- Cover-Art Zuweisung
- Stream Service (Internetradio URLs)
- Podcast-Feeds (RSS, Auto-Download)
- Vorkonfigurierter Katalog (deutsche Kindersender)

### Phase 6: Eltern-Einstellungen & Sicherheit ✓
> Nach dieser Phase: PIN-geschützte Bereiche, Lautstärke-Limit, Einschlaftimer, Zugriffssteuerung aktiv.

- PIN-basierte Authentifizierung (Offen/Eltern/Experte)
- Maximale Lautstärke
- Einschlaftimer
- Startup-Volume
- Idle-Shutdown
- Hörbuch-Fortschritt pro Karte (Resume)

### Phase 7: System & Stabilität ✓
> Nach dieser Phase: Updates via Web-App, Backup/Restore, Read-Only Filesystem, stabil im Dauerbetrieb.

- Update-Mechanismus (via Web-App, kein SSH)
- Backup/Export (Config + Karten-Zuweisungen)
- Restore/Import
- OverlayFS (Read-Only Root) — opt-in hinter Config-Flag
- System-Info, Restart, Shutdown im Experten-Bereich

> **Verschoben auf Post-Beta:** Hardware-Watchdog mit systemd-notify-Integration (siehe BACKLOG K7).

### Phase 8: PWA & Polish ✓
> Nach dieser Phase: App zum Homescreen hinzufügen, Offline-fähig, Performance optimiert.

- Service Worker (Offline-Cache für App-Shell)
- PWA Manifest + Icons
- Performance-Optimierung (Pi Zero W Target)
- Accessibility-Audit (Basis-A11y: ARIA, Focus, Kontrast — "Leichte Sprache" bleibt im Backlog für Post-Beta)
- Dokumentation für Endanwender

## Meilenstein 1.5: Beta-Readiness (v0.2.x → v0.2.0-beta)
> Pre-Beta-Härtung. Referenz: [`PRE-BETA-AUDIT.md`](PRE-BETA-AUDIT.md). Kein neues Feature, nur Qualität.

- **Security-Härtung** (Phase 1): Auth-Lockdown nach Setup, X-Real-IP hinter nginx, Path-Traversal auf `/play-folder`, Captive-Portal WPA2 + Timeout, Watchdog entschärft, Tier-Checks, globales Rate-Limit, sanitized Error-Responses. ✅ erledigt
- **Update-Härtung** (Phase 2): `asyncio.Lock` + pip-Rollback + Tests für `/update/apply`, `/update/check` PARENT-gated. ✅ erledigt
- **Test-Coverage** (Phase 3): playlist/button/websocket/gyro_service Service-Tests, parametrisierter Auth-Matrix-Test, 2s-Cooldown-Test. ✅ erledigt
- **Captive-Portal + Install E2E** (Phase 4): First-Boot-Flow auf 3 SD-Images, Install-Script Idempotenz, nginx-Limits für Zero W. ⏳ braucht Hardware
- **Doku + Aufräumen** (Phase 5): CONTRIBUTING, SECURITY, UPDATE, BACKUP, Audit-Archiv, Pi-Kompatibilitätsmatrix. ✅ erledigt
- **Product-Decisions** (Phase 6): Gyro Tilt-forward/back (Volume vs. play_pause). ⏳ braucht User
- **WLAN-Rettung** (Post-Audit): `ConnectivityMonitor` startet das bestehende Captive Portal automatisch, wenn das Heim-WLAN anhaltend nicht erreichbar ist. Eltern-UI mit AP-Credentials + druckbarem QR-Code. ✅ erledigt (Live-Test auf Pi offen)

## Meilenstein 2: Erweiterungen (Zukunft)

> **Leitplanke:** Tonado bleibt eine Kinder-Musikbox, kein Smart-Home-Hub (siehe [VISION](VISION.md#was-tonado-nicht-ist)). Erweiterungen, die das Kernerlebnis „Figur auflegen → Musik spielt" erweitern, nicht ersetzen.

- Spotify Connect — **nur als Receiver** (Box erscheint in der Spotify-App als Abspielziel). Keine Spotify-Player-Logik in Tonado selbst.
- AirPlay / Chromecast — ebenfalls Receiver-Modus
- TeddyCloud / TAF-Kompatibilität (Import fremder Figur-Zuordnungen)
- BLE-Provisioning (WiFi-Setup via App statt Captive Portal)
- 3D-Druck-Gehäuse-Vorlagen
- LED-Ring Integration
- Display-Support (E-Ink oder kleines LCD)
- Community-Plugin-System
- Englische Dokumentation
- Pi-Image zum direkten Flashen (pi-gen) — **Kernziel für nicht-technische Eltern**

## Prinzipien für die Umsetzung

1. **Jede Phase ist eigenständig testbar.** Nach Phase 1+2 funktioniert die Box über die Kommandozeile. Nach Phase 3 über den Browser.
2. **Pi Zero W ist immer der Performance-Test.** Wenn es dort läuft, läuft es überall.
3. **Keine Phase ohne Hardware-Validierung.** Code wird auf dem echten Pi getestet, nicht nur im Unit-Test.
4. **UX vor Features.** Lieber weniger Features die perfekt funktionieren als viele halbgare.
