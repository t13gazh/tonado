# Pi-Image-Architektur

> **Status:** Umgesetzt für `v0.4.0-beta`. Die ursprüngliche Entwurfs-Fassung (Abschnitte 1–8) ist als Begründungs-Historie erhalten; wo sich die reale Umsetzung davon unterscheidet, gilt der **Abschnitt „Stand der Umsetzung"** direkt unten — er ist die maßgebliche Quelle.
>
> **Vorarbeit:** [`install-strategy.md`](install-strategy.md) beschreibt die UX-Lücke zwischen SSH-Installation (Alpha) und flashbarem Image (Beta-Ziel).

## Stand der Umsetzung (v0.4.0-beta, maßgeblich)

Die Boot-Fix-Welle vom 2026-06-10/11 hat das Image vom „bootet headless nicht" zum funktionsfähigen Setup-Pfad gebracht. Wo die Entwurfs-Abschnitte unten abweichen, gilt das hier.

### Access-Point-Architektur — eine Quelle für `wlan0`

Es gibt **genau einen** privilegierten AP-Mechanismus: [`system/setup-ap.sh`](../../system/setup-ap.sh). Früher konkurrierten zwei Implementierungen (das Bash-Skript **und** ein zweiter, privilegierter Pfad im Python-`CaptivePortalService`) um `wlan0` und kollidierten beim Boot. Jetzt:

| AP-Typ | Wann | Wer startet | Sicherheit | SSID |
|--------|------|-------------|------------|------|
| **Setup-AP** | Erst-Boot, bis `.setup-complete` | systemd: `tonado-ap.service` → `setup-ap.sh start open` | **OFFEN** (Eltern haben noch keine Zugangsdaten — Henne-Ei) | `Tonado-Setup` |
| **Recovery-AP** | Laufzeit, wenn das bekannte WLAN wegfällt | `ConnectivityMonitor` → `CaptivePortalService` → `sudo -n setup-ap.sh start secured …` | **WPA2** (Eltern kennen die Creds aus dem Wizard) | konfigurierbar (Default `Tonado`) |

- `setup-ap.sh` CLI: `start open [ssid]` | `start secured <ssid> <psk>` | `stop`. Setzt `country_code=DE` in der hostapd-Config, schreibt Configs nach `/run/tonado/` (tmpfs, SD-schonend), und setzt `wlan0` **dynamisch** unmanaged (`nmcli device set wlan0 managed no` beim Start, `… yes` beim Stop) — es gibt **keine** statische NetworkManager-Unmanaged-Drop-in-Datei mehr (die war ein Henne-Ei-Deadlock).
- `CaptivePortalService` (läuft als unprivilegierter `pi`-User) hält nur noch die State-Machine (Owner/Timeout/Credentials) und delegiert jede `wlan0`-Operation per `sudo -n setup-ap.sh` — kein privilegierter Netzwerk-Code mehr im App-Prozess. Die passenden NOPASSWD-Grants stehen in [`system/sudoers.d/tonado`](../../system/sudoers.d/tonado).
- Recovery-Zugangsdaten (`captive_portal.ap_ssid` / `captive_portal.ap_password`) setzen die Eltern im Wizard-Schritt „Notfall-WLAN" (vorausgefüllt, editierbar).
- Teardown nach Setup: `wifi_service.finalize_setup_ap_teardown` stoppt+disabled `tonado-ap.service`; dessen `ExecStop` (`setup-ap.sh stop`) gibt `wlan0` an NetworkManager zurück.
- **Boot-Entscheidung Setup-AP vs. Heim-WLAN:** `imager-wifi-probe.service` läuft `Before=tonado-ap.service`, pollt bis zu 30 s, ob bereits ein Heim-WLAN trägt (z.B. vom Imager geseedet), und schreibt ggf. `/run/tonado/home-wifi-active`. `tonado-ap.service` trägt `ConditionPathExists=!/run/tonado/home-wifi-active` (zusätzlich zu `!/opt/tonado/config/.setup-complete`) — ein bereits verbundenes Heim-WLAN unterdrückt also den Setup-AP. Bewusst ohne `network-online.target` (das würde bei rfkill-Sperre den Boot ~90-110 s stallen).

### Reale Stage-Struktur (`scripts/pi-gen-stage/stage-tonado/`)

