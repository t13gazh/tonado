# Changelog

Alle nennenswerten Änderungen an Tonado werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Hinzugefügt

- **pi-gen Stage `scripts/pi-gen-stage/stage-tonado/`.** Infrastruktur, um ein Tonado-Image lokal mit pi-gen zu bauen — 10 Stage-Dateien inkl. Package-Liste, systemd-Unit-Symlinks aus dem Repo, Boot-Overlays (SPI, I2C, OnOff SHIM), First-Boot-Service und Install-Marker. Vorbereitung auf flashbare Images für nicht-technische Eltern (Backlog Prio 3).
- **First-Boot-Service `firstrun.service` + `firstrun.sh`.** Läuft beim allerersten Start, rotiert SSH-Host-Keys vor `sshd`-Start, erzeugt gerätespezifisches JWT-Secret, richtet Git-Trust für den pi-User ein. Idempotent, markiert sich nach Erfolg als erledigt.
- **Imager-WLAN-Probe `imager-wifi-probe.service`.** Beim Boot prüft die Box 20 Sekunden lang, ob die im Raspberry Pi Imager hinterlegten WLAN-Daten tragen. Klappt’s: kein Setup-WLAN. Klappt’s nicht: Setup-WLAN geht auf, Eltern korrigieren per Browser ohne neu zu flashen.
- **Setup-Wizard-Abschluss mit Dual-WLAN und QR-Code.** Beim letzten Schritt probiert die Box das Heim-WLAN, ohne das Setup-WLAN abzureißen. Der Browser bleibt erreichbar, während das Handy aufs Heim-WLAN wechselt — die Seite findet die Box automatisch wieder, QR-Code als Handy-Fallback, iOS-Hinweise für Safari, gestufte Rückmeldungen nach 30 s / 60 s / 90 s, harter Stop nach 5 min.
- **API-Endpoints `POST /api/setup/test-wifi`, `POST /api/setup/confirm-complete`, `POST /api/setup/cancel-probe`.** Einmal-Token-Guard auf `confirm-complete`, 10-Versuch-Lockout gegen Brute-Force, Rate-Limit-Bucket `wifi_probe` (6/min).
- **Reset ohne Auth solange kein Experten-PIN existiert.** Wenn die Box mitten im Setup steckt und der User nicht weiterkommt, ist `/api/setup/reset` offen — verhindert, dass Eltern die Box durch einen Abbruch verloren sind.

### Verbessert

- **sudoers.d/tonado erweitert** um AP-Teardown-Rechte (systemctl stop/disable tonado-ap, nmcli general reload, Löschen der NetworkManager-Unmanaged-Config). Nach dem Setup kann die Box den Setup-Modus sauber abschalten.
- **CSP und CORS im Setup-Modus aufgelockert.** Nur solange die Ersteinrichtung offen ist, darf der Browser quer über die Setup-WLAN- und mDNS-Adressen gehen; sobald `.setup-complete` existiert, greift wieder die strenge Policy.
- **Pre-Commit-Hook fängt 0-Byte-Müll-Dateien im Repo-Root.** Shell-Fragment-Artefakte (Klammern, Python-Literals) landen nicht mehr versehentlich im Commit. Bypass via `SKIP_JUNK_CHECK=1`.

### Behoben

- **Gesundheits-Endpoint-Test auf aktuelle Version synchronisiert** (stand noch auf `0.2.1-alpha`).

## [0.3.1-beta] — 2026-04-23

Update-Härtungs-Welle: Auto-Update-Pfad wird zuverlässig, vier Sicherheits-Findings geschlossen, inline Progress-UI im Update-Dialog.

### Wichtig beim Upgrade von 0.3.0-beta

Diese Version behebt einen Bug im Auto-Update-Pfad, der genau in 0.3.0-beta steckt. Das heißt: der Weg „in der App auf Nach Updates suchen klicken und installieren" kann auf einem Pi Zero W oder frisch aufgesetzten Pi 3B+ noch stolpern, weil er die alte (fehlerhafte) Update-Pipeline durchläuft.

**Einmaliger Umweg:** Per SSH auf die Box, dann

```bash
curl -sSL https://raw.githubusercontent.com/t13gazh/tonado/main/system/install.sh | sudo bash
```

Danach läuft „Nach Updates suchen" zuverlässig aus der App — für alle weiteren Updates reicht der App-Weg.

