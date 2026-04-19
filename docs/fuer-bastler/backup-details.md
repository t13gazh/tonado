# Backup-Details (für Bastler)

Technische Details zum Backup-/Restore-Mechanismus. Die Eltern-Sicht dazu steht in **[docs/fuer-eltern/BACKUP.md](../fuer-eltern/BACKUP.md)**.

## Format

Die Backup-Datei ist eine JSON mit folgender Struktur:

```json
{
  "version": "1",
  "exported_at": "2026-04-17T12:00:00Z",
  "cards": [ ... ],
  "config": { ... },
  "playlists": [ ... ],
  "streams": { "radio": [ ... ], "podcasts": [ ... ] }
}
```

Dateiname-Muster: `tonado-backup-<datum>.json`.

## Was gesichert wird

| Teil | Enthalten |
|------|-----------|
| Figuren-/Karten-Zuordnungen (`cards`) | ja |
| Eltern-Einstellungen (Lautstärke-Limits, Sleep-Timer-Defaults) | ja |
| Hardware-Konfiguration (Audio-Output, GPIO-Button-Belegung, Gyro) | ja |
| Gespeicherte WLAN-Credentials | nein (absichtlich — Credentials stehen nie im Backup) |
| `jwt_secret` und andere Secrets | nein (werden vor dem Export gefiltert) |
| Playlist-Definitionen | ja (Referenzen auf Audio-Pfade, nicht die Dateien selbst) |
| Radio-Stationen + Podcast-Feeds | ja |
| Audio-Dateien (MP3, FLAC, OGG, Cover) | nein (wegen Größe — siehe Backlog „Vollbackup inkl. Content") |

## Versions-Kompatibilität

Tonado akzeptiert Backups aus älteren Versionen. Backups aus **künftigen** Versionen werden aktuell mit einer Warnung importiert — fehlen Felder, werden sie ignoriert.

## Cross-Box-Wiederherstellung

Backup von Box A auf Box B einspielen:

- Karten- und Playlist-Zuordnungen werden übernommen, wenn die Audio-Pfade gleich sind.
- Die Hardware-Konfiguration kann nicht passen — der gesicherte Audio-Output (z.B. ein bestimmter DAC-Gerätepfad) existiert auf einer neuen Box mit anderer Hardware evtl. nicht.
- **Empfehlung:** Nach dem Import den Setup-Wizard neu starten (Einstellungen → System → **Einrichtung neu starten**, Experten-PIN). Das re-detektiert die Hardware; die Zuordnungen bleiben erhalten.

## Automatische Backups

Aktuell nicht implementiert. Im Backlog: tägliches Auto-Backup auf einen angeschlossenen USB-Stick.

## Audio-Dateien übertragen

Audio-Dateien sind nicht Teil des Backups. Für die Übertragung der eigentlichen Musik:

- **Über die App:** Upload-Funktion in der Bibliothek.
- **Manuell (Experten):** Dateien direkt in den Musik-Ordner der Box kopieren (siehe Bibliothek-Anleitung und Deployment-Infos in `docs/fuer-entwickler/`).

## Fehlersuche

| Fehler | Ursache | Abhilfe |
|--------|---------|---------|
| `Invalid backup file` | JSON defekt / falsche Kodierung | Backup neu exportieren |
| `Not a valid Tonado backup` | Fremdes Format oder `version`-Feld fehlt | Prüfen, dass die Datei mit `{"version": ...}` beginnt |
| Import-Checkliste zeigt Fehler | Schema-Validation: Pflichtfelder fehlen | Details in der Meldung — die ersten 5 Fehler werden gelistet |
| Cards importiert, aber Audio spielt nicht | Audio-Dateien fehlen im Media-Ordner | Audio-Dateien manuell übertragen (siehe oben) |
