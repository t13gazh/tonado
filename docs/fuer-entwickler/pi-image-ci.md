# Pi-Image CI/CD

Entwurf für die GitHub-Actions-Pipeline, die aus einem `v*`-Release-Tag ein fertiges Tonado-Pi-Image baut, signiert und als Release-Asset hochlädt. Ziel: Flash-first statt SSH-first (siehe [`install-strategy.md`](install-strategy.md)).

Status: **Entwurf / RFC**. Kein Workflow-YAML produktiv. `scripts/pi-gen-stage/` existiert noch nicht und wird als Teil der Umsetzungs-Welle erstellt.

---

## 1. Workflow-Trigger

Drei Trigger, jeweils mit unterschiedlichem Seiteneffekt:

| Trigger | Baut? | Lädt Release-Asset hoch? | Zweck |
|---------|-------|---------------------------|-------|
| `push` Tag `v*` (z. B. `v0.4.0-beta`) | ja | ja | Produktiver Release-Build |
| `workflow_dispatch` (manuell) | ja | optional (`inputs.upload=true`) | Testing, Hotfix-Rebuild ohne neuen Tag |
| `pull_request` gegen `main` mit Pfad-Filter auf `scripts/pi-gen-stage/**` oder `.github/workflows/pi-image.yml` | ja (Dry-Run, nur Zero-W-Variante) | nein | Regressionsschutz, wenn jemand an der Stage schraubt |

Begründung PR-Dry-Run: Image-Build ist teuer (Minuten/Bandbreite). Nur wenn die Stage oder der Workflow selbst geändert wird, lohnt ein PR-Build. Ergebnis wird nur als Artifact aufgehoben (7 Tage), nicht als Release.

```yaml
on:
  push:
    tags: ['v*']
  workflow_dispatch:
    inputs:
      upload:
        description: 'Upload to release?'
        type: boolean
        default: false
      ref:
        description: 'Branch/Tag (leer = aktueller)'
        type: string
        default: ''
  pull_request:
    branches: [main]
    paths:
      - 'scripts/pi-gen-stage/**'
      - '.github/workflows/pi-image.yml'
```

---

## 2. Workflow-Struktur

### Runner-Wahl: x86 + QEMU (empfohlen)

GitHub bietet seit Anfang 2025 öffentlich ARM64-Linux-Runner (`ubuntu-24.04-arm`), für **public repos kostenlos**. Klingt nach dem naturgemäßen Match — ist es aber nur halb. `pi-gen` nutzt standardmäßig `qemu-user-static` + `binfmt_misc`, um ein ARM-RootFS auf x86 zu bauen. Das funktioniert seit Jahren, ist gut dokumentiert, und die meisten Tonado-Contributor testen lokal auf x86-Laptops. **Vorteile x86 + QEMU:**

- Reproduzierbar mit lokalem Setup (jeder Contributor kann den Build zuhause nachstellen)
- Schnellere Runner-CPUs (ubuntu-latest = 4 vCPU, 16 GB RAM; ARM-Runner 2026 meist 2 vCPU, 8 GB)
- Debian apt-Mirrors sind für x86 sauberer gespiegelt, weniger Flake

**Nachteile:**

- QEMU-Emulation kostet ~30-50 % mehr Build-Zeit gegenüber nativem ARM
- Einzelne pi-gen-Stages (v. a. Rust-Tooling) sind in QEMU fehleranfällig — wir nutzen aber aktuell keins davon

**Empfehlung:** `ubuntu-24.04` x86 + QEMU/binfmt, später evaluieren ob `ubuntu-24.04-arm` Build-Zeit halbiert, wenn Hardware in 2026 aufgerüstet ist.

### Was macht pi-gen, was wir selbst

pi-gen läuft **im Docker-Mode** (`CONTINUE=0`, `USE_QCOW2=1`). Vorteile: saubere Trennung, deterministisch, kein Umweg über `debootstrap` als Runner-Privileg. Nachteil: Docker-in-Actions = der Runner muss privileged mounts erlauben, was `ubuntu-latest` nativ kann.

- **pi-gen übernimmt:** Stages 0-2 (base system, apt-Packages, user-space), Image-Zusammenbau (`.img` + `.img.xz`), Boot-Partition-Layout
- **Tonado-Stage (custom):** neue Stage `stage-tonado` nach Stage 2 — kopiert unser Release-Artefakt ins Image, installiert Python-Dependencies im First-Boot-Hook, registriert `tonado.service`, pre-konfiguriert MPD, hostapd, dnsmasq
- **First-Boot-Hook:** ein Script in `/etc/rc.local` oder systemd-`first-boot.service`, das beim ersten Start Captive-Portal-Netzwerk aufspannt und idempotent auf nachfolgenden Bootss no-op ist

