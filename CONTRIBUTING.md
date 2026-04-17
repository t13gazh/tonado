# Beiträge zu Tonado

Schön, dass du mithelfen willst. Tonado ist ein Open-Source-Projekt, das eine Kinder-Musikbox baut, die *nicht* von einem Hersteller oder Abo abhängig ist — je mehr Augen auf dem Code liegen, desto besser.

## Zuerst — die Leitplanken

- **Kinder sind die Zielgruppe.** Alles am Produkt (UX, Performance, Fehlerverhalten) muss für nicht-technische Eltern funktionieren. Wenn ein Feature nur für Entwickler cool ist, gehört es nicht rein.
- **Lokal läuft alles.** Keine Cloud-Services, keine Pflicht-Accounts, keine Tracker. Features, die das aufweichen, werden nicht übernommen.
- **Keine Marken-Klone.** Wir benennen oder imitieren keine kommerziellen Musikboxen. Das schützt das Projekt und respektiert andere.

## Bevor du anfängst

1. **Issue durchsuchen / öffnen.** Für größere Änderungen bitte vorher ein Issue, damit wir die Richtung klären bevor Code geschrieben wird.
2. **`CLAUDE.md` beachten.** Die Datei liegt im Repo-Root (nur lokal — nicht im öffentlichen Clone) und erklärt Namenskonventionen, Commit-Format und Sprachregeln. Die wichtigsten Punkte:
   - Code, Commits, Kommentare: Englisch.
   - UI-Strings und User-Doku: Deutsch mit echten Umlauten (ä/ö/ü/ß — nie ae/oe/ue).
   - Branch: `main` (nicht `master`).
3. **Lokal aufsetzen.** [docs/installation.md](docs/installation.md) für den Pi, [docs/entwicklung.md](docs/entwicklung.md) für die Dev-Umgebung (Backend: `pip install -e ".[dev]"`, Frontend: `cd web && npm install`).

## Workflow

1. Fork + Feature-Branch (`feat/meine-änderung` oder `fix/bug-xyz`).
2. Änderung mit Tests absichern. Backend-Tests laufen mit `.venv/Scripts/pytest` (Windows) bzw. `.venv/bin/pytest` (Unix). Frontend-Build mit `cd web && npm run build`.
3. Falls UI berührt wurde: `web/build/` committen (siehe README für Begründung — auf dem Pi wird nicht gebuildet).
4. Commit-Message im Conventional-Commits-Format:
   ```
   feat(player): add shuffle gesture handler

   Co-Authored-By: <dein Name> <email@example.com>
   ```
5. Pull Request gegen `main`. Beschreibe **warum** die Änderung existiert, nicht nur was sie tut.

## Tests

- Neue Features brauchen Tests. Regressions-Fixes auch — sonst kommt der Bug wieder.
- Hardware-Pfade werden gemockt, damit die Suite auf Windows und auf CI läuft (siehe `tests/mock_mpd.py`, `MockRfidReader`, `MockGyroSensor`, `MockGpioButton*`).
- Integration-Tests für Router nutzen `test_routers.py` als Vorlage.
- Pre-existing Failures? Bitte *nicht* stillschweigend deaktivieren — entweder fixen oder im PR begründen.

## Security

Vor einem PR mit Security-Impact bitte erst [SECURITY.md](SECURITY.md) lesen. Vulnerabilities bitte *nicht* in öffentlichen Issues melden.

## Hardware

Wir supportet offiziell Pi 3B+ (getestet). Pi Zero W / Zero 2 W / Pi 4 / 5 laufen experimentell — wer sie testet: Bitte Ergebnisse im Issue-Tracker dokumentieren (Backlog unter "Pi-Kompatibilitätsmatrix").

## Fragen

Issue aufmachen und `question` taggen. Antwort gibt's in der Regel innerhalb weniger Tage.

Danke! 🎶
