# Tonado

**Die Musikbox, die dir gehört.**

Eine Open-Source Kinder-Musikbox mit RFID-Karten — gesteuert vom Smartphone, gebaut auf dem Raspberry Pi. Kein Abo, keine Cloud, keine Limits.

## Was ist Tonado?

Tonado verwandelt einen Raspberry Pi in eine Musikbox für Kinder. Das Kind legt eine Figur oder Karte auf — die Musik spielt sofort. Eltern verwalten alles bequem vom Smartphone: Musik hinzufügen, Figuren zuweisen, Lautstärke begrenzen, Einschlaftimer setzen.

### Was kostet Tonado?

| Komponente | Empfehlung | Preis ca. |
|------------|-----------|-----------|
| Raspberry Pi | 3B+ (empfohlen) oder Zero W (minimum) | 35–45 € |
| RFID-Reader | RC522 (SPI) oder PN532 (I2C) | 5–10 € |
| Lautsprecher | Beliebig (3.5mm, I2S DAC, USB) | 10–20 € |
| RFID-Karten | MIFARE Classic 1K (13.56 MHz) | 5 € / 10 Stk |
| microSD-Karte | 16 GB+ (Class 10) | 8 € |
| Netzteil | 5V / 2.5A (Pi 3B+) | 10 € |
| **Optional** | | |
| Audio-HAT | HifiBerry MiniAmp (besserer Sound) | 15 € |
| Gyro-Sensor | MPU6050 (I2C) | 3 € |
| GPIO-Buttons | Arcade-Buttons oder Taster | 5 € |
| Gehäuse | 3D-Druck oder Holzbox | variabel |

**Gesamtkosten: ca. 70–100 €** — eigene MP3s, kein Abo, keine laufenden Kosten.

## Features

### Für Kinder
- **Figur oder Karte auflegen → Musik spielt** — intuitiv und sofort
- **Große Buttons** — Play/Pause, Lauter/Leiser, Vor/Zurück
- **Gyro-Sensor** — Box kippen zum Vor-/Zurückspulen (optional)

### Für Eltern (Web-App)
- **Figuren-Wizard** — Figur scannen, Inhalt auswählen, fertig
- **Bibliothek** — Alle Hörbücher und Musik als Cover-Galerie
- **Musik hochladen** — Drag & Drop im Browser
- **Streams** — Internetradio, Podcasts, ARD Audiothek
- **Lautstärke begrenzen** — Maximale Lautstärke einstellen
- **Einschlaftimer** — Musik stoppt automatisch
- **PIN-geschützt** — Kinder sehen nur den Player, Eltern verwalten

### Für Bastler
- **Open Source** — MIT-Lizenz, vollständig anpassbar
- **Hardware-Wizard** — Erkennt RFID-Reader, Audio-Output, Gyro automatisch
- **Kein SSH nötig** — Alles über die Web-App konfigurierbar
- **Modularer Aufbau** — Services einzeln austauschbar

## Schnellstart

```bash
# 1. Tonado-Image auf SD-Karte flashen (Raspberry Pi Imager)
# 2. SD-Karte in den Pi, einschalten
# 3. Mit dem WLAN "Tonado-Setup" verbinden
# 4. Browser öffnet automatisch den Einrichtungs-Wizard
# 5. WLAN auswählen → Hardware wird erkannt → erste Figur zuweisen → fertig!
```

## Tech Stack

- **Frontend:** Svelte 5 + Tailwind CSS (PWA)
- **Backend:** Python / FastAPI
- **Audio:** MPD (Music Player Daemon)
- **Datenbank:** SQLite

## Status

> **Alpha (v0.1.0)** — Funktioniert, aber noch nicht für Endnutzer bereit.

Tonado läuft auf einem Pi Zero W mit HifiBerry MiniAmp und RC522 RFID-Reader. Die Web-App steuert Musik, Radio und Podcasts. Hardware-Erkennung funktioniert automatisch — der Gyro-Sensor ist noch nicht auf echter Hardware getestet.

### Was funktioniert

- Player mit Live-Progress, Seek, Shuffle, Repeat, Volume
- Bibliothek: Ordner, Radio, Podcasts (mit Episoden-Queue)
- Figuren-Wizard (UI fertig, RC522 Hardware-Detection getestet)
- Eltern-Einstellungen: PIN, Sleep Timer, Volume Limit
- Browser-Audio: Musik direkt auf dem Smartphone hören
- Security: Auth auf System-Endpoints, Path-Validation, Upload-Limits

### Was noch fehlt bis Beta (v0.2.0)

- RFID-Reader: RC522 (SPI) getestet — PN532 (I2C) und USB noch offen
- Gyro-Sensor (MPU6050) auf echter Hardware testen
- Ersteinrichtungs-Wizard (Captive Portal) End-to-End testen
- Hardware-Resilience: Saubere Fehlermeldungen wenn Teile fehlen
- Install-Script auf frischem Pi testen
- Weitere Pi-Modelle testen (3B+, 4, 5)
- SD-Karte mind. 16 GB (4 GB reicht nicht für Medien)

### Getestete Hardware

| Komponente | Status |
|-----------|--------|
| Pi Zero W + HifiBerry MiniAmp | Funktioniert |
| RC522 RFID-Reader (SPI) | Funktioniert (Auto-Detection) |
| Alles andere | Noch nicht getestet |

Wir suchen Tester! Wenn du einen Pi und RFID-Reader hast, melde dich gerne.

---

*Inspiriert von großartigen Open-Source-Projekten wie [Phoniebox](https://github.com/MiczFlor/RPi-Jukebox-RFID) und [TonUINO](https://www.voss.earth/tonuino/) — und der Idee, dass Kinderzimmer keine Cloud-Anbindung brauchen.*

## Lizenz

MIT License — Siehe [LICENSE](LICENSE)

## Mitmachen

Tonado ist ein Community-Projekt. Beiträge sind willkommen! Mehr Infos folgen.
