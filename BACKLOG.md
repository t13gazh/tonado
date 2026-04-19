# Backlog

> **UX-Leitlinie:** So einfach wie möglich. Kein überladenes UI. Besser als alle anderen Apps. Layouts testen, ausprobieren, verwerfen, umbauen — bis Nutzer sagen: "Das ist durchdacht, das sieht geil aus."

> Der Pre-Beta-Audit (April 2026) ist abgearbeitet. Findings-Historie: [`docs/archive/pre-beta-audit-findings.md`](docs/archive/pre-beta-audit-findings.md). Offene Punkte sind unten in die aktiven Listen überführt.

## Bekannte Probleme

- [ ] **Browser-Audio bricht bei Stream-Wechsel ab.** Wenn Browser-Audio aktiv ist und man den Radio-Stream oder die Musik wechselt, kommt kein Audio mehr im Browser. Erst nach manuellem Deaktivieren/Aktivieren wieder Ton. Bisherige Fix-Versuche (Retry-Chain, Reload-Delay 2.5s, alten Stream sofort stoppen, same-URI Detection) haben nicht geholfen. Root Cause ist tiefer — vermutlich muss der gesamte Ansatz (HTML Audio Element auf Streaming-Proxy) überdacht werden. Mögliche Alternative: WebAudio API oder Server-Sent Events für Stream-Status.

## Offene Beta-Blocker (aus Pre-Beta-Audit)

- [ ] Captive-Portal-First-Boot E2E auf 3 SD-Images (Pi 3B+, Zero W, Pi 4) — braucht Hardware. Pi aus dem Karton → AP → WLAN einrichten → erster Karten-Play, nicht-technisch durchgespielt (K4).
- [ ] Pi-Kompatibilitätsmatrix Live-Tests auf Zero W / Pi 4 / Pi 5 (H8).
- [ ] Install-Script End-to-End auf echter SD-Karte (>= 16 GB, frisches Bookworm-Lite).
- [ ] Performance-Optimierung Pi Zero W (Health-Endpoint, CPU-Idle-Last).
- [x] Hardcoded UI-Strings → i18n (bereits umgesetzt — 559 `t()`-Aufrufe, 0 hardcoded Strings in allen 29 Svelte-Komponenten, Audit 2026-04-19).

## Setup-Wizard (offen)

- [ ] Status-LED Steuerung via ButtonService (GPIO 23, Blinkmuster für Boot/Play/Error).
- [ ] Hilfe/Troubleshooting als Popup aus Git-Docs laden.

## Prio 1 — Kernfunktionen

- [ ] **Sleep-Timer verlängern aus dem Player-Pill:** Klick auf den Pill öffnet Mini-Sheet mit „+5 Min / +10 Min / Abbrechen". Typischer Eltern-Workflow wenn Kind noch wach ist. Aktuell nur Abbrechen möglich, Neustart nur über Einstellungen.

## Prio 2 — Differenzierung

- [ ] **Sprachaufnahme in der Web-App:** Figur/Karte auflegen → App erkennt sie → direkt besprechen (MediaRecorder API). Physische Geste + Aufnahme verknüpft = einprägsamer als nachträgliches Zuordnen.
- [ ] **Offline-Modus:** Box trennt Internet-WLAN, spannt eigenes AP auf. App zeigt Offline-Status, Streaming-Features (Radio, Podcasts) werden visuell deaktiviert. Lokale Musik + Figuren funktionieren weiter. Datenschutz-Feature für bewusste Eltern — kein Datenverkehr nach außen.
- [ ] **WLAN-Verwaltung in Einstellungen:** Verfügbare Netze scannen, neues WLAN hinzufügen, zwischen gespeicherten Netzen wechseln. Unabhängig vom Offline-Modus — normales Netzwerk-Management über die App.
- [ ] **Dateien/Ordner von der Box herunterladen** (Use Case: Musik vom Handy hochgeladen, lokal gelöscht, am Laptop wieder holen).
- [ ] **Figur verloren = kein Problem:** Content ist an ID gebunden, einfach neue Karte beschreiben und gleichen Inhalt zuordnen. In App klar kommunizieren.

## Prio 2.5 — Update-System ausbauen

