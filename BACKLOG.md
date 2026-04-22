# Backlog

> **UX-Leitlinie:** So einfach wie möglich. Kein überladenes UI. Besser als alle anderen Apps. Layouts testen, ausprobieren, verwerfen, umbauen — bis Nutzer sagen: "Das ist durchdacht, das sieht geil aus."

> Der Pre-Beta-Audit (April 2026) ist abgearbeitet. Findings-Historie: [`docs/archive/pre-beta-audit-findings.md`](docs/archive/pre-beta-audit-findings.md). Offene Punkte sind unten in die aktiven Listen überführt.

## Offene Beta-Blocker (aus Pre-Beta-Audit)

Scope für v0.2.0-beta: die physisch vorhandene Hardware — Pi 3B+ und Pi Zero W. Pi 4 / Pi 5 werden in Post-Beta nachgezogen, sobald ein Gerät verfügbar ist.

- [x] Install-Script End-to-End auf echter SD-Karte (2026-04-22 auf Zero W mit 4 GB Bookworm-Lite durchgespielt, Service startet sauber).
- [x] Pi-Kompatibilitätsmatrix Live-Tests auf Pi 3B+ und Zero W (H8) — Zero W 0.2.1-alpha: Install sauber, CPU 40 °C idle, RAM 160/427 MB, keine Errors in 10 min. 3B+ ebenfalls live.
- [x] Performance-Optimierung Pi Zero W — Idle-Werte entspannt, keine Optimierung für Beta nötig (siehe Zahlen oben).
- [x] Hardcoded UI-Strings → i18n (bereits umgesetzt — 559 `t()`-Aufrufe, 0 hardcoded Strings in allen 29 Svelte-Komponenten, Audit 2026-04-19).

**Captive-Portal-First-Boot E2E** ist an das Pi-Image gebunden und rückt daher mit in Post-Beta: mit dem heutigen Install-Script muss der Pi ohnehin vorher per WLAN oder LAN erreichbar sein, weil das Script via `curl | sudo bash` über SSH läuft. Erst das Pi-Image zum Flashen (Prio-3 unten) macht das AP-First-Boot-Szenario realistisch — siehe [`docs/fuer-entwickler/install-strategy.md`](docs/fuer-entwickler/install-strategy.md).

## Setup-Wizard (offen)

- [ ] Status-LED Steuerung via ButtonService (GPIO 23, Blinkmuster für Boot/Play/Error).
- [ ] Hilfe/Troubleshooting als Popup aus Git-Docs laden.

## UX-Polish (Post-Beta)

