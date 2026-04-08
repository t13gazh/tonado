# Changelog

Alle nennenswerten Änderungen an Tonado werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [0.2.1-alpha] — 2026-04-08

### Verbessert

- **Update-Dialog:** Zeigt jetzt verständliche Änderungsübersicht statt technischer Commit-Hashes. Änderungen werden aus dem Changelog gelesen.

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