- [ ] **Update via GitHub Releases API:** Statt git pull — Release-Archiv herunterladen, Semver-Vergleich mit lokaler Version. Kein Git auf Endnutzer-Pi nötig. Aktuell: git-basiertes Update in system_service.py (check_update/apply_update).
- [ ] **Changelog in der App anzeigen:** Release Notes aus GitHub vor Installation zeigen.
- [ ] **Update-Fortschrittsanzeige:** Download + Installation mit visuellem Feedback.
- [ ] **Update-Rollback:** Alte Version als Fallback behalten, bei Boot-Failure automatisch zurück.
- [ ] **Checksum-Validierung:** SHA256 aus Release prüfen vor Installation.
- [ ] **USB-Stick-Update:** Release-Archiv auf Stick → Box erkennt beim Einstecken, Offline-Update möglich.

## Prio 3 — Wertvolle Erweiterungen

- [ ] **Pi-Image zum Flashen** (pi-gen): Fertiges Image für nicht-technische Eltern — einmal flashen, einmal im Browser öffnen, fertig. Schließt die Install-Lücke zwischen „technik-affin (SSH)" und „Zielgruppe der Vision". Details in [`docs/fuer-entwickler/install-strategy.md`](docs/fuer-entwickler/install-strategy.md).
- [ ] **Box-Name:** Im Setup Wizard festlegen, in Einstellungen nachträglich änderbar. Default "Tonado". Ändert mDNS-Hostname (z.B. `meinebox.local`) und Netzwerk-Discovery-Name.
- [ ] **Farbschema:** Farbthema der Web-App in den Einstellungen änderbar. Personalisierung der Box-Oberfläche (z.B. Lieblingsfarbe des Kindes).
- [ ] **Radio/Podcast-Katalog:** Durchsuchbarer Katalog öffentlich-rechtlicher Sender und Podcasts (ARD Audiothek, Deutschlandfunk etc.). Direkt in der App browsen und hinzufügen statt URLs manuell recherchieren und einfügen.
- [ ] **Stream-Gesundheitscheck:** Mitgelieferte Kinder-Radiosender/Podcasts regelmäßig auf Erreichbarkeit prüfen. URLs können sich ändern — automatisch updaten (via curated Liste aus Repo/Release) oder zum Löschen markieren und Nutzer hinweisen. Gilt auch für manuell hinzugefügte Streams.
- [ ] **Kategorien/Tags für Bibliothek:** Inhalte mit Stimmungen/Anlässen taggen (z.B. Einschlafen, Lieblingshörbuch, Weihnachten, Geburtstag). Schnellzugriff statt durch lange Ordnerlisten scrollen. Muss einfach bleiben — Konzept recherchieren, was für Eltern praktisch ist ohne zu überladen.
- [ ] **Figur direkt aus Bibliothek verknüpfen:** Beim Browsen in der Bibliothek direkt eine Figur/Karte zuordnen können, ohne den Umweg über den Figuren-Wizard.
- [ ] **Content an mehrere Figuren binden:** Gleiches Hörbuch auf zwei oder mehr Karten — z.B. eine fürs Kinderzimmer, eine fürs Auto.
- [ ] **Vollbackup inkl. Content:** Optional alle Audiodateien ins Backup einschließen (nicht nur Config + Kartenzuordnung). Restore muss alles wiederherstellen können. Offene Frage: Merge-Strategie bei Konflikten (bestehende Daten vs. Backup-Daten).
- [ ] **Mehrsprachigkeit der Web-App:** i18n aktivieren (Grundstruktur ist vorbereitet), Sprachwahl bei Ersteinrichtung und später in Einstellungen änderbar. Deutsch als Default, Englisch als erste Zweitsprache.
- [ ] **Klopf-Modus als Alternative zu Kipp-Gesten:** Accelerometer des MPU6050 für Klopf-Erkennung nutzen (1x, 2x, 3x klopfen = verschiedene Aktionen, ggf. Richtung unterscheidbar). In Einstellungen umschaltbar zwischen Kipp-Modus und Klopf-Modus.
- [ ] **Gyro-Gesten individuell zuweisbar:** Jede der 5 Gesten (Kippen L/R/V/Z, Schütteln) frei mit einer Aktion (Skip, Volume, Play/Pause, Stop, Shuffle, keine) belegbar. Defaults folgen weiter der K8-Kopplung an `card.remove_pauses`. UI als "Erweitert"-Sektion unter Gyro-Einstellungen, damit der Standard-Nutzer nicht überfordert wird.
- [ ] **Startup/Shutdown-Sound:** Konfigurierbarer Sound beim Hoch- und Herunterfahren, aktivierbar/deaktivierbar in Einstellungen. Eigene Sounds hochladbar. Standard-Sounds mitliefern (lizenzfrei, z.B. von freesound.org/CC0).
- [ ] **Kindersicherung für physische Tasten:** Lautstärke-Tasten / Skip-Tasten deaktivierbar über App.
- [ ] **Lautstärke-Schritte:** Konfigurierbare Schrittgröße für physische Lautstärke-Knöpfe. Idealerweise intelligent berechnet basierend auf aktuellem Level (unten feinere Schritte, oben gröbere) statt linear.
- [ ] **Eltern-Dashboard:** Übersicht was heute/diese Woche gehört wurde, wie lange. Nutzungsstatistik pro Kind/Figur.
- [ ] **DRM-freier Import:** Klar kommunizieren welche Formate unterstützt werden (MP3, FLAC, OGG, WAV). Hinweis bei DRM-geschützten Dateien.
- [ ] **Bibliothek sortieren:** Drag & Drop für eigene Sortierung + Umschalten zwischen Sortieroptionen (alphabetisch, zuletzt hinzugefügt, Spieldauer).
- [ ] **Bibliothek verwalten:** Titel innerhalb von Ordnern/Playlists löschen, zwischen Ordnern verschieben, Reihenfolge per Drag & Drop ändern.
- [ ] **Titel aus Ordner direkt einer Playlist hinzufügen** (Kontextmenü / "Zu Playlist hinzufügen").
- [ ] **Suche:** Freitext über alle Titel, Ordner, Playlists. Schnell finden ohne langes Scrollen.
- [ ] **Filter:** Nach Typ (Musik, Hörbuch, Podcast), nach Figur-Zuordnung (zugeordnet/frei).
- [ ] **Playlist aus mehreren Ordnern zusammenstellen:** Quick-Add — durch Bibliothek browsen, Titel antippen = hinzugefügt. So einfach wie möglich.
- [ ] **Warteschlange / "Als nächstes":** Spontan einen Titel einschieben ohne Playlist zu ändern.
- [ ] **Cover-Art erweitert:** ID3-Tags auslesen und Cover anzeigen (vorhanden). Fallback: Auto-Generierung (Farbe + Initiale) oder eigenes Bild hochladen.
- [ ] **Ordner umbenennen:** Alle Referenzen (cards.content_path, playlist_items) aktualisieren.
- [ ] **Playlist umbenennen:** Backend existiert (rename_playlist()), Frontend-UI fehlt.
- [ ] **Verknüpfungen über IDs statt Pfade:** Ordner-Rename darf keine Zuordnungen zerstören.
- [ ] **Sleep Timer Countdown im Player:** Hinweis + verbleibende Zeit in der Player-Ansicht.
- [ ] **Metadaten bearbeiten:** Titel/Album/Interpret in der App korrigieren.
- [ ] **Batch-Upload:** Mehrere Dateien gleichzeitig hochladen mit Fortschrittsanzeige.
- [ ] **Ordner hochladen:** Ganzes Album auf einmal, Ordnerstruktur beibehalten.
- [ ] **SD-Karten-Portabilität:** SD-Karte zwischen verschiedenen Pi-Modellen wechselbar (z.B. auf Pi Zero W vorbereiten, in Pi 3B+ stecken). Hardware-Wizard erkennt neue Hardware beim Boot und rekonfiguriert automatisch (Audio-Output, RFID-Interface etc.).

