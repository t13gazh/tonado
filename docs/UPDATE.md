# Tonado aktualisieren

Diese Anleitung richtet sich an Endnutzer. Du brauchst kein SSH und keinen Git-Client — alles läuft über die Web-App.

## Schnellversion

1. Web-App öffnen → **Einstellungen** (Experten-Login: PIN eingeben falls gesetzt).
2. **System** → **Update** → **Nach Updates suchen**.
3. Wenn ein Update gefunden wird, Changelog durchlesen und **Update installieren** klicken.
4. Die Box startet sich am Ende neu. Wenige Sekunden später läuft sie wieder.

**Wichtig:** Während der Installation die Box nicht vom Strom trennen.

## Was passiert im Hintergrund

- Tonado zieht die neueste Version per `git pull` aus dem öffentlichen Repo.
- Wenn sich die Python-Abhängigkeiten geändert haben (`pyproject.toml`), werden sie nachinstalliert.
- Schlägt die Dependency-Installation fehl, rollt Tonado automatisch auf die vorherige Version zurück — inklusive Abhängigkeiten. Du wirst mit einer Fehlermeldung darauf hingewiesen.
- Zuletzt wird der Service neu gestartet (Audio fällt für 5-15 Sekunden aus, je nach Pi-Modell).

## Voraussetzungen

- Der Pi muss online sein (Internet erreichbar, nicht nur LAN).
- Der Installations-Pfad (Standard: `/opt/tonado`) muss ein Git-Checkout sein. Bei manueller Installation per `install.sh` ist das automatisch der Fall.
- **Experten-PIN muss gesetzt sein.** Ohne PIN verweigert die Box Updates aus Sicherheitsgründen.

## Fehlersuche

| Symptom | Ursache | Abhilfe |
|---------|---------|---------|
| "Kein Git-Repository" | Pi wurde per ZIP statt `install.sh` eingerichtet | Neu installieren oder `git init` manuell (Experten) |
| "git pull fehlgeschlagen" | Lokale Änderungen / kein Internet | Logs prüfen (`journalctl -u tonado`), Box neustarten |
| "Abhängigkeiten konnten nicht installiert werden. Rollback durchgeführt." | Neue Python-Version fehlt, Speicher voll, Paket-Registry down | `df -h` + `pip install -e .[pi]` manuell, dann Issue öffnen |
| Update hängt > 10 min auf dem Pi Zero W | ARMv6 kompiliert aiosqlite neu (bekannt) | Warten — erstmaliger Build dauert einmalig 20-30 min |

## Manuelles Update (nur Experten)

Auf der Box per SSH:
```bash
cd /opt/tonado
git pull
.venv/bin/pip install -e ".[pi]"
sudo systemctl restart tonado
```

## Rollback

Falls ein Update schief geht und der Auto-Rollback nicht reichte:
```bash
cd /opt/tonado
git log --oneline -5         # letzte Commits anschauen
git reset --hard <commit>    # auf den gewünschten Commit
.venv/bin/pip install -e ".[pi]"
sudo systemctl restart tonado
```

## Update-Benachrichtigungen

Die Web-App prüft **nicht automatisch** auf Updates. Du musst sie manuell anstoßen. Hintergrund: Die Box soll keine Hintergrund-Internetverbindungen aufbauen.

## Release-Kanäle

Aktuell gibt es nur `main` (entwickelte Version). Eine stabile Release-Schiene kommt mit `v0.2.0-beta`.