### Build-Zeit-Schätzung

Basiert auf öffentlichen pi-gen-CI-Daten (`RPi-Distro/pi-gen` GitHub Actions):

| Komponente | Zeit (ubuntu-latest, QEMU) |
|------------|----------------------------|
| Stage 0 (minimal bootstrap) | ~5 min |
| Stage 1 (apt base) | ~8 min |
| Stage 2 (Desktop-loses Lite) | ~12 min |
| **Stage Tonado** (apt-packages + Repo-Kopie) | ~3-5 min |
| Image-Export (xz-Kompression) | ~8 min |
| **Gesamt pro Arch** | **35-40 min** |
| Matrix 2 Archs parallel | 35-40 min wall-clock |

Damit liegen wir weit unter dem 6h-Actions-Timeout und haben Puffer für Tests.

### Cache-Strategie

Drei Cache-Schichten, jede mit eigener Invalidation:

1. **apt-Cache** (via `actions/cache`, Pfad `pi-gen/work/*/aptcache`): Key = Hash aller `00-packages`-Dateien. Spart ~8 min beim Folge-Build mit identischer Package-Liste.
2. **Stage-0/1-Cache** (Pfad: `pi-gen/work/.*/stage1/rootfs`): Key = `${{ runner.os }}-pi-gen-stage1-${{ hashFiles('pi-gen-config') }}`. Invalidiert nur bei Basis-Config-Änderung. Spart weitere ~10 min.
3. **pip-Wheel-Cache** für unsere Python-Dependencies (aus `pyproject.toml`), damit First-Boot-Install schneller ist: pre-downloaded als offline-wheels ins Image, spart First-Boot-Internet-Dependency.

Wichtiger Punkt: **Stage-Cache nur gültig, solange pi-gen-Version (`pi-gen ref`) identisch ist** — wir pinnen auf einen festen Commit, nicht auf `master`.

---

## 3. Artefakt-Übergabe

### Wie `scripts/pi-gen-stage/` in den Build-Container kommt

Eigenes Stage-Verzeichnis im Tonado-Repo, Layout:

```
scripts/pi-gen-stage/
  stage-tonado/
    prerun.sh              # symlink target + apt-prereqs
    00-run.sh              # copy tonado release, install systemd units
    00-packages            # apt packages (nginx, mpd, python3-venv, ...)
    files/
      tonado.service       # systemd unit
      nginx.conf           # reverse proxy config
      first-boot.service   # first-boot orchestrator
      first-boot.sh        # actual first-boot work
    EXPORT_IMAGE           # marker file = "diese Stage als fertiges Image exportieren"
    EXPORT_NOOBS           # nur wenn NOOBS-Variante gewünscht
```

Im Workflow:

```yaml
- name: Checkout Tonado
  uses: actions/checkout@v4
  with:
    path: tonado

- name: Checkout pi-gen
  uses: actions/checkout@v4
  with:
    repository: RPi-Distro/pi-gen
    ref: arm64  # oder gepinnter Commit
    path: pi-gen

- name: Wire in Tonado stage
  run: |
    cp -r tonado/scripts/pi-gen-stage/stage-tonado pi-gen/stage-tonado
    # stage2 EXPORT-Flag entfernen, damit unsere Stage das Image liefert
    rm -f pi-gen/stage2/EXPORT_IMAGE pi-gen/stage2/EXPORT_NOOBS
```

### Wie das Release ins Image kommt

**Entscheidung: tar.gz statt git clone.** Begründung:

- Kein git/ssh-Setup im Image-Build nötig, keine Auth-Gymnastik für private Submodules (haben wir aktuell nicht, könnte aber kommen)
- Reproduzierbar: Image enthält exakt den Snapshot des getaggten Commits, kein "irgendwas zwischen HEAD und Tag"
- Schneller: tar kopieren ist O(File-Count), git clone ist O(History)
- Offline-tauglich: Image muss nicht beim First-Boot ins Internet, um den Tonado-Code zu holen

**Vorgehen:**

