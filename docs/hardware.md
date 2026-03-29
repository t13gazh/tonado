# Hardware

Übersicht aller unterstützten Hardware-Komponenten, Verkabelung und Konfiguration.

## Raspberry Pi

Tonado läuft auf allen Raspberry Pi Modellen mit WLAN:

| Modell | RAM | Bewertung | Hinweis |
|---|---|---|---|
| **Pi Zero W** | 512 MB | Minimum | Funktioniert, aber langsamer Start (~15s). 32-bit OS verwenden. |
| **Pi Zero 2 W** | 512 MB | Gut | Quad-Core, deutlich schneller als Zero W |
| **Pi 3B+** | 1 GB | Empfohlen | Gutes Preis-Leistungs-Verhältnis |
| **Pi 4** | 1–8 GB | Optimal | Überdimensioniert, aber zukunftssicher |
| **Pi 5** | 4–8 GB | Optimal | Neuestes Modell, volle Leistung |

**Nicht unterstützt:** Pi 1, Pi B+ v1.2 und ältere Modelle ohne eingebautes WLAN.

> **Empfehlung für Einsteiger:** Pi 3B+ — günstig, genug Leistung, einfach zu bekommen.

## Audio

### Option 1: HifiBerry MiniAmp (empfohlen)

Der HifiBerry MiniAmp ist ein kleiner Verstärker, der direkt auf die GPIO-Leiste des Pi gesteckt wird. Kein Löten nötig.

**Vorteile:**
- Gute Klangqualität (I2S, digital)
- Verstärker eingebaut — Lautsprecher direkt anschließbar
- Kein Klinkenanschluss nötig

**Anschluss:**
1. MiniAmp auf die GPIO-Leiste des Pi aufstecken (passt nur in eine Richtung)
2. Lautsprecher (4–8 Ohm, 3W) an die Schraubklemmen anschließen
3. Tonado erkennt den HifiBerry automatisch bei der Installation

**Kompatible Lautsprecher:** Jeder kleine Lautsprecher mit 4–8 Ohm und 3–5 Watt. Gibt es ab 3 € bei den üblichen Shops.

> **Hinweis:** Der HifiBerry MiniAmp belegt GPIO 18, 19 und 25. GPIO 25 wird als Amp-Enable verwendet — das funktioniert auch zusammen mit dem RC522 RFID-Reader (getestet).

### Option 2: 3.5mm Klinkenausgang

Der eingebaute Klinkenausgang des Pi. Einfach, aber schlechtere Klangqualität.

**Vorteile:**
- Kein zusätzliches Board nötig
- Standard-Kopfhörer oder Aktivlautsprecher anschließbar

**Einschränkungen:**
- Nur Pi 3B+ und größer (Pi Zero W hat keinen Klinkenausgang)
- Analog-Ausgang — hörbares Rauschen bei geringer Lautstärke
- Externer Verstärker oder Aktivlautsprecher nötig

**Konfiguration:** Tonado erkennt automatisch ob ein HifiBerry vorhanden ist. Ohne HifiBerry wird der Onboard-Audio-Ausgang verwendet.

### Option 3: USB-Audio

Ein externer USB-DAC oder USB-Soundkarte.

**Konfiguration:** In `/etc/mpd.conf` das `device` unter `audio_output` anpassen:

```
audio_output {
    type    "alsa"
    name    "USB Audio"
    device  "hw:1,0"
}
```

Die Geräte-Nummer (`hw:1,0`) mit `aplay -l` herausfinden.

## RFID-Reader

Tonado erkennt RFID-Reader automatisch. Es werden drei Typen unterstützt:

### Option 1: RC522 (SPI) — getestet und empfohlen

Günstiger, weit verbreiteter Reader. Wird über SPI an die GPIO-Leiste angeschlossen.

**Verkabelung:**

| RC522 Pin | Pi Pin | GPIO | Funktion |
|---|---|---|---|
| SDA | Pin 24 | GPIO 8 (CE0) | Chip Select |
| SCK | Pin 23 | GPIO 11 (SCLK) | Clock |
| MOSI | Pin 19 | GPIO 10 (MOSI) | Data Out |
| MISO | Pin 21 | GPIO 9 (MISO) | Data In |
| GND | Pin 20 | GND | Masse |
| RST | Pin 22 | GPIO 25 | Reset |
| 3.3V | Pin 17 | 3.3V | Strom |

> **Wichtig:** Der RC522 arbeitet mit 3.3V. Niemals an 5V anschließen — das zerstört den Chip.

**Voraussetzung:** SPI muss aktiviert sein. Das Install-Script macht das automatisch. Manuell: In `/boot/firmware/config.txt` die Zeile `dtparam=spi=on` sicherstellen.

### Option 2: USB-RFID-Reader

USB-Reader, die sich als HID-Tastatur anmelden. Einfach per USB anstecken — keine Verkabelung, keine GPIO-Belegung.

**Vorteile:**
- Plug & Play, keine Verkabelung
- Funktioniert mit allen Pi-Modellen
- Keine SPI/I2C-Konfiguration nötig

**Einschränkung:** Belegt einen USB-Port (Pi Zero W hat nur einen).

**Kompatible Reader:** Die meisten 13.56 MHz USB-Reader, die MIFARE-Karten lesen und sich als HID-Keyboard anmelden. Häufig als "RFID USB Reader 13.56MHz" zu finden.

### Option 3: PN532 (I2C)

Vielseitiger Reader mit I2C-Anschluss. Kann auch NFC-Tags lesen.

**Verkabelung:**

