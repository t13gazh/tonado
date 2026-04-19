# Changelog

Alle nennenswerten Änderungen an Tonado werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Doku

- **Doku-Review Phase 1 (Quickfixes):** README-Tippfehler „Musik hört los" → „Musik spielt" korrigiert, RFID-Jargon im User-Text auf einmalige technische Einführung reduziert, ROADMAP „Watchdog" und „Leichte Sprache" ehrlich als verschoben/Basis-A11y markiert, Spotify-Eintrag als reiner Receiver-Modus geschärft (Vision-konform), installation.md um Schritt 12 für OnOff-SHIM-Kernel-Overlays erweitert und `curl | sudo bash`-Alternative mit Inspect-Pfad ergänzt, Bonjour-Windows-Link direkt auf Apple statt iTunes-Verweis, hardcoded `/home/pi/`-Pfad als `/home/<benutzer>/` verallgemeinert, hardware.md um 2-Satz-Erklärung zur GPIO-25-Doppelnutzung (RC522 RST + HifiBerry Amp-Enable) + PN532-I2C-Adresse ergänzt, UPDATE.md „nur main"-Hinweis als Alpha-Phase-Begründung eingeordnet, BACKUP.md Einleitungssatz entreissend umformuliert, Pi-Zero-W-Teststatus als „Installation auf 0.1.0-alpha verifiziert, für 0.2.x nicht re-getestet" präzisiert.
- **Doku-Review Phase 2 (Struktur):** `docs/`-Tree nach Zielgruppen getrennt — `docs/fuer-eltern/` (BACKUP, UPDATE), `docs/fuer-bastler/` (installation, hardware), `docs/fuer-entwickler/` (ARCHITEKTUR, ROADMAP, UI-GUIDELINES, entwicklung), `docs/archive/` (PRE-BETA-AUDIT). VISION.md bleibt top-level. BACKLOG.md aufgesplittet: aktive Produkt-Prios + bekannte Bugs + offene Beta-Blocker + Architektur-Refactorings bleiben, erledigte Audit-Items (Pre-Beta, Security, E2E, A11y, i18n, Test-Coverage, Architektur, Setup-Wizard-Erledigtes) in neue Historie-Datei `docs/archive/pre-beta-audit-findings.md` ausgelagert. README bekommt Zielgruppen-Navigationsblock. Alle internen Doku-Links (README, CONTRIBUTING, SECURITY, entwicklung.md, ROADMAP.md, installation.md, archive/README.md) auf neue Pfade aktualisiert.
- **Doku-Review Phase 3 (Content):** Neue Eltern-lesbare Feature-Übersicht (`docs/fuer-eltern/features.md`) — was Tonado heute kann, was bald kommt, was denkbar ist. VISION.md „Kein Bluetooth-Speaker" geschärft: Box als Receiver-Ziel (Spotify/AirPlay) explizit vom eigenen Player abgegrenzt. Bluetooth-Speaker-Backlog-Item erhält Vision-Konflikt-Notiz. Neue Datei `docs/fuer-entwickler/install-strategy.md` dokumentiert den Weg von „heute: SSH + curl|bash für technik-affine Eltern" zu „Ziel: Pi-Image zum Flashen" und benennt die Lücke zur Vision ehrlich. README-Status-Block geschärft: Alpha ist aktuell nur für technik-affine Eltern, Pi-Image ist Beta-Ziel. Pi-Image als Prio-3-Backlog-Item hinzugefügt, Cross-Referenz zur Install-Strategie.

### Hinzugefügt

- **Cover-Art im Player und in der Bibliothek:** Bilder aus ID3-Tags (MP3, FLAC, OGG, MP4, WMA) oder einer `cover.jpg`/`cover.png` im Ordner werden automatisch angezeigt. Fallback: farbige Kachel mit Anfangsbuchstabe.
- **Suche in der Bibliothek:** Freitext-Suche über alle vier Tabs (Ordner, Radio, Podcasts, Playlisten) mit Tab-Treffer-Zählern und Umlaut-/Diacritic-toleranter Suche ("uber" findet "Über").
- **Sleep-Timer-Countdown im Player:** Verbleibende Zeit erscheint dezent zwischen Fortschrittsbalken und Wiedergabe-Steuerung. Wechselt unter einer Minute auf Sekunden-Takt und färbt sich in der letzten Minute warm.

### Verbessert

