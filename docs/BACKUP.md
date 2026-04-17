# Backup & Wiederherstellung

Sicherst du deine Konfiguration, deine Figuren-Zuordnungen und deine eigenen Radio/Podcast-Streams. Audio-Dateien selbst sind aktuell **nicht** Teil des Backups.

## Backup erstellen

1. Web-App öffnen → **Einstellungen** → **System** → **Backup**.
2. **Backup herunterladen** klicken.
3. Die Datei heißt `tonado-backup-<datum>.json` und landet im Download-Ordner deines Geräts.
4. Sicher aufbewahren — im besten Fall nicht auf dem gleichen Gerät wie die Box.

Für den Export brauchst du Eltern-PIN.

## Wiederherstellung

1. Im gleichen Dialog **Backup einspielen** wählen.
2. Die JSON-Datei hochladen.
3. Bestätigen, dass bestehende Daten überschrieben werden dürfen.
4. Die Box importiert Konfig, Karten und Streams. Audio-Dateien musst du separat übertragen (via SMB, sftp oder Upload).

Für den Import brauchst du Experten-PIN (höhere Schutzstufe, weil die Datei die gesamte Box überschreiben kann).

## Was ist im Backup drin?

| Teil | Enthalten |
|------|-----------|
| Figuren-/Karten-Zuordnungen (`cards`) | ✅ |
| Eltern-Einstellungen (Lautstärke-Limits, Sleep-Timer-Defaults) | ✅ |
| Hardware-Konfiguration (Audio-Output, GPIO-Button-Belegung, Gyro) | ✅ |
| Gespeicherte WLAN-Credentials | ❌ (absichtlich — Credentials stehen nie im Backup) |
| Audio-Secrets / JWT-Secret | ❌ (werden vor Export gefiltert) |
| Playlist-Definitionen | ✅ (Referenzen auf Audio-Pfade, nicht die Dateien selbst) |
| Radio-Stationen + Podcast-Feeds | ✅ |
| Audio-Dateien (MP3, FLAC, OGG, Cover) | ❌ (wegen Größe — siehe Backlog „Vollbackup inkl. Content") |

## Format

Die Backup-Datei ist eine menschen-lesbare JSON mit folgender Struktur:

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

## Versions-Kompatibilität

Tonado akzeptiert Backups von älteren `v0.2.x`-Versionen. Backups aus **zukünftigen** Versionen (`v0.3+`) werden aktuell mit einer Warnung importiert — fehlen Felder, werden sie ignoriert.

## Cross-Box Wiederherstellung

Backup von Pi A auf Pi B einspielen:
- ✅ Karten- und Playlist-Zuordnungen übernehmen wenn die Audio-Pfade gleich sind.
- ⚠️ Hardware-Config kann falsch sein — der Audio-Output `hw:1` existiert auf einem Pi mit anderer DAC-Konfiguration evtl. nicht.
- **Empfehlung:** Nach dem Import erneut den Setup-Wizard starten (Einstellungen → System → **Einrichtung neu starten**, Experten-PIN). Das re-detektiert Hardware, Zuordnungen bleiben erhalten.

## Automatische Backups

Aktuell **nicht** implementiert. Im Backlog vorgesehen: tägliches Auto-Backup auf einen angeschlossenen USB-Stick.

## Fehlersuche

| Fehler | Ursache | Abhilfe |
|--------|---------|---------|
| `Invalid backup file` | JSON defekt / falsche Kodierung | Neu exportieren |
| `Not a valid Tonado backup` | Fremdes Format oder Version-Feld fehlt | Prüfe, dass die Datei mit `{"version": ...}` beginnt |
| Import-Checkliste zeigt Fehler | Schema-Validation: Pflichtfelder fehlen | Details in der Meldung — die ersten 5 Fehler werden gelistet |
| Cards importiert aber Audio spielt nicht | Audio-Dateien fehlen im Media-Ordner | Audio-Dateien manuell nach `/home/<user>/tonado/media/` kopieren |