## Architektur-Refactorings (aus Senior-Review 2026-04-17, Post-Beta)

- [ ] **InputRouter extrahieren** — GyroService kennt aktuell `card.remove_pauses` (K8-Kopplung) und mappt Gesten auf Playback-Actions selbst. Sobald Buttons, Doppeltipp-RFID oder zukünftige Eingaben dieselbe Kontext-Logik brauchen, duplizierts sich. Sauberer: Gyro emittiert neutrale Gesten (`tilt_forward`, `shake`), ein `InputRouter`/`PlaybackDispatcher` konsumiert alle Input-Quellen und entscheidet kontextabhängig. Macht außerdem das Prio-3-Item "Gyro-Gesten individuell zuweisbar" trivial — nur Dispatcher-Config.
- [ ] **ConfigKeyRegistry als Single Source of Truth** — Heute gibt es drei Orte, die über Config-Keys entscheiden: `config_whitelist.py` (public writable), `backup_service._RESTORE_CONFIG_SKIP_PREFIXES` (backup-ignore), `gyro_service._on_config_changed` (watcher). Keine Stelle kennt die anderen. Vorschlag: Ein zentrales Registry pro Key mit Metadaten (public-writable, backup-policy, watchers, type, range). Whitelist/Skip/Subscription leiten sich daraus ab, Compiler hilft beim Hinzufügen neuer Keys.
- [ ] **Response-Schema-Policy statt Feld-Blanking** — M5 maskiert LAN-Metadaten heute händisch (`d["hostname"] = ""`). Skaliert nicht. Sauberer: Zwei Pydantic-Modelle (`SystemInfoPublic` vs. `SystemInfoFull`), Router wählt Modell per Tier. Grenze dokumentiert sich im Schema statt im Handler. Gilt auch für `/system/hardware` und künftige Diagnose-Endpoints.
- [ ] **JWT-Rotation: Token-in-Response bei PIN-Change** — Aktuell evictet `set_pin()` alle Sessions inklusive der gerade aktiven Wizard-Session. Heute durch Bootstrap-Pass mitigiert, aber fragil. Besser: `set_pin()` gibt optional ein frisches Token zurück; Router reicht es in der Response durch. Client-seitige Session-Recovery wird trivial, Invariante „PIN-Change evictet alles" bleibt explizit.

