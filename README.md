# 🌪️ Tonado

**Die Musikbox, die dir gehört.**

Eine Open-Source Kinder-Musikbox mit RFID-Karten — gesteuert vom Smartphone, gebaut auf dem Raspberry Pi. Kein Abo, keine Cloud, keine Limits.

## Was ist Tonado?

Tonado verwandelt einen Raspberry Pi in eine Musikbox für Kinder. Das Kind legt eine RFID-Karte auf — die Musik spielt sofort. Eltern verwalten alles bequem vom Smartphone: Musik hinzufügen, Karten zuweisen, Lautstärke begrenzen, Einschlaftimer setzen.

### Warum Tonado?

| | Musikbox | Tonado |
|---|---------|--------|
| **Einstiegspreis** | ~100 € + 18 €/Figur | ~70 € (Pi + RFID + Lautsprecher) |
| **30 Hörbücher** | 540 € (30 × 18 €) | 0 € (eigene MP3s) |
| **Eigene Inhalte** | 90 Min pro Kreativ-Figur | Unbegrenzt |
| **Abo nötig?** | Optional (Abo-Service) | Nein, nie |
| **Cloud-Pflicht** | Ja | Nein, komplett offline möglich |
| **Erweiterbar** | Nein | GPIO, Gyro-Sensor, Streaming, ... |

## Features

### Für Kinder
- **Karte auflegen → Musik spielt** — so einfach wie bei der Musikbox
- **Große Buttons** — Play/Pause, Lauter/Leiser, Vor/Zurück
- **Gyro-Sensor** — Box kippen zum Vor-/Zurückspulen (optional)

### Für Eltern (Web-App)
- **Karten-Wizard** — Karte scannen, Inhalt auswählen, fertig
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

## Hardware

### Was du brauchst

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

**Gesamtkosten: ca. 70–100 €** (vs. 100 € Musikbox + Figuren)

## Schnellstart

```bash
# 1. Tonado-Image auf SD-Karte flashen (Raspberry Pi Imager)
# 2. SD-Karte in den Pi, einschalten
# 3. Mit dem WLAN "Tonado-Setup" verbinden
# 4. Browser öffnet automatisch den Einrichtungs-Wizard
# 5. WLAN auswählen → Hardware wird erkannt → erste Karte zuweisen → fertig!
```

## Tech Stack

- **Frontend:** Svelte 5 + Tailwind CSS (PWA)
- **Backend:** Python / FastAPI
- **Audio:** MPD (Music Player Daemon)
- **Datenbank:** SQLite

## Status

🚧 **In aktiver Entwicklung.** Tonado befindet sich in der Architektur- und Planungsphase.

## Lizenz

MIT License — Siehe [LICENSE](LICENSE)

## Mitmachen

Tonado ist ein Community-Projekt. Beiträge sind willkommen! Mehr Infos folgen.

---

*Inspiriert von [Vorgängerprojekt](https://github.com/MiczFlor/RPi-Jukebox), [anderes DIY-Projekt](https://www.voss.earth/tonuino/) und der Idee, dass Kinderzimmer keine Cloud-Anbindung brauchen.*