Die Config-Schritte werden zur **Bake-Time im Stage-Skript geschrieben**, nicht über `files/` abgelegt — pi-gen kopiert `files/` nicht automatisch (nur `config.txt.append` wird in `01-sys-tweaks` explizit ins ROOTFS kopiert).

| Substage | Inhalt |
|----------|--------|
| `01-sys-tweaks/` | Distro-Units enablen (mpd, nginx, avahi); `config.txt.append` explizit kopieren (SPI, I2C, OnOff-SHIM) |
| `02-tonado-code/00-run.sh` | im Chroot: `git clone` + `pip install .[pi]` (Frontend ist als `web/build/` im Repo committed — kein npm im Image) |
| `03-tonado-config/00-run.sh` | **alle netzwerkfreien `install.sh`-Schritte:** nginx-Site (+ Captive-Portal-Auto-Open-Antworten für Android/iOS/Windows, Default-Site entfernt), `mpd.conf`, sudoers-Drop-in (visudo-validiert), `i2c-dev`-modules-load, WLAN-Land `DE`, journald-Limit 30 MB, `dnsmasq.service`+`hostapd.service` **maskiert** (sonst :53-Konflikt mit der eigenen Portal-Instanz), Bluetooth/triggerhappy/ModemManager disabled, `ipv6.disable=1` (einzeilig), `machine-id`+SSH-Host-Keys geleert |
| `04-tonado-finalize/00-run.sh` | Build-Deps purgen, `chown pi:pi`, Repo-Units symlinken+enablen, Hardware-Gruppen, Install-Marker |

### Was `firstrun.sh` beim Erst-Boot wirklich tut

Einmalig, Marker-gated: SSH-Host-Keys regenerieren (Image liefert leere `/etc/ssh`), **WLAN-Funk entsperren** (`rfkill unblock wifi` + `iw reg set DE`, vor dem AP-Start), Git-Trust für den `pi`-User einrichten. **Kein** JWT-Secret und **kein** Setup-AP-PSK — der Setup-AP ist offen, und das JWT-Secret erzeugt der `AuthService` selbst pro Gerät in der SQLite-DB (deshalb darf die DB nicht ins Image gebacken werden; ein blockierender CI-Schritt `scripts/ci/assert-no-baked-db.sh` erzwingt das).

### Build & Verifikation
[`.github/workflows/pi-image.yml`](../../.github/workflows/pi-image.yml) setzt `DISABLE_FIRST_BOOT_USER_RENAME=1` (sonst headless-Konsolen-Hang), `chmod +x` auf alle Stage- und `system/`-Skripte (Windows-Checkout verliert das Bit), und ruft den DB-Guard. [`scripts/ci/qemu-smoke.sh`](../../scripts/ci/qemu-smoke.sh) prüft die Bake-Outputs offline (nginx-Site, sudoers, i2c-dev, cmdline einzeilig, dnsmasq maskiert, machine-id leer).

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
| 3 | SD-Karte rein, Strom an | 30–60 s | First-Boot-Expand, `firstrun.service` (SSH-Keys, rfkill-Unblock, Git-Trust), `tonado-ap.service` startet den **offenen** Setup-AP |
| 4 | Handy → WLAN „Tonado-Setup" verbinden (**offen, kein Passwort** — siehe „Stand der Umsetzung") | 30 s | Captive-Portal-Redirect öffnet Setup-Wizard im Browser (`http://192.168.4.1`) |
| 5 | Wizard durchklicken (Heim-WLAN, Audio-Output, Eltern-PIN, Notfall-WLAN, ggf. Figuren) | 3–5 min | Setup-Wizard, am Ende `touch /opt/tonado/config/.setup-complete` |
| 6 | Pi wechselt ins Heim-WLAN, Handy mit Heim-WLAN verbinden, Box via `tonado.local` erreichen | 30 s | `tonado-ap.service` überspringt sich wegen `ConditionPathExists=!` |

**Was im Image vorbereitet ist (Bake-Time):**
- Komplettes `/opt/tonado/` inkl. Git-History, `.venv` und `web/build/`
- Alle Debian-Pakete: `python3`, `mpd`, `nginx`, `hostapd`, `dnsmasq`, `network-manager`, `avahi-daemon`, …
- Python-Dependencies vorinstalliert (`.venv` im Image — siehe 2.3)
- Systemd-Units aktiviert: `mpd`, `nginx`, `tonado`, `tonado-ap`, `firstrun`
- Nginx-Config, MPD-Config, sudoers.d-Drop-In
- `/boot/firmware/config.txt` bereits mit `dtparam=spi=on`, `dtparam=i2c_arm=on`, gpio-shutdown/poweroff (OnOff-SHIM), ohne HifiBerry-Overlay (wird im Wizard gesetzt)