```yaml
- name: Build Tonado release tarball
  run: |
    cd tonado
    # Frontend lokal bauen (auf x86 schnell, pi-gen müsste es sonst in QEMU bauen)
    (cd web && npm ci && npm run build)
    # Wheel-Cache für Pi-Dependencies vorbereiten
    pip download -r requirements-pi.txt -d dist/wheels --platform linux_aarch64 --only-binary=:all: || true
    # Tarball
    tar czf ../pi-gen/stage-tonado/files/tonado-release.tar.gz \
        core/ web/build/ system/ scripts/ pyproject.toml dist/wheels/
```

Die Stage entpackt das Tarball beim Stage-Run nach `/opt/tonado/`.

**Risiko:** Wheels sind pip-Plattform-spezifisch (`linux_aarch64` vs. `linux_armv6l` für Pi Zero W). Wir brauchen pro Matrix-Variante einen eigenen Wheel-Satz. Fallback: Wheels nicht pre-downloaden, First-Boot installiert via pip aus dem Internet (macht Erst-Setup abhängig vom WLAN, was eh vorausgesetzt ist, aber langsamer).

---

## 4. Release-Upload

### Matrix-Strategy für zwei Architekturen

```yaml
jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - arch: armhf
            target: pi-zero-w
            pi_gen_ref: master
            release: bookworm
          - arch: arm64
            target: pi-3plus-4-5
            pi_gen_ref: arm64
            release: bookworm
    runs-on: ubuntu-24.04
    name: Build ${{ matrix.target }}
```

`fail-fast: false`, damit ein kaputter ARMhf-Build nicht den ARM64-Build abbricht — wir wollen im Zweifel wenigstens ein funktionierendes Image releasen.

### Upload + Release-Body

Nach erfolgreichem Build:

```yaml
- name: Compute SHA256
  id: sum
  run: |
    cd pi-gen/deploy
    sha256sum *.img.xz > SHA256SUMS-${{ matrix.target }}.txt
    echo "file=$(ls *.img.xz)" >> $GITHUB_OUTPUT

- name: Upload to release
  if: startsWith(github.ref, 'refs/tags/v') || inputs.upload == true
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    TAG="${GITHUB_REF_NAME}"
    cd pi-gen/deploy
    gh release upload "$TAG" \
      "${{ steps.sum.outputs.file }}" \
      "SHA256SUMS-${{ matrix.target }}.txt" \
      --clobber
```

Release-Body mit Flash-Anleitung wird in einem **eigenen finalen Job** (`needs: build`) per `gh release edit --notes-file` gesetzt, NICHT pro Matrix-Run — sonst rewritet jede Matrix-Variante die Notes und das letzte gewinnt:

