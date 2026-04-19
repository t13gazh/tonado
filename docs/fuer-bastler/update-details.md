# Update-Details (für Bastler)

Technische Details zum Update-Mechanismus. Die Eltern-Sicht dazu steht in **[docs/fuer-eltern/UPDATE.md](../fuer-eltern/UPDATE.md)**.

## Was im Hintergrund passiert

- Tonado zieht die neueste Version per `git pull` aus dem öffentlichen Repo.
- Wenn sich die Python-Abhängigkeiten geändert haben (`pyproject.toml`), werden sie nachinstalliert.
- Schlägt die Dependency-Installation fehl, rollt Tonado automatisch auf die vorherige Version zurück — inklusive Abhängigkeiten. Der Fehler wird im UI angezeigt.
- Zuletzt wird der Service neu gestartet (Audio fällt für 5-15 Sekunden aus, je nach Pi-Modell).

## Voraussetzungen

- Der Pi muss online sein (Internet erreichbar, nicht nur LAN).
- Der Installations-Pfad (Standard: `/opt/tonado`) muss ein Git-Checkout sein. Bei manueller Installation per `install.sh` ist das automatisch der Fall.
- **Experten-PIN muss gesetzt sein.** Ohne PIN verweigert die Box Updates aus Sicherheitsgründen.

## Release-Kanäle

Tonado ist aktuell in der Alpha-Phase: Das Update-Verfahren zieht jeden neuen Commit auf dem `main`-Branch. Ab der Beta-Version gibt es getaggte Releases mit Changelog und optional manueller Freigabe pro Update.

## Manuelles Update via SSH

Per SSH auf dem Pi:

```bash
cd /opt/tonado
git pull
.venv/bin/pip install -e ".[pi]"
sudo systemctl restart tonado
```

## Rollback

Falls ein Update schiefgeht und der Auto-Rollback nicht reichte:

```bash
cd /opt/tonado
git log --oneline -5         # letzte Commits anschauen
git reset --hard <commit>    # auf den gewünschten Commit
.venv/bin/pip install -e ".[pi]"
sudo systemctl restart tonado
```

## Fehlersuche

| Symptom | Ursache | Abhilfe |
|---------|---------|---------|
| „Kein Git-Repository" | Pi wurde per ZIP statt `install.sh` eingerichtet | Neu installieren oder `git init` manuell |
| „git pull fehlgeschlagen" | Lokale Änderungen / kein Internet | Logs prüfen (`journalctl -u tonado`), Box neustarten |
| „Abhängigkeiten konnten nicht installiert werden. Rollback durchgeführt." | Neue Python-Version fehlt, Speicher voll, Paket-Registry down | `df -h` prüfen, `.venv/bin/pip install -e ".[pi]"` manuell, dann Issue öffnen |
| Update hängt > 10 min auf dem Pi Zero W | ARMv6 kompiliert aiosqlite neu (bekannt) | Warten — der erstmalige Build dauert einmalig 20-30 min |

## Hinweis zur automatischen Update-Prüfung

Die Web-App prüft **nicht automatisch** auf Updates. Sie müssen manuell angestoßen werden. Hintergrund: Die Box soll keine Hintergrund-Internetverbindungen aufbauen.
