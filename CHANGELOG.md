# Changelog

Alle nennenswerten Änderungen an Tonado werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

## [0.3.0-beta] — 2026-04-22

Erste Beta — aus der Alpha-Linie promoviert, nachdem Pi 3B+ und Pi Zero W auf frischer Hardware live verifiziert sind, 398 Backend-Tests grün sind und die wichtigsten UX-Polishs + Konsistenz-Fixes drin sind.

### Was du merkst

- Sleep-Timer zeigt die Restzeit direkt im Player, plus Verlängern um 5 oder 10 Minuten.
- Cover-Bilder in Player und Bibliothek — aus den Musik-Dateien oder aus einer cover.jpg im Ordner.
- Suche in der Bibliothek: ein Feld findet über Ordner, Radio, Podcasts und Playlisten gleichzeitig.
- Browser-Audio bleibt beim Figuren-Wechsel stabil, kein Abbrechen mehr bei jedem Stream.
- PIN-Eingabe im Setup mit vier einzelnen Ziffern-Boxen, springt automatisch zur nächsten Zeile.
- Hilfe-Taste in jedem Setup-Schritt mit Tipps fürs Troubleshooting.
- WLAN-Rettung: fällt dein Heim-WLAN länger aus, öffnet die Box automatisch ihren Einrichtungs-Modus mit QR-Code.
- Figuren-Löschen nur noch im aufgeklappten Detail — kein versehentliches Tippen mehr auf der Kachel.
- Einheitliches Aussehen bei Fehlermeldungen, Auswahl-Leisten und Schaltern in allen Einstellungen.

Deine Figuren, Einstellungen und Musik bleiben beim Update erhalten.

### Für Entwickler

Detaillierte Änderungs-Historie zwischen v0.2.1-alpha und v0.3.0-beta: siehe Git-Commits (`git log v0.2.1-alpha..v0.3.0-beta --oneline`). Das vorherige, ausführliche Release-Notes-Format war zu Dev-lastig für den Update-Dialog und wurde mit v0.3.0-beta auf `WAS-IST-NEU.md` als primäre Quelle umgestellt.


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

[0.3.0-beta]: https://github.com/t13gazh/tonado/compare/v0.2.1-alpha...v0.3.0-beta
[0.2.1-alpha]: https://github.com/t13gazh/tonado/compare/v0.2.0-alpha...v0.2.1-alpha
[0.2.0-alpha]: https://github.com/t13gazh/tonado/compare/v0.1.0-alpha...v0.2.0-alpha
[0.1.0-alpha]: https://github.com/t13gazh/tonado/releases/tag/v0.1.0-alpha