```yaml
update-release-body:
  needs: build
  runs-on: ubuntu-latest
  if: startsWith(github.ref, 'refs/tags/v')
  steps:
    - uses: actions/checkout@v4
    - name: Fetch checksums
      run: gh release download "$GITHUB_REF_NAME" --pattern 'SHA256SUMS-*.txt' --dir sums
      env: { GH_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }
    - name: Assemble notes
      run: |
        TAG="${GITHUB_REF_NAME}"
        {
          echo "## Flash-Anleitung"
          echo ""
          echo "1. Raspberry Pi Imager öffnen"
          echo "2. Eigene Image-Datei wählen -> .img.xz unten auswählen"
          echo "3. SD-Karte flashen, Pi booten, Handy mit AP 'Tonado-Setup' verbinden"
          echo ""
          echo "## Varianten"
          echo "- \`tonado-${TAG}-pi-zero-w.img.xz\` (Pi Zero W, 32-bit)"
          echo "- \`tonado-${TAG}-pi-3plus-4-5.img.xz\` (Pi 3B+ / 4 / 5, 64-bit)"
          echo ""
          echo "## SHA256"
          echo '```'
          cat sums/*.txt
          echo '```'
          echo ""
          # Plus existierenden Changelog-Block anhängen
        } > notes.md
        gh release edit "$TAG" --notes-file notes.md
      env: { GH_TOKEN: "${{ secrets.GITHUB_TOKEN }}" }
```

---

## 5. Signing / Verifikation

**Empfehlung für Tonado-Scope: SHA256 + optional cosign keyless.**

| Option | Für uns? | Begründung |
|--------|----------|------------|
| Nur SHA256 | **Ja, Pflicht** | Minimum für Flash-Verifikation. Eltern sollen Image nicht aus dubiosen Quellen installieren. |
| cosign keyless (OIDC über GitHub Actions) | **Ja, empfohlen** | Kein Key-Management, Attestierung über GitHub-Identity, verifizierbar mit `cosign verify-blob --certificate-identity ...`. Kostet uns 2 Zeilen Workflow, kein Setup-Aufwand. |
| cosign mit eigenem Keypair | Nein | Key-Verwaltung, Rotation, Contributor-Share-Problem — zu viel Overhead für 1-5 Contributor. |
| GPG-Signatur | Nein | Toolchain-Schmerzen beim User (Pi Imager prüft nichts davon), und kein Key-Setup rechtfertigbar. |
| SLSA provenance attestation | **Optional, Stufe 2-3** | Seit 2024 `actions/attest-build-provenance` verfügbar, attestiert Build-Herkunft reproduzierbar. Für Tonado-Scope (Hobby/OSS, kein Enterprise) ist es **nice-to-have**, nicht erfolgsentscheidend. Aufwand: eine Action-Zeile. Wenn wir's einbauen, dann gleich — später nachziehen ist teurer als von Tag 1. |

```yaml
- name: Sign image (cosign keyless)
  uses: sigstore/cosign-installer@v3
- run: |
    cosign sign-blob --yes \
      --output-signature ${{ steps.sum.outputs.file }}.sig \
      --output-certificate ${{ steps.sum.outputs.file }}.pem \
      ${{ steps.sum.outputs.file }}

- name: Attest provenance
  uses: actions/attest-build-provenance@v2
  with:
    subject-path: pi-gen/deploy/${{ steps.sum.outputs.file }}
```

Docs für den End-User: kurzer Absatz in den Release-Notes, der zeigt, wie man `sha256sum -c` und `cosign verify-blob` prüft. Primär wichtig für den „datenschutz-bewusste Eltern"-Typ der Vision.

---

## 6. Test-Stage (QEMU-Boot-Smoke-Test)

**Empfehlung: Ja, aber minimal.**

Ziel: Image bootet bis zum Login, tonado.service startet, HTTP 200 auf `/api/health`. Das fängt ~80 % der Regressionen: kaputte systemd-Units, fehlende Dependencies, nginx-Config-Fehler.

### Realismus im 6-Stunden-Budget

```
qemu-system-aarch64 \
  -M raspi3b -cpu cortex-a72 -smp 4 -m 1G \
  -kernel ... -initrd ... -append ... \
  -drive file=tonado-image.img,format=raw,if=sd \
  -nographic -netdev user,id=net0,hostfwd=tcp::8080-:8080 \
  -device usb-net,netdev=net0
```

- Boot-Zeit in QEMU: ~60-90 s bis SSH-ready
- Tonado-Service-Startup: +15 s (siehe Memory)
- Smoke-Test: `curl -f http://localhost:8080/api/health` mit `timeout 180` + Retry-Loop
- **Insgesamt: ~5 min pro Variante**

Pi-Zero-W / armhf in QEMU ist fragiler (Kernel-Passgenauigkeit), darum Test nur für arm64 — das deckt den Hauptpfad, die Zero-W-Variante ist additiv und historisch stabiler, weil sie auf demselben Code basiert.

```yaml
smoke-test:
  needs: build
  runs-on: ubuntu-latest
  strategy:
    matrix:
      target: [pi-3plus-4-5]  # bewusst nur arm64
  steps:
    - name: Install QEMU
      run: sudo apt-get install -y qemu-system-arm qemu-utils
    - name: Download image
      uses: actions/download-artifact@v4
    - name: Boot + smoke test
      timeout-minutes: 10
      run: scripts/ci/qemu-smoke.sh
```

Alle Smoke-Test-Details in `scripts/ci/qemu-smoke.sh` (eigenes Script, damit Contributor es lokal reproduzieren können).

---

## 7. Rollback / Hotfix

### Re-Run ohne neues Tag

`workflow_dispatch` mit `inputs.ref` — baut vom angegebenen Branch/Tag, überschreibt Release-Assets via `gh release upload --clobber`. Häufige Fälle:

- Image kaputt, Code okay -> `workflow_dispatch(ref=v0.4.0-beta, upload=true)` macht denselben Build nochmal
- Stage-Script kaputt -> fix auf main, dann `workflow_dispatch(ref=main, upload=false)` als Trockenlauf, danach neuer Patch-Tag

### Update-Pfad: Image vs. git pull

**Das ist eine Architektur-Entscheidung, die NICHT in dieser CI-Doku fällt.** Siehe bestehende Memory-Einträge „Update-Strategie" und „Update-Mechanismus" — Tonado nutzt aktuell `git pull` + CHANGELOG-basierte Update-UI. Das bleibt.

Implikationen für CI:
- **Jedes Release bekommt trotzdem ein Image**, weil Erstinstallation darüber läuft
- **Aber nicht jedes Image muss frisch geflashed werden** — bestehende Boxen updaten sich selbst via git pull
- Image-Build-Frequenz = Release-Tag-Frequenz, nicht Commit-Frequenz
- Wenn der system-architect (noch nicht konsultiert für diese Welle) hier umschwenkt auf „Image-only Updates", dann muss das Update-UI-Konzept angepasst werden — aus CI-Sicht ändert das nichts

---

## 8. Kosten

### GitHub-Actions-Minuten

- **Public Repo: unlimited Minuten** auf `ubuntu-latest`. Tonado bleibt public, also keine direkten Kosten.
- **Queue-Zeit**: Free-Tier-Public-Repos teilen sich öffentliche Runner-Pools. Erfahrungswerte 2025/26: Ubuntu-Runner 0-5 min Queue, ARM64-Runner gelegentlich 10-30 min Queue in Peak-Zeit. Unkritisch für Release-Builds (passieren wöchentlich, nicht stündlich).
- Matrix mit 2 Varianten + Smoke-Test: ~80 Runner-Minuten pro Release. Wenn wir 1x pro Woche releasen: ~5 Std/Monat. Immer noch frei.

### Release-Asset-Storage

- Public Repos: **kein hartes Storage-Limit** auf Releases (anders als Actions-Cache mit 10 GB/Repo).
- **Harte Grenze: 2 GB pro einzelne Datei.** Geschätzte Image-Größe:

| Image | Roh | xz-komprimiert |
|-------|-----|----------------|
| Pi Zero W (armhf, Lite + Tonado) | ~1.8 GB | ~600-800 MB |
| Pi 3/4/5 (arm64, Lite + Tonado) | ~2.2 GB | ~750-950 MB |

**Komprimierte Images passen komfortabel unter 2 GB.** Unkomprimierte `.img` wären Grenzfall bei arm64 — wir laden nur `.img.xz` hoch, alles gut. Release-Größe gesamt pro Tag: ~1.5-2 GB. 10 Tags = 20 GB, absolut vertretbar für öffentliches OSS-Projekt.

### Traffic-Kosten

Public-Repo-Downloads sind für Publisher kostenlos. End-User zahlen nichts. Kein CDN-Setup nötig.

---

## 9. YAML-Skeleton

Kein vollständiger Workflow — das ist der Stub, der die Stage-Integration und Upload zeigt. Der Rest (Caching, Matrix-Defaults, Secrets) kommt in der Umsetzungs-Welle.

```yaml
name: Build Pi Image

on:
  push:
    tags: ['v*']
  workflow_dispatch:
    inputs:
      upload: { type: boolean, default: false }
      ref: { type: string, default: '' }
  pull_request:
    paths:
      - 'scripts/pi-gen-stage/**'
      - '.github/workflows/pi-image.yml'

permissions:
  contents: write      # für gh release upload
  id-token: write      # für cosign keyless + attest-build-provenance
  attestations: write  # für attest-build-provenance

jobs:
  build:
    strategy:
      fail-fast: false
      matrix:
        include:
          - arch: armhf
            target: pi-zero-w
            pi_gen_ref: master
          - arch: arm64
            target: pi-3plus-4-5
            pi_gen_ref: arm64
    runs-on: ubuntu-24.04
    name: Build ${{ matrix.target }}
    steps:
      - name: Checkout Tonado
        uses: actions/checkout@v4
        with:
          path: tonado
          ref: ${{ inputs.ref || github.ref }}

      - name: Setup Node + Python
        uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: 'tonado/web/package-lock.json' }
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }

      - name: Build frontend + release tarball
        working-directory: tonado
        run: |
          cd web && npm ci && npm run build && cd ..
          tar czf ../tonado-release.tar.gz \
              core/ web/build/ system/ pyproject.toml README.md CHANGELOG.md

      - name: Checkout pi-gen
        uses: actions/checkout@v4
        with:
          repository: RPi-Distro/pi-gen
          ref: ${{ matrix.pi_gen_ref }}
          path: pi-gen

      - name: Wire in Tonado stage
        run: |
          cp -r tonado/scripts/pi-gen-stage/stage-tonado pi-gen/stage-tonado
          cp tonado-release.tar.gz pi-gen/stage-tonado/files/
          rm -f pi-gen/stage2/EXPORT_IMAGE pi-gen/stage2/EXPORT_NOOBS

      - name: Configure pi-gen
        run: |
          cat > pi-gen/config <<EOF
          IMG_NAME='tonado-${{ github.ref_name }}-${{ matrix.target }}'
          RELEASE=bookworm
          TARGET_HOSTNAME=tonado
          ENABLE_SSH=1
          STAGE_LIST='stage0 stage1 stage2 stage-tonado'
          DEPLOY_COMPRESSION=xz
          EOF

      - name: Cache pi-gen stages
        uses: actions/cache@v4
        with:
          path: pi-gen/work
          key: pi-gen-${{ matrix.target }}-${{ hashFiles('tonado/scripts/pi-gen-stage/**', 'pi-gen/config') }}
          restore-keys: pi-gen-${{ matrix.target }}-

      - name: Build image
        working-directory: pi-gen
        run: sudo ./build-docker.sh
        env: { PI_GEN_CI: 1 }

      - name: Compute SHA256 + sign
        id: sum
        run: |
          cd pi-gen/deploy
          IMG=$(ls *.img.xz)
          sha256sum "$IMG" > "SHA256SUMS-${{ matrix.target }}.txt"
          echo "file=$IMG" >> $GITHUB_OUTPUT

      - uses: sigstore/cosign-installer@v3
      - name: Cosign sign
        working-directory: pi-gen/deploy
        run: |
          cosign sign-blob --yes \
            --output-signature "${{ steps.sum.outputs.file }}.sig" \
            --output-certificate "${{ steps.sum.outputs.file }}.pem" \
            "${{ steps.sum.outputs.file }}"

      - uses: actions/attest-build-provenance@v2
        with: { subject-path: 'pi-gen/deploy/${{ steps.sum.outputs.file }}' }

      - name: Upload artifact (always, for PR dry-runs)
        uses: actions/upload-artifact@v4
        with:
          name: image-${{ matrix.target }}
          path: pi-gen/deploy/
          retention-days: 7

      - name: Upload to release
        if: startsWith(github.ref, 'refs/tags/v') || inputs.upload == true
        env: { GH_TOKEN: '${{ secrets.GITHUB_TOKEN }}' }
        working-directory: pi-gen/deploy
        run: |
          gh release upload "${{ github.ref_name }}" \
            "${{ steps.sum.outputs.file }}" \
            "${{ steps.sum.outputs.file }}.sig" \
            "${{ steps.sum.outputs.file }}.pem" \
            "SHA256SUMS-${{ matrix.target }}.txt" \
            --clobber

  smoke-test:
    needs: build
    runs-on: ubuntu-latest
    if: github.event_name != 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/download-artifact@v4
        with: { name: image-pi-3plus-4-5, path: ./img }
      - run: sudo apt-get install -y qemu-system-arm qemu-utils xz-utils
      - run: scripts/ci/qemu-smoke.sh ./img/*.img.xz

  update-release-notes:
    needs: [build, smoke-test]
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/checkout@v4
      - name: Assemble + publish notes
        env: { GH_TOKEN: '${{ secrets.GITHUB_TOKEN }}' }
        run: scripts/ci/release-notes.sh "${{ github.ref_name }}"
```

---

## 10. Umsetzungs-Reihenfolge

Damit dieser Plan nicht auf einmal einschlägt:

1. **Stage-Skeleton**: `scripts/pi-gen-stage/stage-tonado/` mit `00-packages`, `00-run.sh`, `files/tonado.service`, `files/first-boot.sh`. Lokal mit pi-gen testen, ohne CI.
2. **Lokaler Build-Durchlauf**: auf einer x86-Ubuntu-VM pi-gen + unsere Stage bauen, Image in QEMU booten. Erst wenn das funktioniert, CI einschalten.
3. **Workflow ohne Upload**: PR mit `.github/workflows/pi-image.yml`, nur Artifact-Upload. Matrix-Stabilität + Cache-Timing verifizieren.
4. **Release-Upload aktivieren**: nach dem ersten Tag-Build, der grün durchläuft, `gh release upload` freischalten.
5. **Signing + Attestation**: in einem eigenen PR, ändert nichts am Image selbst.
6. **QEMU-Smoke-Test**: als letzter Baustein, weil er am fragilsten ist und wir den Rest nicht dahinter blocken wollen.

Parallelisierbare Wellen: (1)+(2) sequenziell, danach (3) und separate Arbeit an `scripts/ci/qemu-smoke.sh` parallel.
