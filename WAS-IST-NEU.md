# Was ist neu

Kurze, eltern-freundliche Übersicht pro Version. Dieser Text wird im
Update-Dialog der Web-App angezeigt. Keine technischen Details, keine
Markdown-Formatierungen wie **fett** oder *kursiv* — nur Klartext,
Überschriften mit `###` und Listen mit `- `.

Die ausführliche Änderungs-Historie für Entwickler steht in
[CHANGELOG.md](CHANGELOG.md).

## [0.3.1-beta] — 2026-04-23

### Auto-Update wird zuverlässig

Das Einrichten neuer Versionen dauert auf dem kleinen Pi Zero W manchmal länger als eine halbe Minute. Genau dieser längere Teil hat den Update-Knopf in 0.3.0-beta still hängen lassen. Ab dieser Version läuft es sauber durch.

### Wichtig für dieses eine Update

Der Fix lebt an genau der Stelle, die in 0.3.0-beta den Fehler hatte. Der Update-Knopf in der App zieht also immer noch die alte Logik, bis du einmal manuell auf 0.3.1 gehst. Einmaliger Umweg per SSH auf die Box:

curl -sSL https://raw.githubusercontent.com/t13gazh/tonado/main/system/install.sh | sudo bash

Ab dann läuft „Nach Updates suchen" zuverlässig aus der App — für alle weiteren Updates reicht der App-Weg.

### Was du sonst merkst

- Live-Statuszeile im Update-Dialog: Wird installiert, Neustart, Prüfung, Auf neue Version aktualisiert.
- „Seite neu laden"-Button für die seltenen Fälle, in denen die Box länger braucht als erwartet.
- Update-Check ist begrenzt auf 6 Versuche pro Minute — schont die SD-Karte, falls die App mal in einer Schleife nachfragt.
- „Box ist bereits aktuell" bekommt eine eigene kurze Bestätigung statt stummer Rückkehr.

### Sicherheit

Die Box läuft jetzt mit minimalen Root-Rechten: genau drei Kommandos (Neustart, Herunterfahren, Reboot) dürfen ohne Passwort laufen, alles andere braucht den Standard-Login. Die interne Schnittstelle ist nur noch lokal auf der Box erreichbar — Zugang läuft ausschließlich über den Web-Server.

Deine Figuren, Einstellungen und Musik bleiben beim Update erhalten.

## [0.3.0-beta] — 2026-04-22

### Erste Beta

Die Box ist jetzt offiziell aus dem Experimentier-Stadium raus. Auf
Pi 3B+ und Pi Zero W gründlich getestet, Hauptfunktionen stabil.

### Was du merkst

- Sleep-Timer zeigt die Restzeit direkt im Player — mit Knopf zum
  Verlängern um 5 oder 10 Minuten.
- Cover-Bilder in Player und Bibliothek. Entweder aus den Musik-Dateien
  selbst, oder du legst eine cover.jpg in den Ordner.
- Suche in der Bibliothek: ein Feld für alle Bereiche (Ordner, Radio,
  Podcasts, Playlisten).
- Browser-Audio bleibt beim Figuren-Wechsel stabil — kein Abbrechen mehr
  bei jedem Stream.
- PIN-Eingabe im Setup mit vier einzelnen Ziffern-Boxen, springt
  automatisch zur nächsten Zeile.
- Hilfe-Taste in jedem Setup-Schritt mit Tipps fürs Troubleshooting.
- WLAN-Rettung: fällt dein Heim-WLAN länger aus, öffnet die Box
  automatisch ihren Einrichtungs-Modus mit QR-Code zum Verbinden.

### Polish

- Einheitliches Aussehen bei Fehlermeldungen, Auswahl-Leisten und
  Schaltern in allen Einstellungen.
- Figuren-Löschen nur noch im aufgeklappten Detail-Fenster — nicht mehr
  versehentlich auf der Kachel.
- Hochgeladene Ordner-Cover gewinnen über das eingebettete Bild in der
  MP3.

Deine Figuren, Einstellungen und Musik bleiben beim Update erhalten.