**Was beim First Boot passiert (`firstrun.service`, einmalig):** *(maßgeblich: „Stand der Umsetzung" oben)*
- SSH-Host-Keys rotieren, WLAN-Funk entsperren (`rfkill unblock` + `iw reg set DE`), Git-Trust setzen
- `/etc/machine-id` wird vom Image leer ausgeliefert → systemd regeneriert eine eindeutige pro Gerät
- Dateisystem auf SD-Karten-Größe expandieren (von Pi OS Lite übernommen)
- Self-Disable via Marker-Datei
- **Kein** Setup-AP-PSK (der Setup-AP ist offen) und **kein** JWT-Secret-File (der `AuthService` erzeugt es pro Gerät in der DB)

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
│   └── 00-run.sh                # läuft IM Chroot: git clone, pip install
├── 03-tonado-config/
│   └── 00-run.sh                # Config aus install.sh portiert: nginx-Site,
│                                # mpd.conf, sudoers, i2c-dev, WLAN-Land DE,
│                                # journald-Limit, ipv6-disable
└── 04-tonado-finalize/
    └── 00-run.sh                # Permissions, Marker-Dateien, cleanup
```

> Hinweis: Die Config-Dateien (nginx-Site, mpd.conf, sudoers …) werden in
> `03-tonado-config/00-run.sh` zur Bake-Time **geschrieben**, nicht über `files/`
> abgelegt — pi-gen kopiert `files/` nicht automatisch (nur `config.txt.append`
> wird in `01-sys-tweaks` explizit ins ROOTFS kopiert). Diese Architektur-Doku
> wird in WP6 vollständig auf den aktuellen Stand (AP-Konsolidierung) gebracht.

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
rfkill iw wireless-tools   # WLAN-Funk entsperren + Imager-Probe (iwgetid)
git
# Build (für pip install, wird am Ende von 04-tonado-finalize wieder purged)
python3-dev build-essential libffi-dev
```

**Begründung `network-manager`:** Pi OS Lite Bookworm nutzt per Default NetworkManager. Wir brauchen ihn für `nmcli` im Wizard (WLAN-Credentials persistent speichern).

**Nicht im Image (Ressourcen-Ersparnis):**
- ~~`nodejs` / `npm`~~ — Frontend wird **im Build-Container** gebaut, nicht auf dem Pi. Entspricht `feedback_cross_compile.md`.
- ~~`curl`/`wget` zum Laufzeit-Download~~ — alles liegt schon im Image.
- ~~Python-Compile-Toolchain zur Laufzeit~~ — nur zur Bake-Time, dann `apt-get purge`.

### 2.4 Python-Dependencies im Image

Im Chroot-Script `02-tonado-code/00-run.sh` (ein `00-run.sh`, das intern `on_chroot` nutzt — pi-gen behandelt `run.sh` und `run-chroot.sh` unterschiedlich; wir verwenden durchgängig `00-run.sh` mit explizitem `on_chroot`):

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

`04-tonado-finalize/00-run.sh` (läuft zur Bake-Time außerhalb vom Chroot):

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

**Maßgeblich ist „Stand der Umsetzung" oben.** Das reale `system/firstrun.sh` generiert **kein** Setup-AP-PSK (der Setup-AP ist offen) und rendert kein hostapd-Template — das macht `setup-ap.sh` zur Laufzeit. Es macht:
- SSH-Host-Keys regenerieren (im Image sind sie leer, siehe 7)
- WLAN-Funk entsperren (`rfkill unblock wifi` + `iw reg set DE`) vor dem AP-Start
- Git-Trust für den `pi`-User setzen
- Marker `/var/lib/tonado/firstrun.done` schreiben

### 4.3 Flag-Datei `.setup-complete`

Die Logik (`ConditionPathExists=!/opt/tonado/config/.setup-complete`) bleibt. Sie wird vom Setup-Wizard am Ende angelegt. Wichtig:

- **Bei späterem WLAN-Verlust** spannt der `ConnectivityMonitor` nach einer Karenzzeit **automatisch** den Recovery-AP auf (WPA2, Creds aus dem Wizard) — anders als hier ursprünglich geplant. Das ist die „WLAN-Rettung": die Box wird unterwegs (Oma, Auto) wieder erreichbar, ohne physischen Knopf. Schutz gegen Ping-Pong bei kurzen Aussetzern: Boot-Grace, Double-Check, Circuit-Breaker (siehe [`core/services/connectivity_monitor.py`](../../core/services/connectivity_monitor.py)). Ein physischer Reset-Knopf bleibt als zusätzlicher Fallback im Backlog.
- **Bei Image-Reflash:** Neue SD-Karte hat kein `.setup-complete` → Setup-AP wieder aktiv. Korrekt.

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
| Default-User-Passwort | Pi OS Lite hatte früher `pi/raspberry`. Im Image: **kein Passwort für `pi`** → Passwort-SSH-Login unmöglich (`PermitEmptyPasswords no`). Achtung: der Imager-Customization-Dialog erscheint **nicht** bei eigenem `.img.xz`, erzwingt also nichts | Eltern brauchen kein Login (Setup-AP). Bastler: `userconf.txt` manuell auf bootfs (siehe 7.4) |
| Setup-AP-PSK | — | **Entfällt: der Setup-AP ist offen** (Option C, siehe 7.2). Der *Recovery-*AP ist WPA2; seine Creds setzen die Eltern im Wizard |
| Tonado-PIN | Experten-/Eltern-PIN muss vom User gesetzt werden (Setup ist ohne PIN nicht abschließbar) | Setup-Wizard, nicht Image |
| JWT-Secret | Sonst kann jeder mit Image-JWT alle Boxen angreifen | **`AuthService` erzeugt es pro Gerät in der SQLite-DB** beim ersten Start (kein File); CI-Guard verhindert eine gebackene DB |

### 7.2 Setup-WLAN: offen (Option C umgesetzt)

**Umgesetzt: Option C — offener Setup-AP.** Der User verbindet sich ohne Passwort mit `Tonado-Setup`, der Wizard ist nur über das Captive-Portal erreichbar (RFC-1918-Link, kein Internet-Zugang durch den AP). Der Wizard ist **nicht abschließbar, ohne dass eine Eltern-PIN gesetzt wurde** (`setup_wizard.complete_setup` wirft sonst) — danach `.setup-complete` → Setup-AP aus.

Begründung: In dem Fenster, in dem der offene AP aktiv ist, ist das Security-Fenster klein; der UX-Gewinn („Handy findet WLAN, tippen, rein, fertig") ist massiv. Ein Angreifer im Funkradius könnte den Wizard parallel öffnen — aber Heim-WLAN-Bruteforce ist via `PROBE_FAIL_LOCKOUT` gedeckelt, und ohne gesetzte Eltern-PIN bleibt das Setup offen statt „fertig". Der **Recovery-**AP (nach Setup) ist dagegen WPA2, weil die Box dann unterwegs sein kann und die Eltern die Creds kennen. Bekannte Resthärtung (offener Setup-AP ohne Zeit-Timeout) steht im [`BACKLOG.md`](../../BACKLOG.md).

### 7.3 Secrets-Generierung im `firstrun.sh`

Maßgeblich ist [`system/firstrun.sh`](../../system/firstrun.sh) selbst. Kern: SSH-Host-Keys rotieren, WLAN-Funk entsperren + Land setzen, Git-Trust. **Kein** JWT-Secret-File und **kein** AP-PSK (siehe „Stand der Umsetzung" oben). Das JWT-Secret erzeugt der `AuthService` pro Gerät in der DB.

### 7.4 SSH im Image

**SSH-Server aktiv, aber kein Default-Passwort.** Begründung: Bastler brauchen SSH für Debug; nicht-technische Eltern kommen nie auf die Idee, einen SSH-Client zu öffnen. Die Angriffsfläche ist klein, solange wir kein Default-Passwort liefern.

**Wichtig — der Imager hilft hier NICHT:** Der OS-Customization-Dialog (User/Passwort/SSH-Key/WLAN) erscheint im Raspberry Pi Imager nur bei den offiziellen Pi-OS-Images, die er aus seiner Liste kennt — **nicht** bei einem eigenen `.img.xz` über „Use custom". Es wird also weder ein Passwort noch ein SSH-Key gesetzt. Folge: Der `pi`-User bleibt passwortlos und ein Passwort-SSH-Login ist mangels Passwort unmöglich (`sshd` lehnt leere Passwörter ab). Das ist sicherheitstechnisch eher gut.

Konsequenzen je Zielgruppe:
- **Eltern:** brauchen nie SSH. Zugang ausschliesslich über den Setup-AP + Wizard (Abschnitt 1), danach `http://tonado.local`.
- **Bastler/Entwickler:** wer SSH will, legt **nach dem Flashen** auf die `bootfs`-FAT-Partition (im Windows-Explorer/Finder sichtbar) eine `userconf.txt` mit `pi:<crypt-hash>` (Hash via `openssl passwd -6`) und/oder einen Public Key nach `/home/pi/.ssh/authorized_keys`. Mit `DISABLE_FIRST_BOOT_USER_RENAME=0` ist der Bookworm-`userconf`-Mechanismus im Image vorhanden und konsumiert die Datei beim ersten Boot. Beim Pi 3B+/4/5 ist LAN-Kabel der robusteste Headless-Zugang (kein WLAN-Raten nötig).

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

| Datei | Zielgruppe | Status |
|-------|-----------|--------|
| `docs/fuer-eltern/flashen.md` | Eltern, nicht-technisch | **Geschrieben** (Imager-Anleitung inkl. offenem Setup-WLAN + „kein Internet"-Hinweis) |
| `docs/fuer-entwickler/pi-image-ci.md` | Maintainer | **Vorhanden** (pi-gen-Setup, CI-Workflow, Signatur) |

`install-strategy.md` → noch **aktualisieren** auf den Stand „Image ist jetzt Default, SSH-Pfad ist Fallback für Bastler".

### 8.4 CI-Integration (später, nicht Welle-1-Scope)

pi-gen baut in QEMU — das läuft **nicht** auf GitHub Actions Standard-Runner (arm64-Emulation ist erlaubt, aber langsam, ~30–60 min pro Image). Optionen:

- GitHub Actions mit `qemu-user-static`, arm64-Runner (wenn Org-Plan vorhanden)
- Self-hosted Runner auf einem schnellen x86-Build-Host
- Manueller Build-Host beim Maintainer, Release-Script pusht die Images

**Für Welle 1 (erste Image-Release):** manueller Build auf Entwickler-Maschine, SHA256 + Release manuell. CI kommt mit einer späteren Welle.

## 9. Product-Owner-Fragen — entschieden

> Diese Fragen sind inzwischen alle beantwortet (Umsetzung in `v0.4.0-beta`): **Q1** beide Varianten (arm64 + armhf). **Q2** offenes Setup-WLAN (Option A). **Q3** SSH aktiv, `pi` passwortlos (Option A). **Q4** `.setup-complete` nach komplettem Wizard (Option B). **Q5** automatische WLAN-Rettung via `ConnectivityMonitor` (Recovery-AP) statt Hardware-Knopf; Knopf bleibt Backlog-Fallback. **Q6** SHA256 + cosign-keyless (Option A). Der ursprüngliche Fragenkatalog bleibt als Historie erhalten.

Ursprünglich vor der Impl-Welle zu beantworten (Ja/Nein oder A/B/C):

**Q1 — Varianten-Strategie:** Liefern wir **beide** Varianten (arm64 + armhf) aus, oder verlegen wir Pi Zero W auf den Bastler-Pfad (`curl | sudo bash`)?
- A) Beide Varianten (empfohlen, BACKLOG-Beta-Matrix verlangt Zero-W-Support)
- B) Nur arm64, Zero W bleibt Bastler-Pfad

**Q2 — Setup-WLAN-PSK:** Wie kommt das PSK zum User?
- A) Offenes Setup-WLAN, Wizard erzwingt Experten-PIN im ersten Schritt (empfohlen, beste UX)
- B) Pro-Gerät-PSK, user muss `ssh pi@tonado.local && cat /opt/tonado/config/setup-ap.psk` (widerspricht Vision)
- C) Identisches PSK für alle Images, dokumentiert in `flashen.md` (einfach, aber bei Nachbar-Tonado-Box trivial angreifbar)

**Q3 — Default-SSH im Image:** SSH aktiv lassen?
- A) Ja, aktiv. `pi` ist passwortlos → Login nur, wenn ein Bastler bewusst `userconf.txt`/Key auf bootfs legt; Eltern-Angriffsfläche bleibt null (empfohlen, Bastler-Kompat). **Korrektur:** Der Imager erzwingt **kein** Passwort/Key bei Custom-Images — siehe 7.4.
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
