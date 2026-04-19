# Backup & Wiederherstellung

Ein Backup sichert deine Konfiguration, deine Figuren-Zuordnungen und deine gespeicherten Radio-Sender und Podcasts. So kannst du jederzeit auf denselben Stand zurück — nach einem Umzug auf eine neue Box, nach einem Fehlgriff in den Einstellungen, oder einfach zur Sicherheit.

Musik-Dateien selbst sind heute **nicht** Teil des Backups — die bewahrst du separat auf (z.B. auf deinem Computer, von wo du sie hochgeladen hast).

## Backup erstellen

1. In der App die **Einstellungen** öffnen.
2. **System → Backup** aufrufen.
3. **Backup herunterladen** tippen.
4. Die Datei landet im Download-Ordner deines Handys oder Computers.
5. Sicher aufbewahren — am besten nicht nur auf dem Gerät, mit dem du die Box bedienst.

Für den Export fragt die Box nach der Eltern-PIN.

## Backup einspielen

1. In der App unter **Einstellungen → System → Backup** die Option **Backup einspielen** wählen.
2. Die gespeicherte Datei auswählen.
3. Bestätigen, dass die bestehenden Einstellungen überschrieben werden dürfen.
4. Die Box übernimmt deine Figuren-Zuordnungen, Einstellungen und gespeicherten Streams.

Für den Import fragt die Box nach der Experten-PIN — weil ein Import die gesamte Box überschreiben kann.

## Was ist im Backup drin?

- Deine Figuren- und Karten-Zuordnungen (welche Figur spielt was).
- Eltern-Einstellungen wie Lautstärke-Obergrenze und Standard-Einschlaftimer.
- Die Hardware-Konfiguration, die der Einrichtungs-Assistent erkannt hat.
- Deine eigenen Playlisten.
- Deine Liste gespeicherter Radio-Sender und Podcast-Feeds.

**Nicht im Backup** (mit Absicht):

- WLAN-Passwörter — werden aus Sicherheitsgründen nie gesichert.
- Musik-Dateien selbst — wegen der Größe. Die überträgst du bei Bedarf über die Upload-Funktion in der App.

## Nach einem Hardware-Wechsel

Wenn du das Backup auf eine andere Box einspielst — etwa weil die alte Box kaputt ist oder du auf einen schnelleren Raspberry Pi umsteigst — dann übernimmt die neue Box deine Figuren-Zuordnungen und Einstellungen. **Empfehlung:** Führe danach einmal den Einrichtungs-Assistenten neu aus (Einstellungen → System → Einrichtung neu starten). So stellt sich die neue Box auf ihre eigene Hardware ein. Deine Zuordnungen bleiben dabei erhalten.

## Wenn etwas nicht klappt

Starte die Box einfach neu und versuche es erneut. Hilft das nicht, melde dich bitte auf [GitHub](https://github.com/t13gazh/tonado/issues) — wir helfen gern.

## Für Technik-Profis

Technische Details zum Backup-Format (JSON-Struktur, Versions-Kompatibilität, Cross-Box-Wiederherstellung, CLI-Pfade, Fehlercodes): siehe **[Backup-Details für Bastler](../fuer-bastler/backup-details.md)**.