- [ ] **UI-Konsistenz-Welle: gemeinsames Komponenten-Set bauen.** Der Audit am 2026-04-22 ([`docs/archive/ui-consistency-audit-2026-04-22.md`](docs/archive/ui-consistency-audit-2026-04-22.md)) fand 9 visuelle Sprachen für „Auswahl aus N", 3 Toggle-Varianten, 6 Fehlerdarstellungen, 3 Primary-Button-Höhen, 4 Settings-Row-Layouts. Für Beta sind die vier sichtbarsten Punkte lokal gefixt; systemisch bleibt das offen. Vorgeschlagene Kern-Komponenten: `<Button variant size>`, `<SettingRow>`, `<ToggleRow>`, `<SegmentSelect>`, `<PinEntry>`. Blueprints existieren bereits im Code (iOS-Switch in WLAN-Rettung, Segmented-Control in Library-Sort, OTP-Cells in PinStep). Aufwand: 2-3 Tage inkl. Migration aller Call-Sites. Zuerst die Komponenten bauen, dann in separaten Commits jede Einstellungen-Seite umstellen.
- [ ] **ContentPicker „Belegte Figur"-Hinweis visuell polieren.** Heute steht eine dezente Zeile „Figur: Name" unter jedem belegten Eintrag. Funktional gut, optisch fad. Emil-Review: evtl. farbiges Chip/Badge mit Figuren-Icon + Name, oder Name links im Hauptblock statt untendrunter; das gesamte Row-Rhythmus-Gefühl mit echten Karten einmal durchspielen. Priorisiert nach Beta.
- [ ] **OnOff SHIM: Hold-Delay + Power-LED-Patterns.** Aktuell triggert ein kurzer Tastendruck sofort den Shutdown. Gewünscht: (a) erst nach 3 s Drücken-und-Halten triggert Shutdown, während der Haltezeit blinkt die Power-LED als Feedback („ich höre dich, weiter halten = Ja"); (b) nach dem Start blinkt die Power-LED so lange, bis alle Services ready sind, danach Dauerleuchten. Technisch: `gpiomon`/Userspace-Listener mit Zeitmessung, LED via GPIO (SHIM nutzt üblicherweise GPIO 17 Button + GPIO 4 PowerOff; LED-Pin aus SHIM-Spec verifizieren). Braucht Hardware-Test am OnOff-SHIM-Pi.

## Doku-Pflege

- [ ] **Hardware-Claims breit prüfen.** Punktuelle Reviews wurden gemacht (HifiBerry-Ausrichtung, GPIO-25-Doppelnutzung, PN532-I2C-Adresse). Rest von `docs/fuer-bastler/hardware.md` noch durch einen Bastler mit echtem Pi/HAT gegenlesen lassen, bevor die Doku in Beta geht.

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
- [ ] **Filter:** Nach Typ (Musik, Hörbuch, Podcast), nach Figur-Zuordnung (zugeordnet/frei).
- [ ] **Playlist aus mehreren Ordnern zusammenstellen:** Quick-Add — durch Bibliothek browsen, Titel antippen = hinzugefügt. So einfach wie möglich.
- [ ] **Warteschlange / "Als nächstes":** Spontan einen Titel einschieben ohne Playlist zu ändern.
- [ ] **Verknüpfungen über IDs statt Pfade:** Ordner-Rename (bereits UI-seitig möglich) zerstört Zuordnungen, wenn Backend weiter mit Pfaden arbeitet. Umstellung auf IDs als Aufräum-Arbeit.
- [ ] **Metadaten bearbeiten:** Titel/Album/Interpret in der App korrigieren.
- [ ] **Ordner hochladen:** Ganzes Album auf einmal, Ordnerstruktur beibehalten (`webkitdirectory`).
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
- [ ] **Spotify-Integration (Musik/Hörbücher abspielen):** Eine Möglichkeit, Spotify-Inhalte über Tonado zu hören. ⚠️ Vision-Konflikt: [VISION](docs/VISION.md#was-tonado-nicht-ist) sagt „kein eigener Spotify-Player" — nur Receiver-Modus (Box erscheint in der Spotify-App als Abspielziel) ist erwogen. Offene Frage (Product Owner): Reicht der Receiver-Modus (Spotify Connect via librespot, Elternhandy steuert, Kind hört über die Box), oder soll die Figur-auf-Box-Logik auf Spotify-Inhalte erweitert werden (eigener Player, Figur = Spotify-Playlist/Hörbuch)? Letzteres erfordert Premium-Account + Client-Lizenz + UX-Integration in den Figuren-Wizard und würde die Vision-Aussage entsprechend aufweichen.
- [ ] **Bluetooth-Speaker-Modus:** Box als normaler BT-Lautsprecher vom Handy nutzen. ⚠️ Vision-Konflikt: In [VISION](docs/VISION.md#was-tonado-nicht-ist) steht „kein Bluetooth-Speaker", weil Tonado eine Kinder-Musikbox ist, kein allgemeiner Lautsprecher. Nur weiter verfolgen, wenn ein klarer Kinder-Use-Case erkennbar ist (z.B. Handy als temporäre Hörbuch-Quelle, wenn Figur fehlt). ⚠️ Technisch: BT und WiFi teilen sich den Chip (Pi Zero W, 3B+), BT-Audio (A2DP) + WiFi gleichzeitig = Interferenzen/Stottern. Evtl. nur auf Pi 4/5 sinnvoll oder mit USB-BT-Dongle.
- [ ] **BT-Kopfhörer-Unterstützung:** Kabellose Kopfhörer mit der Box koppeln. Separate Kopfhörer-Lautstärkegrenze (Gehörschutz). ⚠️ Gleiche HW-Einschränkung wie BT-Speaker. Braucht PulseAudio/PipeWire zwischen MPD und ALSA — verkompliziert Audio-Pipeline.
- [ ] **NFC-Smartphone-Interaktion:** RFID-Reader erkennt Smartphone (NFC/HCE auf 13,56 MHz). Use Cases: (a) Ersteinrichtung ohne PIN — Handy auflegen = vertraut, physische Nähe als Auth, (b) Gastmodus — Besucherkind legt Handy auf → eingeschränkter Zugriff, (c) BT-Speaker/Streaming aktivieren — Handy auflegen schaltet Box in BT-Modus, (d) Handsfree-Steuerung durch physische Geste statt App. ⚠️ iPhone-HCE stark eingeschränkt, Android braucht native App (kein reines PWA).
- [ ] **Multiroom / Sync-Play:** Mehrere Boxen über LAN koppeln, gleichen Content synchron abspielen.
- [ ] **Nachtlicht-Steuerung:** Falls LED angeschlossen (GPIO), Farbe/Helligkeit über App steuerbar.
- [ ] **Mehrere Boxen in einer App verwalten:** Haushaltsmodus — eine App steuert mehrere Tonado-Boxen (z.B. Kinderzimmer + Wohnzimmer).
