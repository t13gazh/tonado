# Tonado

**Die Musikbox, die dir gehört.**

Tonado verwandelt einen Raspberry Pi in eine Musikbox für Kinder. Figur oder Karte auflegen — Musik spielt. Alles andere steuern Eltern bequem vom Smartphone. Kein Abo, keine Cloud, keine Limits.

## Features

- **Figur auflegen, Musik hört los** — Kinder legen eine RFID-Figur oder -Karte auf, der Rest passiert von allein
- **Smartphone als Fernbedienung** — Musik verwalten, Figuren zuweisen, Lautstärke begrenzen, Einschlaftimer setzen
- **Eigene Musik, eigene Regeln** — MP3s hochladen, Internetradio, Podcasts — alles auf deinem Pi, nichts in der Cloud
- **Kindersicher** — PIN-geschützte Eltern-Einstellungen, maximale Lautstärke, automatischer Einschlaftimer
- **Gesten-Steuerung** — Box kippen zum Skippen, schütteln für Shuffle (optional, mit Gyro-Sensor)
- **Open Source** — MIT-Lizenz, vollständig anpassbar, keine versteckten Kosten

## So funktioniert's

1. **Tonado-Image auf SD-Karte schreiben** — z.B. mit dem Raspberry Pi Imager
2. **SD-Karte in den Pi stecken und einschalten**
3. **Mit dem WLAN „Tonado-Setup" verbinden** — der Einrichtungsassistent führt durch den Rest

Danach öffnest du die Tonado-App im Browser auf deinem Smartphone, lädst Musik hoch, weist sie einer Figur zu — fertig.

## Was du brauchst

| Komponente | Beispiel | ca. Preis |
|---|---|---|
| Raspberry Pi | Zero W, 3B+, 4 oder 5 | 15–50 € |
| microSD-Karte | mind. 16 GB, Class 10 | 8 € |
| Lautsprecher | z.B. HifiBerry MiniAmp + kleiner Lautsprecher | 15–25 € |
| RFID-Reader | z.B. RC522 (SPI) | 5–10 € |
| Figuren oder Karten | RFID-Chips (13.56 MHz) | 5 € / 10 Stk |
| USB-Netzteil | 5V, passend zum Pi-Modell | 10 € |
| **Optional:** Gyro-Sensor | MPU6050 — für Gesten-Steuerung | 3 € |
| **Optional:** Gehäuse | 3D-Druck, Holzbox, ... | variabel |

**Gesamtkosten: ca. 70–100 €** — eigene Musik, kein Abo, keine laufenden Kosten.

<!-- Screenshots folgen -->

## Status

> **Alpha (v0.1.0)** — Tonado funktioniert, ist aber noch nicht für Endnutzer verpackt.

**Was funktioniert:**
- Player mit Live-Fortschritt, Seek, Shuffle, Repeat, Lautstärke
- Bibliothek mit Ordnern, Internetradio, Podcasts
- Figuren-Wizard: Figur scannen, Inhalt zuweisen
- Eltern-Einstellungen: PIN, Einschlaftimer, Lautstärkelimit
- Hardware-Erkennung: RC522 RFID-Reader wird automatisch erkannt
- Browser-Audio: Musik direkt auf dem Smartphone hören

**Was noch kommt:**
- Fertiges Image zum Flashen (aktuell noch manuelle Installation)
- Weitere RFID-Reader (PN532, USB) und Pi-Modelle testen
- Captive-Portal-Ersteinrichtung End-to-End
- Bessere Fehlermeldungen wenn Hardware fehlt

Wir suchen Tester! Wenn du einen Pi und RFID-Reader hast, melde dich gerne.

## Für Entwickler

Tonado ist gebaut mit **Svelte 5**, **FastAPI**, **MPD** und **SQLite**.

```
web/          → Frontend (Svelte 5 + Tailwind CSS, PWA)
core/         → Backend (Python / FastAPI)
docs/         → Dokumentation
tests/        → Tests
install.sh    → Installations-Script
```

Entwicklungsumgebung einrichten:

```bash
# Backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"    # Windows
# .venv/bin/pip install -e ".[dev]"      # Linux/Mac

# Frontend
cd web && npm install && npm run dev

# Backend starten
uvicorn core.main:app --host 127.0.0.1 --port 8080
```

Beiträge sind willkommen — schau in die [Issues](https://github.com/t13gazh/tonado/issues) oder eröffne eine neue.

## Lizenz

MIT License — siehe [LICENSE](LICENSE)
