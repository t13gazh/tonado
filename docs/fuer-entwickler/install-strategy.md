# Install-Strategie

Wie installieren Eltern Tonado auf ihrem Pi? Dieser Text beschreibt den aktuellen Stand und den Zielzustand, damit die Lücke zwischen Vision („auch für nicht-technische Eltern") und Realität („SSH + curl | sudo bash") explizit ist und nicht schleichend vergessen wird.

## Der SSH-Weg (für Bastler, erprobt)

**Zielgruppe:** technik-affine Eltern. In der [Vision](../VISION.md#zielgruppe) ist das die primäre Zielgruppe — sie haben einen Pi, trauen sich, einen zu kaufen, kennen SSH zumindest oberflächlich.

**Flow:**

1. Raspberry Pi Imager installieren.
2. Pi OS Lite auf SD-Karte schreiben, mit Hostname, SSH, WLAN-Zugangsdaten vorkonfigurieren.
3. Pi booten, per SSH verbinden.
4. `curl -sSL https://raw.githubusercontent.com/t13gazh/tonado/main/system/install.sh | sudo bash`
5. Warten (5–30 Minuten je nach Pi-Modell).
6. Browser öffnen, Box einrichten.

Dokumentiert in [`../fuer-bastler/installation.md`](../fuer-bastler/installation.md).

**Was daran gut ist:** Volle Kontrolle, Open-Source-typisch, schnell veränderbar.

**Was daran nicht passt:** Eine nicht-technische Mutter bricht spätestens bei „SSH" ab. Die UX-Vision („Zielgruppe sekundär: datenschutz-bewusste Eltern") wird vom Install-Schritt gefiltert — wer hierher kommt, muss sich erstmal durch technische Grundlagen arbeiten.

## Der Image-Weg (seit v0.4.0-beta, im Feldtest)

**Stand:** Das Pi-Image ist gebaut und wird mit jedem `v*`-Tag als Release veröffentlicht. Es wird per Raspberry Pi Imager („Eigenes Image") auf die SD-Karte geflasht; der erste Boot geht direkt in den Captive-Portal-Wizard, der Rest läuft im Browser. Der Pfad ist noch nicht mit nicht-technischen Eltern auf echter Hardware validiert.

**Flow:**

1. Raspberry Pi Imager installieren.
2. „Tonado"-Image (aus unseren Releases) auf SD-Karte schreiben.
3. Pi booten.
4. Handy mit dem AP „Tonado-Setup" verbinden, Browser öffnet sich automatisch.
5. Hardware-Wizard läuft durch, Eltern klicken sich durch, Box ist einsatzbereit.

**Was dafür gebaut wurde:**

- `pi-gen`-basierter Build unserer eigenen Image-Variante (zwei Images: Pi 3B+/4/5/Zero 2 W und Pi Zero W).
- Automatischer CI-Build, der bei jedem Tag ein neues Image erzeugt ([`pi-image-ci.md`](pi-image-ci.md)).
- Prüfsumme (SHA256) und Signatur (cosign keyless), damit Eltern ein gefälschtes Image erkennen können.
- Dokumentation für Eltern, die den Flash-Prozess erklärt, ohne SSH zu erwähnen: [`flashen.md`](../fuer-eltern/flashen.md).

## Die Lücke ehrlich benennen

Die Vision spricht von der „Freundin, die sagt: Kann ich auch so eine haben?". Der SSH-Weg kann diese Freundin nicht bedienen. Der Image-Weg soll sie bedienen können — bewiesen ist das erst, wenn nicht-technische Eltern ihn auf echter Hardware ohne Hilfe schaffen.

Der Fallback, solange diese Validierung aussteht, ist „jemand Technischer macht die Ersteinrichtung" (SSH-Weg). Das funktioniert für Maker und technik-affine Eltern (Zielgruppe 1 und 3 der Vision), nicht aber für Zielgruppe 2 (datenschutz-bewusste, nicht notwendigerweise technische Eltern).

## Entscheidungen

- **Keine paketierten Linux-Distros (.deb, Snap).** Tonado ist eine Box, keine Linux-Anwendung. Das Image IST das Deployment.
- **Kein Docker.** Pi Zero W wäre damit überfordert; außerdem verdeckt Docker die Hardware-Nähe (GPIO, SPI, I2C), auf die wir uns verlassen.
- **pi-gen als Build-Tool.** Es ist das Tool, mit dem das offizielle Pi OS gebaut wird — Debugging-Pfade sind bekannt.

## Konsequenzen für Contributors

- Features, die nur über SSH konfigurierbar sind, sind kein Produkt-Ende-Zustand, sondern höchstens Durchgangsetappe.
- Jedes neue Einstellungs-Detail sollte in der Web-App abbildbar sein, nicht nur in config.txt / Umgebungsvariablen.
- Das Bastler-`install.sh` (SSH-Pfad) muss idempotent bleiben, damit ein Re-Run keinen Schaden anrichtet. **Nicht** für das Image: dort sind die Install-Schritte zur Bake-Time ins Image gebacken, beim ersten Boot läuft nur `firstrun.service` (Geräte-Init, einmalig markergated) — das Image führt die `install.sh`-Schritte nicht bei jedem First-Boot aus. Details: [`pi-image-architecture.md`](pi-image-architecture.md).
