# Entwicklung

Anleitung für Entwickler, die an Tonado mitarbeiten möchten.

## Tech Stack

| Schicht | Technologie |
|---------|------------|
| Frontend | Svelte 5 + SvelteKit (adapter-static) + Tailwind CSS v4 |
| Backend | Python 3.11+ / FastAPI / Uvicorn |
| Audio | MPD via python-mpd2 (async) |
| Config | SQLite (WAL-Modus) |
| Auth | PBKDF2 + PyJWT (PIN-basiert, 3 Tiers) |

## Repo-Struktur

```
web/          Frontend (Svelte 5 + Tailwind CSS v4, PWA)
core/         Backend (Python / FastAPI)
  routers/    API-Routen
  services/   Business-Logik
  hardware/   RFID, Gyro, GPIO
  schemas/    Pydantic Models
system/       Installationsscripts, systemd-Service
docs/         Dokumentation
tests/        Tests
```

## Entwicklungsumgebung einrichten

### Voraussetzungen

- Python 3.11+
- Node.js 20+
- Git

### Setup

```bash
git clone https://github.com/t13gazh/tonado.git
cd tonado

# Backend
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"    # Windows
# .venv/bin/pip install -e ".[dev]"      # Linux/Mac

# Frontend
cd web && npm install
```

### Starten

Zwei Terminals:

```bash
# Terminal 1: Backend
uvicorn core.main:app --host 127.0.0.1 --port 8080

# Terminal 2: Frontend (Dev-Server mit Hot-Reload)
cd web && npm run dev
```

Browser: `http://localhost:5173`

### Mock-Modus

Hardware-Services (RFID, Gyro, GPIO) laufen auf Windows/Mac automatisch im Mock-Modus. MPD muss nicht installiert sein — der Player-Service fängt Verbindungsfehler ab.

## Frontend auf den Pi deployen

Node.js ist auf dem Pi **nicht** installiert. Das Frontend wird lokal gebaut und liegt als Build im Repo.

```bash
cd web && npm run build
# Build committen und pushen — Pi zieht Update über die App
```

Alternativ manuell per scp:

```bash
scp -r web/build/ pi@<hostname>.local:/opt/tonado/web/
ssh pi@<hostname>.local "sudo systemctl restart tonado"
```

## Tests

```bash
# Alle Tests
.venv/Scripts/pytest              # Windows
# .venv/bin/pytest                # Linux/Mac

# Einzelne Datei
pytest tests/test_player.py

# Mit Ausgabe
pytest -v -s
```

## Code-Stil

- **Linter:** Ruff (konfiguriert in `pyproject.toml`)
- **Code:** Englisch (Variablen, Funktionen, Kommentare, Commits)
- **UI-Texte:** Deutsch mit echten Umlauten
- **Commits:** Conventional Commits, Englisch
- **Branch:** `main` als Standard-Branch

```bash
# Linter prüfen
ruff check .

# Linter auto-fix
ruff check --fix .
```

## Architektur

Detaillierte Architektur-Dokumentation: [ARCHITEKTUR.md](ARCHITEKTUR.md)

Kurzfassung: Service-Architektur mit Event-Bus. Unabhängige Python-Services kommunizieren über asyncio Events. Frontend ist eine statische PWA (Svelte 5), die über REST und WebSocket mit dem Backend spricht.

## Weiterführende Docs

- [Architektur](ARCHITEKTUR.md) — Service-Diagramm, Datenmodell, Security
- [Roadmap](ROADMAP.md) — Meilensteine und Phasen
- [Vision](../VISION.md) — Produktvision und UX-Prinzipien
- [Hardware](../fuer-bastler/hardware.md) — Unterstützte Hardware und Verkabelung
