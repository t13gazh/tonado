# Pi-Image-Architektur

> **Status:** Entwurf, noch nicht implementiert. Referenz für die Welle „Pi-Image zum Flashen" aus [`BACKLOG.md`](../../BACKLOG.md#prio-3--wertvolle-erweiterungen) (Prio 3).
>
> **Zielversion:** `v0.4.0-beta` (erste Image-fähige Tonado-Release).
>
> **Vorarbeit:** [`install-strategy.md`](install-strategy.md) beschreibt die UX-Lücke zwischen SSH-Installation (Alpha) und flashbarem Image (Beta-Ziel). Dieses Dokument beschreibt die technische Umsetzung.

## 0. Abgrenzung zum heutigen Stand

`system/install.sh` bleibt als Bastler-Pfad bestehen („Pi OS Lite + curl | sudo bash"). Das Image ist ein **zusätzlicher** Pfad, kein Ersatz. Beide müssen denselben Zielzustand erreichen, sonst pflegen wir zwei Installationen parallel.

Heutige Referenzen, die dieses Dokument voraussetzt:
- [`system/install.sh`](../../system/install.sh) — 11 Install-Schritte, idempotent, Marker `/var/lib/tonado/install.done`
- [`system/setup-ap.sh`](../../system/setup-ap.sh) — Captive-Portal-Start/-Stop (hostapd + dnsmasq auf `192.168.4.1`)
- [`system/tonado-ap.service`](../../system/tonado-ap.service) — Triggert `setup-ap.sh` nur wenn `/opt/tonado/config/.setup-complete` nicht existiert
- [`system/tonado.service`](../../system/tonado.service) — Uvicorn auf `127.0.0.1:8080`, Nginx davor auf Port 80
- [`core/services/system_service.py`](../../core/services/system_service.py) — `apply_update` nutzt `git pull --ff-only` gegen `origin/main`, vorab `git reset --hard HEAD` + `git clean -fd web/build/`

## 1. Ziel & Nutzerweg

**Verkaufsversprechen für Eltern:** „SD-Karte mit Tonado flashen, Pi einstecken, Handy mit dem Tonado-WLAN verbinden, fertig konfigurieren — 10 Minuten, kein SSH, kein Terminal."

### Nutzerweg Schritt für Schritt

| # | Aktion Eltern | Dauer | Was im Hintergrund passiert |
|---|---------------|-------|-----------------------------|
| 1 | Raspberry Pi Imager öffnen, „Tonado" im Custom-Image-Feld wählen | 1 min | Imager lädt `tonado-<version>-<arch>.img.xz` + prüft SHA256 |
| 2 | SD-Karte flashen | 2–4 min | Imager schreibt Image, erweitert Root-Partition beim ersten Boot nicht nötig (siehe 2.4) |
| 3 | SD-Karte rein, Strom an | 30–60 s | First-Boot-Expand, `firstrun.service` generiert gerätespezifische Secrets, `tonado-ap.service` startet AP |
| 4 | Handy → WLAN „Tonado-Setup" verbinden (PSK auf Rückseite / LED-Code — siehe 7) | 30 s | Captive-Portal-Redirect öffnet Setup-Wizard im Browser |
| 5 | Wizard durchklicken (Heim-WLAN, Audio-Output, ggf. Figuren) | 3–5 min | Bestehender Setup-Wizard (Meilenstein 1, Phase 3), am Ende `touch /opt/tonado/config/.setup-complete` |
| 6 | Pi rebootet ins Heim-WLAN, Handy mit Heim-WLAN verbinden, Box via `tonado.local` erreichen | 30 s | `tonado-ap.service` überspringt sich wegen `ConditionPathExists=!` |

**Was im Image vorbereitet ist (Bake-Time):**
- Komplettes `/opt/tonado/` inkl. Git-History, `.venv` und `web/build/`
- Alle Debian-Pakete: `python3`, `mpd`, `nginx`, `hostapd`, `dnsmasq`, `network-manager`, `avahi-daemon`, …
- Python-Dependencies vorinstalliert (`.venv` im Image — siehe 2.3)
- Systemd-Units aktiviert: `mpd`, `nginx`, `tonado`, `tonado-ap`, `firstrun`
- Nginx-Config, MPD-Config, sudoers.d-Drop-In
- `/boot/firmware/config.txt` bereits mit `dtparam=spi=on`, `dtparam=i2c_arm=on`, gpio-shutdown/poweroff (OnOff-SHIM), ohne HifiBerry-Overlay (wird im Wizard gesetzt)

**Was beim First Boot passiert (`firstrun.service`, einmalig):**
- Gerätespezifische Secrets generieren (Setup-AP-PSK, SSH-Host-Keys rotieren, evtl. Default-PIN-Salt)
- `/etc/machine-id` neu (Debian-Standard-First-Boot)
- Dateisystem auf SD-Karten-Größe expandieren (`raspi-config --expand-rootfs` Äquivalent, wird von Pi OS Lite übernommen wenn vorhanden)
- Self-Disable (`systemctl disable firstrun.service`)

**Was beim ersten Setup-Wizard passiert:**
- WLAN-Credentials via `nmcli` in NetworkManager schreiben
- Heim-WLAN verbinden, AP-Service beim nächsten Reboot inaktiv (Flag-Datei gesetzt)
- Hardware-Detection läuft, Audio-Overlay wird ggf. nachträglich in `config.txt` geschrieben → Reboot-Prompt
- Alles Weitere wie heute in [`core/api/`](../../core/api/) + Svelte-Wizard

### Widerspruch zu `install-strategy.md`

Die heutige Strategie-Doku sagt: *„Install-Script muss idempotent bleiben, damit es auf dem Image bei jedem First-Boot neu laufen könnte ohne Schaden anzurichten."* Das passt **nicht** mehr zur hier vorgeschlagenen Architektur. Im Image laufen die 11 Install-Schritte **zur Bake-Time im pi-gen-Stage**, nicht beim First-Boot. Am Pi läuft beim First-Boot nur noch `firstrun.service` (Secrets + Flags). Das ist schneller (kein apt-update über langsames AP, kein pip install auf 512 MB RAM) und robuster (keine Netzwerk-Abhängigkeit beim ersten Start).

Die Idempotenz-Anforderung bleibt trotzdem gültig — aber als Eigenschaft des Bastler-Pfads, nicht als Image-First-Boot-Behavior. Strategy-Doku entsprechend anpassen, wenn dieses Dokument approved ist.

## 2. Image-Struktur (pi-gen)

### 2.1 Stage-Layout

Wir basieren auf [`RPi-Distro/pi-gen`](https://github.com/RPi-Distro/pi-gen) und fügen eine eigene `stage-tonado` **nach** `stage2` (Lite-Image mit SSH) ein. Stages 3–5 (Desktop) bauen wir nicht. Der pi-gen-Konfig-File (`config`) setzt:

```bash
IMG_NAME=tonado
ENABLE_SSH=1          # für Bastler-Debug, Default-Passwort entfernt (siehe 7)
STAGE_LIST="stage0 stage1 stage2 stage-tonado"
TARGET_HOSTNAME=tonado
```

### 2.2 `stage-tonado/` Struktur

```
stage-tonado/
├── prerun.sh                    # Stage-Hook, aus stage2 kopieren
├── EXPORT_IMAGE                 # Datei markiert: „Image aus dieser Stage exportieren"
├── EXPORT_NOOBS                 # weglassen, wir brauchen kein NOOBS
├── 00-packages                  # apt-get install Liste
├── 00-packages-nr               # apt-get install --no-install-recommends Liste
├── 01-sys-tweaks/
│   ├── 00-run.sh                # systemctl enable für alle Tonado-Units
│   └── files/
│       ├── etc/
│       │   ├── systemd/system/tonado.service
│       │   ├── systemd/system/tonado-ap.service
│       │   ├── systemd/system/firstrun.service
│       │   ├── nginx/sites-available/tonado
│       │   ├── mpd.conf
│       │   ├── sudoers.d/tonado
│       │   └── systemd/journald.conf.d/tonado.conf
│       └── boot/firmware/
│           └── config.txt.append       # wird an stage2-config.txt angehängt
├── 02-tonado-code/
│   ├── 00-run-chroot.sh         # läuft IM Chroot: git clone, pip install
│   └── files/
│       └── (leer — Code kommt per git clone im run-chroot)
└── 03-tonado-finalize/
    └── 00-run.sh                # Permissions, Marker-Dateien, cleanup
```

### 2.3 Package-Liste (`00-packages`)

Erweitert gegenüber `install.sh` Schritt 1 — wir brauchen zusätzlich Build-Kram für pip-Wheels, der aber nach Setup wieder raus kann:

```
# Runtime
python3 python3-venv python3-pip
mpd mpc
nginx
hostapd dnsmasq
network-manager
avahi-daemon
i2c-tools spi-tools
git
# Build (für pip install, wird am Ende von 03-tonado-finalize wieder purged)
python3-dev build-essential libffi-dev
```

**Begründung `network-manager`:** Pi OS Lite Bookworm nutzt per Default NetworkManager. Wir brauchen ihn für `nmcli` im Wizard (WLAN-Credentials persistent speichern).

**Nicht im Image (Ressourcen-Ersparnis):**
- ~~`nodejs` / `npm`~~ — Frontend wird **im Build-Container** gebaut, nicht auf dem Pi. Entspricht `feedback_cross_compile.md`.
- ~~`curl`/`wget` zum Laufzeit-Download~~ — alles liegt schon im Image.
- ~~Python-Compile-Toolchain zur Laufzeit~~ — nur zur Bake-Time, dann `apt-get purge`.

### 2.4 Python-Dependencies im Image

Im Chroot-Script `02-tonado-code/00-run-chroot.sh`:

```bash
#!/bin/bash -e
# Läuft IM Chroot (qemu-arm-static). git ist installiert.
on_chroot << EOF
git clone https://github.com/t13gazh/tonado.git /opt/tonado
cd /opt/tonado
git checkout v${TONADO_VERSION}          # aus pi-gen config.env
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -e ".[pi]" -q
# Frontend ist als web/build/ im Repo committed — kein npm nötig.
EOF
```

**Entscheidung: venv im Image, nicht Wheels-Cache.** Vorteil: First-Boot ist bereits lauffähig, kein Pi-seitiger `pip install` über langsames WLAN. Nachteil: Image wird um ~80 MB größer (venv mit allen Deps). Akzeptabel.

**Tag-Pinning statt `main`.** Der Image-Build checkt einen **Release-Tag** (`v0.4.0-beta`) aus, nie `main`. Warum: Der Image-Build-CI läuft nach dem Tag-Push; wenn er `main` auscheckte, würden Post-Tag-Commits silent mit reingeraten. Das Tag ist reproduzierbar.

### 2.5 Boot-Config (`01-sys-tweaks/files/boot/firmware/config.txt.append`)

Was heute `install.sh` nachträglich reinschreibt, schreiben wir vor:

```
# Tonado: Hardware-Interfaces (setup wizard kann HifiBerry später aktivieren)
dtparam=spi=on
dtparam=i2c_arm=on

# Tonado: OnOff SHIM (GPIO 17 = button, GPIO 4 = power-off)
dtoverlay=gpio-shutdown,gpio_pin=17,active_low=1
dtoverlay=gpio-poweroff,gpiopin=4,active_low=1
```

**HifiBerry-Overlay bleibt auskommentiert / nicht gesetzt.** Wizard schreibt es erst wenn im Audio-Step gewählt, weil das `dtparam=audio=on` exklusiv verdrängt.

**IPv6-Disable in `cmdline.txt`:** ebenfalls im Image vorbereiten, spart 512-MB-RAM-Pi im First-Boot.

### 2.6 Post-Install-Scripts in der Stage

`03-tonado-finalize/00-run.sh` (läuft zur Bake-Time außerhalb vom Chroot):

```bash
#!/bin/bash -e
# Post-Install-Cleanup
on_chroot << EOF
# Hardening: Build-Deps wieder raus
apt-get purge -y python3-dev build-essential libffi-dev
apt-get autoremove -y
apt-get clean

# Permissions
chown -R pi:pi /opt/tonado
chmod -R 755 /opt/tonado/web/build

# Services aktivieren (aber nicht starten — passiert erst beim Boot)
systemctl enable mpd
systemctl enable nginx
systemctl enable tonado.service
systemctl enable tonado-ap.service
systemctl enable firstrun.service
systemctl enable avahi-daemon

# Gruppen-Mitgliedschaft
usermod -aG audio,spi,i2c,gpio pi
usermod -aG pi mpd

# Install-Marker setzen — damit installer.sh (wenn Bastler ihn später laufen lässt)
# erkennt „ist Image, nicht anfassen" und sofort short-circuited.
mkdir -p /var/lib/tonado
cat > /var/lib/tonado/install.done <<MARKER
Tonado image-installed $(date -Iseconds)
source=pi-gen
tonado_version=${TONADO_VERSION}
MARKER

# MPD-Datenbank initialisieren (leeres Music-Dir)
mkdir -p /home/pi/tonado/media/.playlists /home/pi/tonado/config
chown -R pi:pi /home/pi/tonado
EOF
```

## 3. Frontend im Image

**Problem:** `web/build/` ist im Repo committed ([`feedback_prebuilt_frontend.md`](#)), aber bei Zwischen-Commits kann es zu Main passen und der Tag-Commit hat die richtige Version oder nicht.

**Entscheidung: Tag-Commit ist Single Source of Truth.**

1. Release-Workflow (manuell oder via GitHub Actions) baut `web/build/`, committed, taggt `v0.4.0-beta`, pusht Tag.
2. Image-Build-CI checkt **den Tag aus**, nicht `main`. Wenn `web/build/index.html` fehlt oder der Hash nicht passt: **Fail Fast**, kein Image.
3. Zusätzliche Sicherung: Build-CI kann optional `npm install && npm run build` im Docker-Container laufen lassen und das Ergebnis gegen das committete `web/build/` byte-für-byte vergleichen. Wenn Abweichung → Fail Fast. Das deckt den Fall „Release vergessen Frontend zu bauen" ab.

**Node im Image: nein.** Bleibt aus ([`feedback_cross_compile.md`](#)). Build passiert im CI-Container, Pi sieht nie Node.

**Konsistenz zu system_service.apply_update:** Das heutige Update macht `git pull --ff-only` + `git clean -fd web/build/` — der Clean-Schritt löscht Pi-lokale Build-Artefakte und holt die Repo-Version wieder. Das ist kompatibel zum Image, weil der Image-initiale Zustand exakt der Tag-State ist. Also: kein Fallstrick.

## 4. First-Boot-Service

### 4.1 Drei unabhängige Systemd-Units

| Unit | Zweck | Trigger | Self-Disable? |
|------|-------|---------|---------------|
| `firstrun.service` | Einmalige Geräte-Init (Secrets, Expand-FS-Fallback) | `ConditionFirstBoot=yes` + `ConditionPathExists=!/var/lib/tonado/firstrun.done` | Ja, via Marker-Datei |
| `tonado-ap.service` | Setup-AP nur wenn noch kein Heim-WLAN | `ConditionPathExists=!/opt/tonado/config/.setup-complete` | Nein — wird bei WLAN-Verlust wieder aktiv (siehe 4.3) |
| `tonado.service` | Die Haupt-App | `After=network.target mpd.service` | Nein — permanent aktiv |

### 4.2 `firstrun.service` (neu)

```ini
[Unit]
Description=Tonado First-Boot Init
ConditionPathExists=!/var/lib/tonado/firstrun.done
Before=tonado-ap.service tonado.service
DefaultDependencies=no
After=systemd-remount-fs.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/opt/tonado/system/firstrun.sh

[Install]
WantedBy=multi-user.target
```

Das Script (`system/firstrun.sh`, neu zu erstellen) macht:
- SSH-Host-Keys regenerieren (im Image sind sie leer, siehe 7)
- Setup-AP-PSK generieren (16 Zeichen base32, in `/opt/tonado/config/setup-ap.psk`)
- `hostapd.conf`-Template mit dem PSK rendern
- Marker `/var/lib/tonado/firstrun.done` schreiben

### 4.3 Flag-Datei `.setup-complete`

Die heutige Logik (`ConditionPathExists=!/opt/tonado/config/.setup-complete`) bleibt. Sie wird vom Setup-Wizard am Ende des WLAN-Steps (oder erst am Ende des gesamten Wizards — siehe Product-Owner-Frage Q4) angelegt. Wichtig:

- **Bei späterem WLAN-Verlust:** Der AP soll sich **nicht** automatisch wieder aufspannen. Sonst verliert man die Kontrolle, wenn das Heim-WLAN einmal 5 Minuten ausfällt. Stattdessen: manuelle WLAN-Rettung über physischen Knopf (Reset-Flow, heute noch nicht implementiert — eigene Welle, siehe Product-Owner-Frage Q5).
- **Bei Image-Reflash:** Neue SD-Karte hat kein `.setup-complete` → AP wieder aktiv. Korrekt.

### 4.4 Captive-Portal-Redirect

`setup-ap.sh` nutzt schon `address=/#/${AP_IP}` in dnsmasq — alle DNS-Anfragen gehen auf den Pi. Das Handy triggert den Captive-Portal-Check (z.B. `http://connectivitycheck.gstatic.com/generate_204`), kriegt den Pi geliefert, der Browser öffnet sich.

**Nginx muss auf Port 80 einen Redirect / SPA für den Wizard liefern** — tut er schon laut `install.sh` Step 9. Das ist kompatibel. Einzige Ergänzung: Nginx muss den Captive-Portal-Hostnamen (beliebig) auf `/` mappen. Dank `server_name _;` ist das bereits der Fall.

## 5. Varianten-Strategie

### 5.1 Empfehlung: eine 64-bit-Variante + eine 32-bit-Variante

| Variante | Hardware | pi-gen-Flag | Geschätzte Größe (uncompressed / xz) |
|----------|----------|-------------|---------------------------------------|
| `tonado-<version>-arm64.img.xz` | Pi 3B+, 4, 5, Zero 2 W | `RELEASE=bookworm ARCH=arm64` (= Standard) | 2.2 GB / 620 MB |
| `tonado-<version>-armhf.img.xz` | Pi Zero W (original) | `RELEASE=bookworm ARCH=armhf` (siehe [pi-gen docs](https://github.com/RPi-Distro/pi-gen#pi-gen-on-armhf-aka-32-bit)) | 2.0 GB / 560 MB |

**Warum zwei Varianten?** Pi Zero W hat BCM2835 (ARMv6) — läuft **nur** auf 32-bit. Alle anderen Pi laufen auf 64-bit. Eine „universal"-32-bit-Variante auf Pi 4/5 wäre ein Performance-Witz.

**Nicht unterstützt:**
- Pi 1 Model B+ (ARMv6, kein WiFi) — wie bisher ausgeschlossen.
- NOOBS — pi-gen baut eh nur `.img`, kein NOOBS-Paket.

### 5.2 Image-Größe realistisch schätzen

Basis Bookworm Lite (arm64): ~1.1 GB uncompressed.

Tonado-Addon:
- Debian Packages (mpd, nginx, hostapd, dnsmasq, network-manager, avahi): ~280 MB
- Python venv mit Deps (`.[pi]` inkl. fastapi, uvicorn, pydantic, httpx, mutagen, PyJWT, python-mpd2, aiosqlite, defusedxml, python-multipart, spidev, smbus2, RPi.GPIO, gpiod): ~220 MB
- Tonado Source + web/build: ~15 MB
- OnOff-SHIM / Captive-Portal-Assets: <1 MB

**Summe uncompressed:** ~1.6 GB. Auf 2 GB padded (pi-gen macht das). `xz -9` komprimiert auf ~580–650 MB. Download-Erfahrung für Eltern: akzeptabel, 2–5 min Download je nach Verbindung.

### 5.3 Alternative: nur 64-bit, Pi Zero W per Bastler-Script

Überlegenswert, wenn Pi Zero W Live-Tests zeigen, dass nicht-technische Eltern ihn eh nicht kaufen. Aus [`project_hardware_status.md`](../../) wissen wir aber: Zero W ist Teil der Beta-Live-Test-Matrix. Also **armhf-Variante mitliefern**.

## 6. Update-Kompatibilität

### 6.1 Problem-Analyse

`system_service.apply_update` macht (Auszug aus [`system_service.py:244-400`](../../core/services/system_service.py)):

```python
await self._git("fetch", "--quiet")
await self._git("reset", "--hard", "HEAD")
await self._git("clean", "-fd", "web/build/")
await self._git("pull", "--ff-only")
```

Das **braucht** zwingend ein funktionales `.git/`-Verzeichnis in `/opt/tonado`. Ein Image, das per `tar` ausgeliefert würde, hätte keins → Update-Feature in der App kaputt.

### 6.2 Entscheidung: `git clone` im Image

Das Image enthält `.git/` (siehe [2.4](#24-python-dependencies-im-image)). Wir sparen kein nennenswertes Platz, indem wir das weglassen würden (~50 MB Git-Objekte für ein junges Repo) — und gewinnen volle Kompatibilität zum heutigen Update-Mechanismus.

**Zusätzliche Härtung für Image-Installationen:**

- `firstrun.service` ruft `git config --global --add safe.directory /opt/tonado` auf. Bei Image-Owner-Mismatch zwischen pi-gen-Chroot und Pi-Laufzeit kann Git sonst `fatal: detected dubious ownership` werfen.
- `firstrun.service` ruft `git config user.email "tonado@localhost"` + `user.name "Tonado"` — nicht, weil wir committen, sondern weil manche Git-Operationen ohne Identity meckern.

### 6.3 Übergang zu GitHub-Releases-API (Prio 2.5 in BACKLOG)

Wenn wir später (Post-Beta) von `git pull` auf Download+Extract von GitHub Releases umstellen, brauchen wir `.git/` **nicht** mehr. Image-Größe sinkt um ~50 MB. Das ist aber ein **separater Arbeitsschritt** nach der Image-Welle, nicht deren Voraussetzung.

## 7. Sicherheit im Image

### 7.1 Was NICHT im Image sein darf

| Item | Grund | Wo generiert |
|------|-------|-------------|
| SSH-Host-Keys | Sonst teilen alle Tonado-Pis weltweit dieselben Keys → MITM trivial | `firstrun.sh` via `ssh-keygen -A` (nachdem alte keys gelöscht) |
| Default-User-Passwort | Pi OS Lite hatte früher `pi/raspberry` — Bookworm erzwingt Imager-Setup. Im Image: **kein Passwort für `pi`**, SSH per Key-Only oder vom Imager gesetzt | Imager setzt Passwort beim Flashen (Pi OS Imager Advanced Options) |
| Setup-AP-PSK | Wenn alle Image-Boxen dasselbe WLAN-PSK haben, kann Nachbar sich einloggen und Wizard hijacken | `firstrun.sh` generiert 16-Zeichen-PSK pro Gerät |
| Tonado-PIN | Experten-PIN muss vom User gesetzt werden | Setup-Wizard, nicht Image |
| JWT-Secret | Sonst kann jeder mit Image-JWT alle Boxen angreifen | `firstrun.sh` generiert zufälliges 32-Byte-Secret in `/opt/tonado/config/jwt_secret` |

### 7.2 Setup-WLAN-Passwort: pro Gerät generiert

**Entscheidung:** Pro-Gerät-PSK, 16 Zeichen Base32 (~80 Bit Entropie). Nicht identisch.

**Wo sieht der User das PSK?** Drei Optionen (Product-Owner-Frage Q2 unten):

A. **Auf der Rückseite des Pi-Gehäuses** — setzt voraus, dass wir Gehäuse mitliefern (tun wir nicht, open-source).
B. **Als Aufkleber auf der SD-Karte / Papier in der Box** — nur bei kommerziellen Komplettpaketen. Für Download-Image nicht möglich.
C. **Open SSID (PSK-frei) für die Setup-Phase.** Der User verbindet sich ohne Passwort, der Wizard ist nur über Captive-Portal erreichbar, Wizard erzwingt direkt im ersten Schritt das Setzen des Experten-PIN. Danach `.setup-complete` → AP aus.

**Empfehlung: Option C.** Begründung: In den 2–5 Minuten, die der AP aktiv ist, ist das Security-Fenster minimal; das Wizard-Interface ist ohnehin an den lokalen Link gebunden (RFC 1918, kein Internet-Zugang durch den AP); der UX-Gewinn („Handy findet WLAN, tippen, rein, fertig") ist massiv. Wenn ein Angreifer im WLAN-Radius sitzt, kann er den Wizard parallel öffnen — aber das Wizard-Erste-Feld ist „setze deinen Experten-PIN" und ab dann ist die Box gelockt. Ein Angreifer müsste genau zwischen AP-Up und User-Setup den Wizard beenden und PIN übernehmen — schmaler Angriffsvektor, dafür UX-Gewinn für 100% der Fälle.

### 7.3 Secrets-Generierung im `firstrun.sh`

Skizze (nicht final, zur Illustration):

```bash
#!/bin/bash
set -euo pipefail
FIRSTRUN_MARKER=/var/lib/tonado/firstrun.done
[ -f "$FIRSTRUN_MARKER" ] && exit 0

# SSH-Host-Keys
rm -f /etc/ssh/ssh_host_*
ssh-keygen -A

# JWT-Secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))" \
    > /opt/tonado/config/jwt_secret
chown pi:pi /opt/tonado/config/jwt_secret
chmod 600 /opt/tonado/config/jwt_secret

# Git-Trust
git config --global --add safe.directory /opt/tonado
git config --global user.email "tonado@localhost"
git config --global user.name "Tonado"

# Marker
mkdir -p "$(dirname "$FIRSTRUN_MARKER")"
date -Iseconds > "$FIRSTRUN_MARKER"
```

### 7.4 SSH im Image

**SSH-Server aktiv, kein Default-Passwort, Key-Login oder Imager-Passwort nötig.** Begründung: Bastler brauchen SSH für Debug; nicht-technische Eltern kommen nie auf die Idee, einen SSH-Client zu öffnen. Die Angriffsfläche ist klein, solange wir kein Default-Passwort liefern.

Pi OS Imager Advanced Options zwingen den User, **entweder** Passwort **oder** SSH-Key zu setzen — das kommt uns zugute.

## 8. Rollout-Plan

### 8.1 Reihenfolge

1. **Interne Tests auf 3 Pi-Modellen**, je 1 Tag Burn-In:
   - Pi Zero W (armhf) — schlechtester Fall, 512 MB RAM
   - Pi 3B+ (arm64) — Standard
   - Pi 4 oder Pi 5 (arm64) — wenn Hardware verfügbar (laut BACKLOG noch nicht zwingend für `v0.4.0-beta`)
2. **Freundes-Test** — ein nicht-technisches Eltern-Paar bekommt Image + Imager-Anleitung, wir sitzen daneben (nicht dazwischen), messen Time-to-First-Song.
3. **Release:** GitHub-Release mit beiden `.img.xz`-Varianten + `SHA256SUMS.txt` + detached GPG-Signatur (wenn wir die Signing-Infrastruktur zur Welle „F3 Release-Signatur" aufgebaut haben).
4. **Doku-Rollout** parallel (siehe 8.3).

### 8.2 SHA256 + Signatur

Release-Body-Template (für `gh release create`):

```markdown
## Tonado v0.4.0-beta

### Download

| Hardware | Datei | Größe | SHA256 |
|----------|-------|-------|--------|
| Pi Zero W | `tonado-0.4.0-beta-armhf.img.xz` | 580 MB | `abc123…` |
| Pi 3B+/4/5/Zero 2 | `tonado-0.4.0-beta-arm64.img.xz` | 620 MB | `def456…` |

### Flashen

Siehe [Anleitung für Eltern](https://github.com/t13gazh/tonado/blob/main/docs/fuer-eltern/flashen.md).

### Verifikation

```bash
sha256sum -c SHA256SUMS.txt
```
```

### 8.3 Neue Doku-Dateien

Diese Files sind **neu zu schreiben**, nicht Teil dieses Architektur-Dokuments:

| Datei | Zielgruppe | Inhalt |
|-------|-----------|--------|
| `docs/fuer-eltern/flashen.md` | Eltern, nicht-technisch | 3-Schritte-Anleitung mit Imager-Screenshots: 1) Imager öffnen, 2) Tonado-Image wählen, 3) SD-Karte flashen, 4) Pi einstecken |
| `docs/fuer-entwickler/image-build.md` | Maintainer | pi-gen-Setup, CI-Workflow, Signatur-Prozess |

`install-strategy.md` → **aktualisieren** auf den Stand „Image ist jetzt Default, SSH-Pfad ist Fallback für Bastler".

### 8.4 CI-Integration (später, nicht Welle-1-Scope)

pi-gen baut in QEMU — das läuft **nicht** auf GitHub Actions Standard-Runner (arm64-Emulation ist erlaubt, aber langsam, ~30–60 min pro Image). Optionen:

- GitHub Actions mit `qemu-user-static`, arm64-Runner (wenn Org-Plan vorhanden)
- Self-hosted Runner auf einem schnellen x86-Build-Host
- Manueller Build-Host beim Maintainer, Release-Script pusht die Images

**Für Welle 1 (erste Image-Release):** manueller Build auf Entwickler-Maschine, SHA256 + Release manuell. CI kommt mit einer späteren Welle.

## 9. Offene Product-Owner-Fragen

Vor der Impl-Welle zu beantworten (Ja/Nein oder A/B/C):

**Q1 — Varianten-Strategie:** Liefern wir **beide** Varianten (arm64 + armhf) aus, oder verlegen wir Pi Zero W auf den Bastler-Pfad (`curl | sudo bash`)?
- A) Beide Varianten (empfohlen, BACKLOG-Beta-Matrix verlangt Zero-W-Support)
- B) Nur arm64, Zero W bleibt Bastler-Pfad

**Q2 — Setup-WLAN-PSK:** Wie kommt das PSK zum User?
- A) Offenes Setup-WLAN, Wizard erzwingt Experten-PIN im ersten Schritt (empfohlen, beste UX)
- B) Pro-Gerät-PSK, user muss `ssh pi@tonado.local && cat /opt/tonado/config/setup-ap.psk` (widerspricht Vision)
- C) Identisches PSK für alle Images, dokumentiert in `flashen.md` (einfach, aber bei Nachbar-Tonado-Box trivial angreifbar)

**Q3 — Default-SSH im Image:** SSH aktiv lassen?
- A) Ja, aktiv. Pi Imager zwingt eh User zu Passwort/Key (empfohlen, Bastler-Kompat)
- B) Nein, nur per Wizard aktivierbar. Erhöht Aufwand für alle Debug-Pfade.

**Q4 — Wann wird `.setup-complete` gesetzt?**
- A) Nach erfolgreichem WLAN-Join (minimal, Rest des Wizards läuft über Heim-WLAN)
- B) Nach komplettem Wizard-Abschluss inkl. Audio/Figuren (empfohlen, klarer „fertig"-Zustand)

**Q5 — Reset-Flow bei WLAN-Verlust:** Wie kommt der User zurück in den Setup-AP, wenn das Heim-WLAN stirbt?
- A) Separater Reset-Knopf (Hardware) löscht `.setup-complete` — eigene Welle, Post-Beta
- B) Via SSH + `rm /opt/tonado/config/.setup-complete` — Bastler-OK, Eltern-unmöglich
- C) Wizard hat „WLAN vergessen"-Button, der die Box in AP-Modus zurücksetzt — braucht physischen Zugang nicht, aber nur solange App noch erreichbar ist
- Dieser Punkt ist **nicht blockierend** für die Image-Welle, aber sollte parallel geklärt werden

**Q6 — Image-Release-Signatur:** Sofort mit GPG-Signing-Infrastruktur aufsetzen oder Welle-2?
- A) Nur SHA256 für Welle 1, Signatur in Welle 2 (Finding F3 aus Security-Audit, sowieso geplant)
- B) Sofort GPG-Signatur (verzögert Welle 1 um Aufbau der Key-Infrastruktur)

**Q7 — Vorinstallierte Figuren/Demo-Content:** Kommt das Image mit Beispiel-Songs/-Radiosendern, damit der Pi nach dem Flashen **direkt** Musik spielen kann, oder ist die Media-Library leer?
- A) Leer, User lädt eigene Inhalte hoch (empfohlen, Vision-konform — „dir gehört")
- B) Mit 2–3 CC0-Beispielsongs + 5 kuratierten Kinder-Radiosendern (einladender, aber ggf. lizenz-fragil)
