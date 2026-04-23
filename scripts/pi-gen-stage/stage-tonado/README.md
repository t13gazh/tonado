# Tonado pi-gen Stage

Dieser Ordner enthaelt die pi-gen Stage `stage-tonado`, die nach `stage2` (Pi OS
Lite Bookworm) ausgefuehrt wird und ein flashbares Tonado-Image erzeugt.
Architektur-Referenz: [`docs/fuer-entwickler/pi-image-architecture.md`](../../../docs/fuer-entwickler/pi-image-architecture.md).

> Zielgruppe dieser README: Maintainer, die lokal ein Image bauen wollen. Eltern
> sehen nur das fertige `.img.xz` auf der GitHub-Releases-Seite.

## Voraussetzungen

- Ubuntu 24.04 LTS **oder** WSL2 mit Ubuntu 24.04
- Docker Engine (`sudo apt install docker.io && sudo usermod -aG docker $USER`, danach neu einloggen)
- `git`, `xz-utils`, `coreutils`
- ~10 GB freier Plattenplatz
- Die erwartete Build-Zeit liegt bei ca. **35 min** pro Variante

## Setup

```bash
# Neben dem Tonado-Checkout auschecken (damit die Stage hineingeklont werden kann)
cd ~/Repos
git clone https://github.com/RPi-Distro/pi-gen.git
cd pi-gen

# WICHTIG: pi-gen auf einen konkreten Commit-SHA pinnen, nicht auf den Branch.
# Branch-HEADs koennen jederzeit aendern -- das bricht die Reproduzierbarkeit
# unserer Image-Builds. Fuer die armhf-Variante (Pi Zero W) entsprechend den
# master-HEAD pinnen.
#
# Aktueller arm64-HEAD (Stand 2026-04-23):
git checkout 4ad56cc850fa60adcc7f07dc15879bc95cc1d281
# Refresh vor jedem Release-Build:
#   git fetch origin && git ls-remote https://github.com/RPi-Distro/pi-gen arm64
# Dann den README-Eintrag hier aktualisieren und committen.

# Tonado-Stage in pi-gen reinkopieren
cp -r ~/Repos/tonado/scripts/pi-gen-stage/stage-tonado ./stage-tonado
```

> Warum gepinnt? pi-gen zieht Debian-Pakete und Scripte aus seinem Tree. Ein
> ungepinnter Branch-Checkout bedeutet: heute gebautes Image != morgen gebautes
> Image, selbst bei gleichem Tonado-Tag. Supply-Chain-Risiko F6 aus dem
> Security-Review. Vor dem v0.4.0-beta-Release sollte dieses Pinning zusaetzlich
> in einen GitHub-Actions-Workflow wandern (actions/checkout@<sha> +
> pi-gen checkout <sha>).

## Konfiguration

Im pi-gen-Root eine Datei `config` anlegen (wird von `build-docker.sh` gelesen):

```bash
# ~/Repos/pi-gen/config
IMG_NAME='tonado-0.3.1-beta-arm64'
RELEASE='bookworm'
STAGE_LIST="stage0 stage1 stage2 stage-tonado"
TARGET_HOSTNAME='tonado'
ENABLE_SSH=1

# Tonado-spezifisch: Git-Tag, der im Image ausgecheckt wird.
# Reproduzierbarkeit: immer ein Tag, niemals 'main'.
TONADO_VERSION='v0.3.1-beta'

# Commit-SHA-Pin fuer Supply-Chain-Integritaet (Security-Review F7).
# Ermittlung:
#   git -C ~/Repos/tonado rev-parse v0.3.1-beta
# Solange Release-Tags nicht GPG-signiert sind, ist dieser Pin die einzige
# Absicherung gegen ein nachtraeglich force-gepushtes Tag. Wenn leer gelassen,
# laeuft der Build mit Warning durch (Uebergangszeit).
TONADO_EXPECTED_SHA='7659797988...'   # volle 40-Zeichen-SHA eintragen

# Optional: eigenen Repo-Fork verwenden.
# TONADO_REPO='https://github.com/deinuser/tonado.git'

# Optional: user-Angaben unterdruecken, damit der Pi Imager sie erzwingt.
# (Kein Default-Passwort im Image.)
DISABLE_FIRST_BOOT_USER_RENAME=0
```

Fuer die 32-bit-Variante (Pi Zero W Original): `IMG_NAME='tonado-0.3.1-beta-armhf'`
und `ARCH=armhf` ergaenzen. Details siehe pi-gen-README.

## Build

```bash
cd ~/Repos/pi-gen
./build-docker.sh
```

Ergebnis:

```
~/Repos/pi-gen/deploy/
├── tonado-0.3.1-beta-arm64.img.xz          # Flashbar (z.B. mit Raspberry Pi Imager)
├── tonado-0.3.1-beta-arm64.info            # Paketliste des Builds
└── tonado-0.3.1-beta-arm64.img.sha256      # Wird NICHT von pi-gen erzeugt -- manuell per 'sha256sum > ...'
```

## Nach dem Build

1. SHA256 erzeugen:
   ```bash
   cd deploy && sha256sum tonado-*.img.xz > SHA256SUMS.txt
   ```
2. Auf Pi Zero W (armhf) UND Pi 3B+ (arm64) flashen, First-Boot testen.
3. Release-Workflow (manuell, Welle-1): GitHub Release anlegen, beide `.img.xz`
   plus `SHA256SUMS.txt` anhaengen.

## Stage-Layout

```
stage-tonado/
├── prerun.sh                           # Copy rootfs from stage2
├── EXPORT_IMAGE                        # IMG_NAME + IMG_SUFFIX fuer pi-gen
├── 00-packages                         # apt Runtime + Build-Deps
├── 01-sys-tweaks/
│   ├── 00-run.sh                       # config.txt append, enable distro-units
│   └── files/
│       ├── etc/NetworkManager/conf.d/99-tonado-wlan0-unmanaged.conf
│       └── boot/firmware/config.txt.append
├── 02-tonado-code/
│   └── 00-run-chroot.sh                # git clone + SHA-Pin + pip install
├── 03-tonado-finalize/
│   └── 00-run.sh                       # apt purge, chown, unit symlinks+enable
└── README.md                           # diese Datei

# Systemd-Unit-Files sind NICHT im Stage-Tree. Sie leben im Tonado-Repo unter
# /opt/tonado/system/*.service und werden in Stage 03 nach /etc/systemd/system
# symlinkt. Single source of truth = Tonado-Repo.
```

## Troubleshooting

- **`fatal: could not read from remote`** im Chroot: Docker-Host braucht
  Internet. `docker run --rm -it busybox ping -c1 github.com` zuerst testen.
- **`qemu: uncaught target signal 11`** auf ARM-Chroot: veraltetes
  `qemu-user-static`. `sudo apt install --reinstall qemu-user-static`.
- **Build bricht in `02-tonado-code`**: meistens eine fehlende Systemabhaengigkeit
  fuer `pip install -e ".[pi]"`. Logs in `work/<IMG_NAME>/stage-tonado/`
  pruefen. Fix gehoert ggf. in `00-packages`.
- **`web/build/index.html missing`**: Der auscheckte Tag hat kein committetes
  Frontend-Build. Im Repo: `cd web && npm install && npm run build`, committen,
  Tag neu setzen (force-push des Tags waere destruktiv -- lieber neuen Tag).
