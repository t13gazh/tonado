# Tonado

> Die Musikbox, die dir gehört.

Open-Source Kinder-Musikbox mit RFID-Figuren, gesteuert vom Smartphone. Raspberry Pi basiert, kein Abo, keine Cloud, keine Limits.

## Features

- **Figur auflegen, Musik hört los** — Kinder legen eine RFID-Figur oder -Karte auf, der Rest passiert von allein
- **Smartphone als Fernbedienung** — Musik verwalten, Figuren zuweisen, Lautstärke begrenzen, Einschlaftimer setzen
- **Eigene Musik, eigene Regeln** — MP3s hochladen, Internetradio, Podcasts — alles auf deinem Pi, nichts in der Cloud
- **Kindersicher** — PIN-geschützte Eltern-Einstellungen, maximale Lautstärke, automatischer Einschlaftimer
- **Gesten-Steuerung** — Box kippen zum Skippen, schütteln für Shuffle (optional, mit Gyro-Sensor)
- **Open Source** — MIT-Lizenz, vollständig anpassbar, keine versteckten Kosten

## Was du brauchst

| Komponente | Beispiel | ca. Preis |
|---|---|---|
| Raspberry Pi | Zero W, 3B+, 4 oder 5 | 15–50 € |
| microSD-Karte | mind. 16 GB, Class 10 | 8 € |
| Lautsprecher | HifiBerry MiniAmp + kleiner Lautsprecher | 15–25 € |
| RFID-Reader | RC522 (SPI) oder USB-RFID-Reader | 5–10 € |
| RFID-Figuren oder -Karten | 13.56 MHz (MIFARE Classic o.ä.) | 5 € / 10 Stk |
| USB-Netzteil | 5V, passend zum Pi-Modell | 10 € |
| **Optional:** Gyro-Sensor | MPU6050 — für Gesten-Steuerung | 3 € |
| **Optional:** Gehäuse | 3D-Druck, Holzbox, Brotdose, ... | variabel |

**Gesamtkosten: ca. 70–100 €** — eigene Musik, kein Abo, keine laufenden Kosten.

Alle Details zu Modellen, Optionen und Verkabelung: **[Hardware-Anleitung](docs/hardware.md)**

## Schnellstart

### 1. SD-Karte vorbereiten

1. [Raspberry Pi Imager](https://www.raspberrypi.com/software/) installieren
2. **Raspberry Pi OS Lite** auswählen (64-bit, oder 32-bit für Pi Zero W)
3. In den Einstellungen: Hostname, SSH, WLAN, Benutzername `pi` konfigurieren
4. Image auf SD-Karte schreiben

### 2. Tonado installieren

Per SSH auf dem Pi einloggen und einen Befehl ausführen:

```bash
ssh pi@<hostname>.local
curl -sSL https://raw.githubusercontent.com/t13gazh/tonado/main/system/install.sh | sudo bash
```

Das Script erledigt alles automatisch — Pakete, Audio, RFID, Webserver. Dauert 5–15 Minuten je nach Pi-Modell. Falls ein Neustart nötig ist: `sudo reboot`

### 3. Loslegen

Browser öffnen, `http://<hostname>.local` aufrufen, Musik hochladen, Figuren zuweisen — fertig.

Ausführliche Anleitung mit Troubleshooting: **[Installationsanleitung](docs/installation.md)**

## Aktualisierung

Über die App: **Einstellungen > System > Nach Updates suchen**

Oder per SSH:

```bash
cd /opt/tonado && sudo -u pi git pull && sudo systemctl restart tonado
```

## Für Entwickler

Tonado ist gebaut mit **Svelte 5**, **FastAPI**, **MPD** und **SQLite**. Hardware-Services laufen auf Windows/Mac im Mock-Modus.

Entwicklungsumgebung, Tests, Deployment: **[Entwickler-Anleitung](docs/entwicklung.md)**

## Status

> **Alpha (v0.1.0)** — Tonado funktioniert, ist aber noch nicht für Endnutzer verpackt.

**Was funktioniert:** Player, Bibliothek, Figuren-Wizard, Eltern-Einstellungen, Hardware-Erkennung, Browser-Audio, automatische Updates.

**Was noch kommt:** Fertiges Image zum Flashen, weitere Hardware testen, bessere Fehlermeldungen, Mehrsprachigkeit.

## Mitmachen

- **Testen:** Probier Tonado aus und melde Probleme als [Issue](https://github.com/t13gazh/tonado/issues)
- **Hardware testen:** Wir suchen Tester mit Pi 3B+/4/5, PN532 (I2C) und USB-RFID-Readern
- **Übersetzen:** Tonado ist auf Deutsch — Hilfe bei weiteren Sprachen willkommen (`web/src/lib/i18n/`)

## Lizenz

MIT License — siehe [LICENSE](LICENSE)
