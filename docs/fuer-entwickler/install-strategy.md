# Install-Strategie

Wie installieren Eltern Tonado auf ihrem Pi? Dieser Text beschreibt den aktuellen Stand und den Zielzustand, damit die Lücke zwischen Vision („auch für nicht-technische Eltern") und Realität („SSH + curl | sudo bash") explizit ist und nicht schleichend vergessen wird.

## Heute (Alpha)

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

## Morgen (Beta, Meilenstein Richtung „für alle Eltern")

**Ziel:** Pi-Image, das per Raspberry Pi Imager oder `dd` auf die SD-Karte geflasht wird. Erster Boot geht direkt in den Captive-Portal-Wizard, der Rest läuft im Browser.

**Flow (Ziel):**

1. Raspberry Pi Imager installieren.
2. „Tonado"-Image (aus unseren Releases) auf SD-Karte schreiben.
3. Pi booten.
4. Handy mit dem AP „Tonado-Setup" verbinden, Browser öffnet sich automatisch.
5. Hardware-Wizard läuft durch, Eltern klicken sich durch, Box ist einsatzbereit.

**Was gebraucht wird:**

- `pi-gen`-basierter Build unserer eigenen Image-Variante.
- Automatischer CI-Build, der bei jedem Tag ein neues Image erzeugt.
- Optional: Checksum + signiertes Image, damit Eltern ein gefälschtes Image erkennen können.
- Dokumentation auf [`../fuer-eltern/`](../fuer-eltern/), die den Flash-Prozess erklärt, ohne SSH zu erwähnen.

## Die Lücke ehrlich benennen

Die Vision spricht von der „Freundin, die sagt: Kann ich auch so eine haben?". Die Alpha-Installation kann diese Freundin nicht bedienen. Das ist kein Bug, sondern der aktuelle Stand — aber er muss beim Beta-Meilenstein weg, sonst halten wir ein UX-Versprechen, das bei Schritt 1 bricht.

Der Fallback zwischen heute und dem Image ist „jemand Technischer macht die Ersteinrichtung". Das funktioniert für Maker und technik-affine Eltern (Zielgruppe 1 und 3 der Vision), nicht aber für Zielgruppe 2 (datenschutz-bewusste, nicht notwendigerweise technische Eltern). Diese Lücke gehört in den aktiven Backlog als Prio 3 / Beta-Ziel.

## Entscheidungen

- **Keine paketierten Linux-Distros (.deb, Snap).** Tonado ist eine Box, keine Linux-Anwendung. Das Image IST das Deployment.
- **Kein Docker.** Pi Zero W wäre damit überfordert; außerdem verdeckt Docker die Hardware-Nähe (GPIO, SPI, I2C), auf die wir uns verlassen.
- **pi-gen als Build-Tool.** Es ist das Tool, mit dem das offizielle Pi OS gebaut wird — Debugging-Pfade sind bekannt.

## Konsequenzen für Contributors

- Features, die nur über SSH konfigurierbar sind, sind kein Produkt-Ende-Zustand, sondern höchstens Durchgangsetappe.
- Jedes neue Einstellungs-Detail sollte in der Web-App abbildbar sein, nicht nur in config.txt / Umgebungsvariablen.
- Install-Script muss idempotent bleiben, damit es auf dem Image bei jedem First-Boot neu laufen könnte ohne Schaden anzurichten.