Wer bereits auf Pi 4 / Pi 5 oder einem Pi 3B+ mit gecachten Python-Wheels ist, kann das Update über die App versuchen; klappt es dort nicht sauber, deckt der SSH-Weg oben dasselbe ab.

### Behoben

- **Auto-Update auf dem Pi bleibt nicht mehr stecken.** Bei großen Installationen lief der Update-Versuch vorher still in einen Rollback, der Status blieb unklar. Der Update-Dialog zeigt jetzt live: „Wird installiert → Neustart → Prüfung → Auf vX.Y.Z aktualisiert". Bei „Box antwortet noch nicht" gibt es zwei klare Optionen: Seite neu laden oder erneut versuchen. „Box ist bereits aktuell" meldet sich explizit statt stummer Bestätigung.
- **Update-Check schont die SD-Karte.** „Nach Updates suchen" ist auf 6 Versuche pro Minute begrenzt — reicht für normales Nutzen, blockiert automatische Schleifen.
- **Browser-Cache hält Update-Status nicht mehr fest.** Nach einer Update-Installation sieht man den neuen Stand sofort, kein manuelles „Cache leeren" mehr nötig.

### Sicherheit

- **Box läuft mit minimalen Root-Rechten.** Das Install-Script legt jetzt eine exakte sudo-Regel für nur drei Kommandos an (Neustart, Herunterfahren, Reboot) und entfernt die Raspberry-Pi-Standard-Pauschalregel. Der interne API-Port ist nur noch lokal auf der Box erreichbar, der Zugang läuft ausschließlich über den Web-Server.

### Für Entwickler

- `core/services/system_service.py::_apply_update_unlocked`: pip `async_run(timeout=600)`, HEAD-Bewegung per `rev-parse` verifiziert (`no_changes`-Shortcut), rc-Checks auf reset/clean/pull, strukturiertes Logging an jedem Hauptschritt, `new_commit_hash` in der Apply-Response damit der Client pollen kann.
- `core/utils/subprocess.py`: `await proc.wait()` nach `proc.kill()` bei Timeout — vermeidet Zombie-PIDs auf Pi Zero W.
- `core/utils/rate_limit.py`: Dedizierter 6/min-Bucket für `/api/system/update/check` vor dem `_SAFE_METHODS`-Exempt, Trailing-Slash-Normalisierung (`path.rstrip("/")`), 429-Body lokalisiert.
- `core/routers/system.py`: Custom `APIRoute`-Klasse stempelt `Cache-Control: no-store, no-cache, must-revalidate` auch auf `HTTPException`-Pfaden. Angewendet auf `/info`, `/health`, `/update/check`, `/update/apply`.
- `system/install.sh` + `system/sudoers.d/tonado`: Visudo-validierter Drop-in mit exakten `/usr/bin/systemctl`, `/usr/sbin/shutdown`, `/usr/sbin/reboot`-Pfaden (Bookworm-usrmerge), Platzhalter `%TONADO_USER%` via `sed` gefüllt. `/etc/sudoers.d/010_pi-nopasswd` wird nach erfolgreicher Validierung entfernt.
- `system/tonado.service` + `system/install.sh`: Uvicorn bindet auf `127.0.0.1:8080`; Nginx-Upstream unverändert.
- Frontend: Phase-basierter Update-State, Poll auf `/api/system/info`, `AbortSignal.timeout(3000)` pro Request, `onDestroy`-Cleanup mit Timer-Refs und `componentAlive`-Flag, ARIA-Live-Region, 429-Handler in `api.ts`, 7 neue i18n-Keys DE/EN.
- Tests: 9 neue Backend-Cases (pip-Timeout-Rollback, Already-up-to-date, Pre-Pull-Reset-Abort, Rollback-Reset-Log, Rate-Limit-Bucket, Per-IP-Isolation, Polling-GET-Exempt, no-store auf 403, Trailing-Slash-Bucket). Gesamt: 411 grün.

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

[0.3.1-beta]: https://github.com/t13gazh/tonado/compare/v0.3.0-beta...v0.3.1-beta
[0.3.0-beta]: https://github.com/t13gazh/tonado/compare/v0.2.1-alpha...v0.3.0-beta
[0.2.1-alpha]: https://github.com/t13gazh/tonado/compare/v0.2.0-alpha...v0.2.1-alpha
[0.2.0-alpha]: https://github.com/t13gazh/tonado/compare/v0.1.0-alpha...v0.2.0-alpha
[0.1.0-alpha]: https://github.com/t13gazh/tonado/releases/tag/v0.1.0-alpha