## Migrations-Wizard (Post-Beta)

- [ ] Phoniebox v2/v3 Daten und Karten-Zuordnungen zu Tonado migrieren.
- [ ] Audio-Dateien (Symlinks), Karten-Mapping, Hardware-Config, Playlisten.
- [ ] Erkennung: /home/pi/RPi-Jukebox-RFID/ vorhanden? Version?
- [ ] Zeitpunkt: Nach v0.2.0-beta.

## Prio 4 — Zukunft / Hardware-abhängig

- [ ] **Aufnahme über Mikrofon am Pi:** USB-Mikro oder I2S MEMS-Mikro (INMP441/SPH0645) anschließen, direkt an der Box aufnehmen statt über Handy-Browser. Karte auflegen + Knopf drücken = aufnehmen.
- [ ] **Bluetooth-Speaker-Modus:** Box als normaler BT-Lautsprecher vom Handy nutzen. ⚠️ Vision-Konflikt: In [VISION](docs/VISION.md#was-tonado-nicht-ist) steht „kein Bluetooth-Speaker", weil Tonado eine Kinder-Musikbox ist, kein allgemeiner Lautsprecher. Nur weiter verfolgen, wenn ein klarer Kinder-Use-Case erkennbar ist (z.B. Handy als temporäre Hörbuch-Quelle, wenn Figur fehlt). ⚠️ Technisch: BT und WiFi teilen sich den Chip (Pi Zero W, 3B+), BT-Audio (A2DP) + WiFi gleichzeitig = Interferenzen/Stottern. Evtl. nur auf Pi 4/5 sinnvoll oder mit USB-BT-Dongle.
- [ ] **BT-Kopfhörer-Unterstützung:** Kabellose Kopfhörer mit der Box koppeln. Separate Kopfhörer-Lautstärkegrenze (Gehörschutz). ⚠️ Gleiche HW-Einschränkung wie BT-Speaker. Braucht PulseAudio/PipeWire zwischen MPD und ALSA — verkompliziert Audio-Pipeline.
- [ ] **NFC-Smartphone-Interaktion:** RFID-Reader erkennt Smartphone (NFC/HCE auf 13,56 MHz). Use Cases: (a) Ersteinrichtung ohne PIN — Handy auflegen = vertraut, physische Nähe als Auth, (b) Gastmodus — Besucherkind legt Handy auf → eingeschränkter Zugriff, (c) BT-Speaker/Streaming aktivieren — Handy auflegen schaltet Box in BT-Modus, (d) Handsfree-Steuerung durch physische Geste statt App. ⚠️ iPhone-HCE stark eingeschränkt, Android braucht native App (kein reines PWA).
- [ ] **Multiroom / Sync-Play:** Mehrere Boxen über LAN koppeln, gleichen Content synchron abspielen.
- [ ] **Nachtlicht-Steuerung:** Falls LED angeschlossen (GPIO), Farbe/Helligkeit über App steuerbar.
- [ ] **Mehrere Boxen in einer App verwalten:** Haushaltsmodus — eine App steuert mehrere Tonado-Boxen (z.B. Kinderzimmer + Wohnzimmer).
