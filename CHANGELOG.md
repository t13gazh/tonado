# Changelog

Alle nennenswerten Änderungen an Tonado werden hier dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.1.0/).
Versionierung folgt [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

### Behoben

- **Player-Seite scrollt nicht mehr auf kleinen Smartphones.** Das Doppel-Polster unten (Safe-Area + Nav-Höhe gleichzeitig) ist raus, die Controls rutschen nicht mehr hinter die untere Leiste und das Cover wird oben nicht mehr angeschnitten.
- **Cover-Art füllt den Rahmen wirklich aus.** Der Cover-Kasten ist jetzt strikt quadratisch und schrumpft nicht mehr gegen die Höhe — keine schwarzen Balken mehr, auch wenn das Bild quadratisch ist.
- **Hochgeladene Ordner-Cover gewinnen über eingebettete ID3-Cover.** Legst du ein Bild in einen Ordner (oder ziehst es beim Upload mit rein), wird es automatisch als `cover.jpg` abgelegt und im Player angezeigt — egal welches Cover die MP3 intern mitbringt.
- **Setup-Hilfe erscheint auch im ersten (Hardware-) Schritt.** Das Fragezeichen wurde vorher vom Spinner-Overlay verdeckt.
- **Unübersetzter „Error: Access denied" beim PIN-Setzen ist weg.** Fehlermeldungen kommen jetzt komplett auf Deutsch und konsistent mit dem Rest der App — auch wenn die Box schon eine PIN kennt.
- **Suche in der Bibliothek zeigt nur noch ein Lösch-Kreuz.** Der zusätzliche Browser-X ist unterdrückt, das eigene X bleibt.
- **Sortierung in der Bibliothek klappt auch bei leeren Ordnern.** Leere Ordner landen nicht mehr alle am Ende, sondern werden nach dem Änderungsdatum des Ordners selbst einsortiert.
- **WLAN-Rettung zeigt die aktive Wartezeit.** Ein Ring hebt den gewählten Preset hervor; neue Installationen bekommen 5 Minuten als Vorauswahl.
- **Sleep-Timer bricht jetzt wirklich ab, wenn jemand während des Fades die Lautstärke hochdreht.** Die Erkennung hat vorher immer gegen den schon aktualisierten Wert verglichen — jetzt merkt der Timer, dass eingegriffen wurde.
- **Browser-Audio bricht nicht mehr bei Stream-Wechsel ab.** Backend-Proxy räumt httpx-Verbindungen sauber ab (`AsyncExitStack`), MPD httpd hält seinen Output dauerhaft offen (`always_on`), und ein neues WebSocket-Signal `player:stream_ready` löst das Reload deterministisch aus statt per 2.5s-Timeout zu raten. MIME-Type wird aus dem MPD-Stream übernommen (Icy-Metadata durchgeschleift).

### Verbessert

- **Sleep-Timer-Pill bleibt über jedem Cover lesbar.** Solider dunkler Hintergrund statt halbtransparent mit blauer Schrift. Die letzte Minute wird warm (amber), der Fade selbst klar als Primary-Zustand mit einem einzelnen ruhigen Puls markiert — statt doppelt zu blinken.
- **Sleep-Timer läuft genau bis 0.** Der Fade-Out beginnt jetzt vor Timer-Ende, sodass bei 0 tatsächlich Stille ist. Bisher lief der Countdown auf 0, _dann_ erst wurde es leiser — das wirkte kaputt.
- **PIN-Eingabe im Setup-Wizard ist als Eingabe erkennbar.** Vier einzelne Ziffern-Boxen (OTP-Stil) statt eines schmalen Felds, das wie ein Button aussah. Automatisches Weiterspringen, Backspace zurück, ArrowLinks/Rechts zum Navigieren, Paste einer 4-stelligen PIN auf einmal. Erster Kasten bekommt beim Öffnen den Fokus.
- **Hilfe-Überschriften klingen wie Hilfe, nicht wie Diagnose.** „Falls das WLAN nicht auftaucht" statt „WLAN wird nicht gefunden" — und analog für Figur, Ton, App, Hardware.
- **Schließen-X im Hilfe-Sheet sitzt klassisch rechts oben.** 44×44 Touch-Target, Drag-Handle bleibt als visueller Hinweis auf Mobile.
- **Library-Suche tippt flüssig.** 300 ms Debounce + `requestIdleCallback` schieben die teure Filter-Arbeit aus dem Tipp-Pfad heraus, während ein dezenter Spinner im Suchfeld zeigt, dass im Hintergrund gefiltert wird.
- **WLAN-Rettung: QR-Code neben den Zugangsdaten.** Auf Desktop 2-spaltig (Daten links, QR rechts), auf Mobile gestapelt. „QR-Code drucken" ist jetzt ein richtiger Primary-Button mit Drucker-Icon statt einem Text-Link. Der Scan-Hinweis ist raus — ein QR-Code erklärt sich selbst.

### Doku

- **Doku-Review Phase 1 (Quickfixes):** README-Tippfehler „Musik hört los" → „Musik spielt" korrigiert, RFID-Jargon im User-Text auf einmalige technische Einführung reduziert, ROADMAP „Watchdog" und „Leichte Sprache" ehrlich als verschoben/Basis-A11y markiert, Spotify-Eintrag als reiner Receiver-Modus geschärft (Vision-konform), installation.md um Schritt 12 für OnOff-SHIM-Kernel-Overlays erweitert und `curl | sudo bash`-Alternative mit Inspect-Pfad ergänzt, Bonjour-Windows-Link direkt auf Apple statt iTunes-Verweis, hardcoded `/home/pi/`-Pfad als `/home/<benutzer>/` verallgemeinert, hardware.md um 2-Satz-Erklärung zur GPIO-25-Doppelnutzung (RC522 RST + HifiBerry Amp-Enable) + PN532-I2C-Adresse ergänzt, UPDATE.md „nur main"-Hinweis als Alpha-Phase-Begründung eingeordnet, BACKUP.md Einleitungssatz entreissend umformuliert, Pi-Zero-W-Teststatus als „Installation auf 0.1.0-alpha verifiziert, für 0.2.x nicht re-getestet" präzisiert.
- **Doku-Review Phase 2 (Struktur):** `docs/`-Tree nach Zielgruppen getrennt — `docs/fuer-eltern/` (BACKUP, UPDATE), `docs/fuer-bastler/` (installation, hardware), `docs/fuer-entwickler/` (ARCHITEKTUR, ROADMAP, UI-GUIDELINES, entwicklung), `docs/archive/` (PRE-BETA-AUDIT). VISION.md bleibt top-level. BACKLOG.md aufgesplittet: aktive Produkt-Prios + bekannte Bugs + offene Beta-Blocker + Architektur-Refactorings bleiben, erledigte Audit-Items (Pre-Beta, Security, E2E, A11y, i18n, Test-Coverage, Architektur, Setup-Wizard-Erledigtes) in neue Historie-Datei `docs/archive/pre-beta-audit-findings.md` ausgelagert. README bekommt Zielgruppen-Navigationsblock. Alle internen Doku-Links (README, CONTRIBUTING, SECURITY, entwicklung.md, ROADMAP.md, installation.md, archive/README.md) auf neue Pfade aktualisiert.
- **Doku-Review Phase 3 (Content):** Neue Eltern-lesbare Feature-Übersicht (`docs/fuer-eltern/features.md`) — was Tonado heute kann, was bald kommt, was denkbar ist. VISION.md „Kein Bluetooth-Speaker" geschärft: Box als Receiver-Ziel (Spotify/AirPlay) explizit vom eigenen Player abgegrenzt. Bluetooth-Speaker-Backlog-Item erhält Vision-Konflikt-Notiz. Neue Datei `docs/fuer-entwickler/install-strategy.md` dokumentiert den Weg von „heute: SSH + curl|bash für technik-affine Eltern" zu „Ziel: Pi-Image zum Flashen" und benennt die Lücke zur Vision ehrlich. README-Status-Block geschärft: Alpha ist aktuell nur für technik-affine Eltern, Pi-Image ist Beta-Ziel. Pi-Image als Prio-3-Backlog-Item hinzugefügt, Cross-Referenz zur Install-Strategie.
- **Doku-Review Phase 4 (Eltern-Polish):** `features.md` mikro-poliert (Alpha-Label, „winziger Funk-Chip" statt „RFID-Chip", keine Codec-Listen, keine Code-Pfade, kein Marken-Name im Body). `BACKUP.md` und `UPDATE.md` auf den Happy-Path für nicht-technische Eltern umgeschrieben — JSON-Struktur, `git pull`/`pip`, `journalctl`/`df -h`, SMB/sftp, Pfad-Snippets und englische Fehler-Strings in neue Bastler-Companion-Seiten `docs/fuer-bastler/backup-details.md` und `docs/fuer-bastler/update-details.md` ausgelagert. Neue Datei `docs/fuer-eltern/ERSTE-SCHRITTE.md` (Happy-Path Tag 1: einschalten, mit Handy verbinden, Musik hochladen, Figur zuordnen, Kind spielen lassen, plus häufige Start-Probleme). Neue Datei `docs/fuer-eltern/FAQ.md` (9 typische Eltern-Fragen, je 2-4 Sätze). README-Navigation um Erste-Schritte (als erster Eltern-Einstieg) und FAQ erweitert.

### Hinzugefügt

- **Einheitliche Inline-Fehlermeldungen.** Neue `InlineError`-Komponente (Symbol + Text, sanfte rote Farbtöne, `role="alert"`) löst die Wildwuchs-Meldungen in Formularen ab und koppelt `aria-invalid` / `aria-describedby` korrekt an die Eingabefelder.
- **Hilfe im Setup-Wizard:** Fragezeichen-Icon in jedem Schritt öffnet ein Info-Sheet mit Troubleshooting-Tipps (WLAN nicht gefunden, Figur wird nicht erkannt, kein Ton, App findet Box nicht, Hardware unvollständig). Funktioniert offline — kein Netz nötig.
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
