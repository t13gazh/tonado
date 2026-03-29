# Installation

Vollständige Anleitung zur Installation von Tonado auf einem Raspberry Pi.

> **Schnellstart:** Die Kurzversion findest du in der [README](../README.md#installation).

## Voraussetzungen

- Raspberry Pi (Zero W, 3B+, 4 oder 5) mit Netzteil
- microSD-Karte, mind. 16 GB, Class 10
- WLAN-Zugang (der Pi muss ins Heimnetzwerk)
- Ein Computer mit [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
- Ein Smartphone oder Computer im selben Netzwerk

## Schritt 1: SD-Karte vorbereiten

1. Raspberry Pi Imager herunterladen und installieren
2. Unter **Betriebssystem** wählen:
   - **Raspberry Pi OS Lite (64-bit)** — für Pi 3B+, 4, 5
   - **Raspberry Pi OS Lite (32-bit)** — für Pi Zero W
3. Unter **SD-Karte** eure microSD auswählen
4. Auf **Einstellungen bearbeiten** klicken (Zahnrad-Icon unten rechts):

| Einstellung | Wert |
|---|---|
| Hostname | Frei wählbar, z.B. `tonado`. Erreichbar als `http://<hostname>.local` |
| SSH aktivieren | Ja, mit Passwort-Authentifizierung |
| Benutzername | `pi` (empfohlen) |
| Passwort | Frei wählen — wird für SSH-Zugang benötigt |
| WLAN | SSID und Passwort eures Heimnetzwerks |
| Land | `DE` |
| Zeitzone | `Europe/Berlin` |
| Tastaturlayout | `de` |

5. **Speichern** und **Schreiben** klicken
6. Warten bis der Vorgang abgeschlossen ist, SD-Karte entnehmen

> **Hinweis:** Der Hostname bestimmt, unter welcher Adresse der Pi im Netzwerk erreichbar ist. Wer `tonado` wählt, erreicht die Box später unter `http://tonado.local`.

## Schritt 2: Erster Start und SSH-Verbindung

1. SD-Karte in den Pi einsetzen
2. Netzteil anschließen — der Pi startet automatisch
3. **2–3 Minuten warten** — beim ersten Start wird das Dateisystem erweitert und die Konfiguration angewendet
4. Per SSH verbinden:

```bash
ssh pi@<hostname>.local
```

Beispiel: Wenn ihr als Hostname `tonado` gewählt habt:

```bash
ssh pi@tonado.local
```

Beim ersten Verbinden fragt SSH nach dem Fingerprint — mit `yes` bestätigen.

### SSH funktioniert nicht?

| Problem | Lösung |
|---|---|
| `<hostname>.local` wird nicht gefunden | Im Router nach der IP-Adresse des Pi suchen, dann `ssh pi@192.168.x.x` verwenden |
| Windows findet `.local` nicht | Bonjour installieren (kommt z.B. mit iTunes) oder IP-Adresse verwenden |
| Verbindung abgelehnt | Noch 1–2 Minuten warten, der Pi ist noch nicht fertig |
| Falsches Passwort | Im Imager nochmal prüfen, SD-Karte ggf. neu schreiben |

## Schritt 3: Tonado installieren

Auf dem Pi folgenden Befehl ausführen:

```bash
curl -sSL https://raw.githubusercontent.com/t13gazh/tonado/main/system/install.sh | sudo bash
```

### Was das Script macht

| Schritt | Beschreibung |
|---|---|
| 1/10 | System-Pakete installieren (MPD, Python, Nginx, Git) |
| 2/10 | Verzeichnisse erstellen (Musik, Konfiguration) |
| 3/10 | Tonado von GitHub klonen und Python-Umgebung einrichten |
| 4/10 | Audio konfigurieren (HifiBerry erkennen oder Onboard-Audio) |
| 5/10 | MPD (Music Player Daemon) konfigurieren |
| 6/10 | Hardware-Interfaces prüfen und aktivieren (SPI, I2C) |
| 7/10 | systemd-Service einrichten (Tonado startet automatisch beim Booten) |
| 8/10 | Frontend prüfen (ist im Repository enthalten) |
| 9/10 | Nginx als Webserver einrichten (Port 80) |
| 10/10 | Hardware-Erkennung ausführen |

### Dauer

| Pi-Modell | ca. Dauer |
|---|---|
| Pi Zero W | 10–15 Minuten |
| Pi 3B+ | 5–8 Minuten |
| Pi 4/5 | 3–5 Minuten |

### Nach der Installation

Das Script zeigt am Ende die Adresse an, unter der Tonado erreichbar ist.

Falls ein **Neustart** nötig ist (wegen SPI/I2C/Audio-Konfiguration):

```bash
sudo reboot
```

Nach dem Neustart (ca. 30 Sekunden warten):

1. Browser öffnen
2. `http://<hostname>.local` aufrufen (oder `http://<IP-Adresse>`)
3. Die Tonado-App sollte erscheinen

> **Tipp:** Falls `<hostname>.local` auf dem Smartphone nicht funktioniert, verwende die IP-Adresse (wird im Setup-Wizard angezeigt). Auf Android kann "Privates DNS" in den Netzwerk-Einstellungen die `.local`-Auflösung blockieren — in dem Fall auf "Aus" stellen.

## Schritt 4: Musik aufspielen und loslegen

1. Im Tab **Bibliothek** Musik hochladen (MP3, FLAC, OGG, WAV)
2. Optional: Im Tab **Figuren** eine RFID-Karte oder -Figur scannen und Musik zuweisen
3. Karte auflegen — Musik spielt!

> **Kein RFID-Reader?** Kein Problem — Tonado funktioniert auch ohne. Musik lässt sich komplett über die App steuern. Der RFID-Reader ist optional und kann jederzeit nachgerüstet werden.

## Aktualisierung

### Über die App

**Einstellungen > System > Nach Updates suchen**

Tonado prüft ob eine neue Version verfügbar ist und aktualisiert sich selbst.

### Per SSH

```bash
cd /opt/tonado && sudo -u pi git pull && sudo systemctl restart tonado
```

## Deinstallation

Falls du Tonado entfernen möchtest:

```bash
sudo systemctl stop tonado
sudo systemctl disable tonado
sudo rm /etc/systemd/system/tonado.service
sudo rm -rf /opt/tonado
sudo rm /etc/nginx/sites-enabled/tonado
sudo systemctl restart nginx
```

Die Musik-Dateien liegen unter `/home/pi/tonado/media/` und werden nicht automatisch gelöscht.

## Fehlerbehebung

### Tonado startet nicht

```bash
# Service-Status prüfen
sudo systemctl status tonado

# Logs anzeigen
sudo journalctl -u tonado -n 50
```

### Kein Audio

```bash
# Audio-Ausgänge anzeigen
aplay -l

# MPD-Status prüfen
mpc status
```

Siehe auch: [Hardware-Anleitung](hardware.md#audio)

### Webseite nicht erreichbar

```bash
# Nginx prüfen
sudo systemctl status nginx
sudo nginx -t

# Tonado läuft?
curl -s http://localhost:8080/api/system/health
```