- **Player-Layout auf kleinen Smartphones:** Safe-Area-Handling (Notch / Dynamic Island), flexibles Cover-Sizing (skaliert mit Viewport), Landscape-Modus und sanftere Druck-Feedbacks an allen Bedienelementen. Kein Abschneiden mehr oben/unten auf iPhone SE, kleineren Android-Geräten oder im Querformat.
- **Banner-Einblendung:** Gesundheits-Banner (Backend-Offline, MPD-Trennung, Speicher-Warnung) gleiten jetzt sanft ein statt instant aufzupoppen — Verhalten respektiert `prefers-reduced-motion`.

### Infrastruktur (Entwickler)

- **Doku-Disziplin per Hook:** Neuer Git-Pre-Commit-Hook (`scripts/hooks/pre-commit`, Installation via `scripts/install-hooks.sh`) blockiert `feat:`/`fix:`-Commits, die Source unter `core/` oder `web/src/` ändern, aber keinen Eintrag in `CHANGELOG.md` mitbringen. Dazu Claude-PostToolUse-Reminder bei Source-Edits. Bypass `SKIP_DOC_CHECK=1 git commit …` für begründete Ausnahmen.

## [0.2.1-alpha] — 2026-04-08

### Hinzugefügt

- **OnOff SHIM:** Sauberes Ein-/Ausschalten per Taster. Kernel-Overlays für GPIO 17 (Button) und GPIO 4 (Power-Off). Wird vom Install-Script automatisch konfiguriert.

### Verbessert

- **Update-Dialog:** Zeigt jetzt verständliche Änderungsübersicht statt technischer Commit-Hashes. Bei fehlenden Changelog-Einträgen werden Commit-Beschreibungen als Fallback angezeigt.
- **Backup-Export:** Nutzt jetzt Auth-Token (behebt 403-Fehler wenn Eltern-PIN gesetzt ist).
- **Backup-Version:** Dynamisch aus pyproject.toml statt fest auf "0.1.0".

## [0.2.0-alpha] — 2026-04-08

### Hinzugefügt

- **Bibliothek-Schutz:** Upload, Ordner erstellen und Löschen erfordern Eltern-PIN (wenn gesetzt). Login-Sheet erscheint inline bei geschützten Aktionen.
- **Auth-Store:** Automatischer Logout nach 5 Minuten Inaktivität.
- **Spezifische Upload-Fehler:** Zu große Dateien (413) und fehlende Berechtigung (403) werden klar benannt.
- **CHANGELOG.md:** Eingeführt ab diesem Release.

### Behoben

- **RFID-Erkennung:** RC522 Receiver Gain auf 33 dB erhöht (Chip-Default 18 dB war zu niedrig für zuverlässige Kartenlesung).
- **Startup-Reihenfolge:** PlaybackDispatcher wird vor Service-Start registriert — erste Karte nach dem Booten wird jetzt erkannt.
- **Nginx Upload-Limit:** Von 1 MB auf 500 MB erhöht (Audio-Dateien wurden beim Upload abgelehnt).
- **Install-Script:** Schritt-Nummerierung korrigiert (1/11 durchgängig).

## [0.1.0-alpha] — 2026-03-28

Erster funktionsfähiger Release. Alle 8 Meilenstein-1-Phasen implementiert.

### Enthalten

- Player mit MPD-Steuerung, Cover Art, Fortschrittsanzeige
- Bibliothek: Ordner, Internetradio, Podcasts, Playlisten
- Figuren-Wizard: RFID-Karte scannen und Inhalt zuweisen
- Eltern-Einstellungen: PIN, Lautstärkelimit, Sleep-Timer mit Fade-Out
- Hardware-Erkennung: RC522 (SPI), PN532 (I2C), USB-RFID-Reader
- Gesten-Steuerung: Kippen, Schütteln (MPU6050)
- GPIO-Button-Erkennung: Interaktiver Scan
- Setup-Wizard: 6 Schritte, Re-Run-sicher
- PWA: Service Worker, Offline-Cache, Homescreen-fähig
- Auto-Updates, Backup/Restore, OverlayFS-Vorbereitung
- 113 Backend-Tests, 1.3 MB Frontend (gzipped)

[0.2.1-alpha]: https://github.com/t13gazh/tonado/compare/v0.2.0-alpha...v0.2.1-alpha
[0.2.0-alpha]: https://github.com/t13gazh/tonado/compare/v0.1.0-alpha...v0.2.0-alpha
[0.1.0-alpha]: https://github.com/t13gazh/tonado/releases/tag/v0.1.0-alpha