| PN532 Pin | Pi Pin | GPIO | Funktion |
|---|---|---|---|
| SDA | Pin 3 | GPIO 2 (SDA) | I2C Data |
| SCL | Pin 5 | GPIO 3 (SCL) | I2C Clock |
| GND | Pin 6 | GND | Masse |
| VCC | Pin 1 | 3.3V | Strom |

> **Hinweis:** Am PN532-Board den DIP-Switch auf I2C stellen (nicht SPI oder UART).

**Voraussetzung:** I2C muss aktiviert sein. Das Install-Script macht das automatisch.

> **Status:** Noch nicht getestet. Wenn du einen PN532 hast und testen möchtest, melde dich gerne per [Issue](https://github.com/t13gazh/tonado/issues).

### Kompatible RFID-Chips

Tonado liest die **UID** (eindeutige Seriennummer) des Chips — kein Beschreiben nötig.

| Chip-Typ | Frequenz | Kompatibel |
|---|---|---|
| MIFARE Classic 1K | 13.56 MHz | Ja |
| MIFARE Classic 4K | 13.56 MHz | Ja |
| MIFARE Ultralight | 13.56 MHz | Ja |
| NTAG213/215/216 | 13.56 MHz | Ja |
| 125 kHz Chips | 125 kHz | Nein — falsche Frequenz |

Die Chips gibt es als Karten, Aufkleber, Schlüsselanhänger oder zum Einbauen in Figuren. Alle Formate funktionieren, solange sie 13.56 MHz verwenden.

## Gyro-Sensor (optional)

Der MPU6050 Gyro-Sensor ermöglicht Gesten-Steuerung:

| Geste | Aktion |
|---|---|
| Kippen links/rechts | Nächster/Vorheriger Titel |
| Kippen vor/zurück | Lautstärke ändern |
| Schütteln | Shuffle |

### Verkabelung

| MPU6050 Pin | Pi Pin | GPIO | Funktion |
|---|---|---|---|
| VCC | Pin 1 | 3.3V | Strom |
| GND | Pin 6 | GND | Masse |
| SDA | Pin 3 | GPIO 2 (SDA) | I2C Data |
| SCL | Pin 5 | GPIO 3 (SCL) | I2C Clock |

> **Hinweis:** Der MPU6050 und der PN532 teilen sich den I2C-Bus. Beide können gleichzeitig angeschlossen werden — sie haben unterschiedliche I2C-Adressen (MPU6050: 0x68, PN532: 0x24).

### Empfindlichkeit

Drei Profile, einstellbar über die App unter **Einstellungen > Gesten**:

| Profil | Beschreibung |
|---|---|
| Sanft | Kleine Bewegungen genügen — für vorsichtige Kinder |
| Normal | Standard — für die meisten Kinder |
| Wild | Kräftiges Kippen/Schütteln nötig — für wilde Kinder |

> **Status:** Bisher nur im Mock-Modus getestet. Hardware-Test steht noch aus.

## Beispiel-Konfigurationen

### Minimal (ca. 50 €)

- Pi Zero W
- USB-RFID-Reader
- USB-Lautsprecher oder 3.5mm Aktivlautsprecher (Pi 3B+ nötig)
- Kein Gyro

### Standard (ca. 80 €)

- Pi 3B+
- RC522 RFID-Reader (SPI)
- HifiBerry MiniAmp + kleiner Lautsprecher
- 5–10 RFID-Karten oder -Figuren

### Komplett (ca. 100 €)

- Pi 3B+ oder 4
- RC522 RFID-Reader (SPI)
- HifiBerry MiniAmp + kleiner Lautsprecher
- MPU6050 Gyro-Sensor
- 10+ RFID-Figuren
- Gehäuse (3D-Druck / Holzbox)

## GPIO-Belegung (Gesamtübersicht)

Wenn alle Komponenten angeschlossen sind:

```
Pin 1  (3.3V)  ← MPU6050 VCC, PN532 VCC
Pin 3  (SDA)   ← MPU6050 SDA, PN532 SDA
Pin 5  (SCL)   ← MPU6050 SCL, PN532 SCL
Pin 6  (GND)   ← MPU6050 GND, PN532 GND
Pin 17 (3.3V)  ← RC522 3.3V
Pin 19 (MOSI)  ← RC522 MOSI
Pin 20 (GND)   ← RC522 GND
Pin 21 (MISO)  ← RC522 MISO
Pin 22 (GPIO25) ← RC522 RST (+ HifiBerry Amp-Enable, Doppelnutzung OK)
Pin 23 (SCLK)  ← RC522 SCK
Pin 24 (CE0)   ← RC522 SDA

HifiBerry MiniAmp belegt zusätzlich: GPIO 18, 19 (I2S)
```

## Troubleshooting

### RFID-Reader wird nicht erkannt

```bash
# SPI aktiv?
ls /dev/spidev*
# Sollte /dev/spidev0.0 zeigen

# I2C aktiv?
ls /dev/i2c*
# Sollte /dev/i2c-1 zeigen

# USB-Reader angeschlossen?
ls /dev/hidraw*

# Hardware-Erkennung manuell ausführen
cd /opt/tonado && .venv/bin/python -c "from core.hardware.detect import detect_all; print(detect_all())"
```

### Kein Audio / HifiBerry nicht erkannt

```bash
# Audio-Geräte anzeigen
aplay -l

# HifiBerry in config.txt?
grep hifiberry /boot/firmware/config.txt

# MPD Audio-Ausgabe testen
mpc volume 50
mpc add http://st01.dlf.de/dlf/01/128/mp3/stream.mp3
mpc play
```

### Gyro reagiert nicht

```bash
# I2C-Geräte scannen
i2cdetect -y 1
# MPU6050 sollte auf Adresse 0x68 erscheinen
```
