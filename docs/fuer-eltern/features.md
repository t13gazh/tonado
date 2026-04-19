# Was Tonado kann

Diese Seite ist für dich, wenn du wissen willst, was deine Box heute tatsächlich leistet, was bald dazu kommt und was in fernerer Zukunft vielleicht möglich wird. Kein Fachjargon, keine Code-Referenzen.

## Was Tonado heute kann (Stand 0.2.1-alpha)

### Musik abspielen

- **Figur auflegen → Musik spielt.** Eine Figur oder Karte mit eingebautem RFID-Chip auflegen, der Rest passiert von allein.
- **Mehrere Quellen in einer Bibliothek:** eigene Musik-Dateien (MP3, FLAC, OGG, WAV), Internetradio, Podcasts als RSS-Feed und eigene Playlisten.
- **Suche** über Ordner, Radio-Sender, Podcasts und Playlisten — auch mit Umlauten oder ohne („Ueber" findet „Über").
- **Cover-Bilder** werden automatisch aus deinen Musik-Dateien gezogen oder aus einer `cover.jpg` im Ordner. Wenn nichts da ist, zeigt Tonado eine farbige Kachel mit dem Anfangsbuchstaben.
- **Verschiedene Quellen pro Figur:** eine Figur kann einem Ordner, einem Radiosender, einem Podcast oder einer Playlist zugeordnet werden.

### Einschlafen und Lautstärke

- **Einschlaftimer:** Musik nach einer eingestellten Zeit sanft ausblenden lassen statt abrupt stoppen.
- **Countdown im Player:** Du siehst, wie viel Zeit der Timer noch läuft. Die letzte Minute färbt sich warm.
- **Lautstärke-Obergrenze:** Maximale Lautstärke begrenzen, damit das Kinderohr geschützt bleibt, egal wie oft der „lauter"-Knopf gedrückt wird.
- **Start-Lautstärke:** Die Box startet immer mit einer definierten Lautstärke — egal wie laut sie zuletzt war.

### Kontrolle aus der Ferne

- **Smartphone als Fernbedienung:** Musik abspielen, pausieren, skippen, Lautstärke regeln, alles vom Handy aus.
- **PIN-Schutz für Eltern-Bereiche:** Bibliothek, Figur-Zuordnung und Einstellungen sind vor neugierigen Kinderfingern geschützt.
- **Experten-PIN** für System-Seiten (Hardware neu erkennen lassen, Box neu starten, WLAN wechseln) als zweite Schutzstufe.

### Figuren verwalten

- **Figuren-Wizard:** Neue Figur auflegen → aus der Bibliothek auswählen → fertig. Zuordnung ist sofort nutzbar.
- **Figur-Übersicht (Card Wall):** Alle Figuren als Bilder-Raster, Zuordnungen auf einen Blick.
- **Figur ändern:** Inhalt einer Figur später beliebig austauschen, ohne die Karte neu zu beschreiben.
- **Verhalten beim Abnehmen einstellbar:** Spielt weiter (für Figuren, die im Halter stecken) oder pausiert (für Karten, die beim Kippen runterfallen).

### Gesten-Steuerung (optional, mit Gyro-Sensor)

- **Kippen links/rechts** = nächster/vorheriger Titel.
- **Schütteln** = Shuffle.
- **Kippen vor/zurück** passt sich dem „Abnehmen"-Verhalten an: Entweder Lautstärke +/- oder Play/Pause + Stop.
- **Drei Empfindlichkeitsstufen** (sanft / normal / wild) für unterschiedlich bewegungsfreudige Kinder.

### Hardware-freundlich

- **Hardware-Wizard** erkennt automatisch, was angeschlossen ist — RFID-Reader, Audio-Ausgang, Gyro-Sensor, physische Tasten.
- **Physische Tasten** für Lautstärke / Play-Pause / Skip — einfach an die Box schrauben, Tonado lernt sie im Setup.
- **Ein- und Ausschalter** (mit OnOff SHIM): sauberes Hoch- und Herunterfahren per Taster, kein Stecker-Ziehen mehr.
- **Gute Klangqualität mit HifiBerry MiniAmp:** kleiner Verstärker-Aufsatz für den Pi, Lautsprecher direkt anschließbar.

### Updates und Sicherheit

- **Updates aus der App:** „Nach Updates suchen" in den System-Einstellungen, ein Klick, Box aktualisiert sich selbst.
- **Backup exportieren:** Alle Figur-Zuordnungen, Radio-Listen, Einstellungen als einzelne Datei herunterladen. Sicher aufbewahren.
- **Backup einspielen:** Bei einem Neuaufbau oder Umzug auf einen anderen Pi dieselbe Datei zurückspielen.
- **WLAN-Notfall:** Wenn das Heim-WLAN länger ausfällt, spannt die Box automatisch ein eigenes Setup-Netz auf, damit du sie wieder einrichten kannst, ohne den Pi auseinanderzubauen.

### Für unterwegs und offline

- **Komplett lokal:** Kein Abo, keine Cloud, kein Tracking. Die Musik bleibt bei dir.
- **App zum Homescreen:** Die Web-App lässt sich wie eine richtige App aufs Handy legen (PWA).
- **Offline nutzbar:** Lokale Musik-Dateien spielen auch ohne Internet. Nur Radio und Podcasts brauchen das WLAN.

## Was bald dazu kommt

Diese Features sind geplant, die nächsten Schritte Richtung Beta.

- **Einschlaftimer verlängern mit einem Tipp:** Wenn das Kind noch wach ist, Timer per „+5 Min"-Tipper im Player verlängern statt in die Einstellungen zu wechseln.
- **Sprachaufnahme direkt in der App:** Figur auflegen → aufnehmen — fertig. Besonders schön für eigene Gute-Nacht-Geschichten oder Grüße von Großeltern.
- **Offline-Modus als bewusste Einstellung:** Box komplett vom Internet trennen, Streaming-Features werden klar als „aus" markiert, lokale Musik läuft weiter.
- **WLAN in der App wechseln:** Neues WLAN hinzufügen, zwischen gespeicherten Netzen umschalten, ohne SSH oder Kabel.
- **Dateien von der Box herunterladen:** Wenn du Musik auf die Box geladen hast und sie auf dem Handy nicht mehr hast, ziehst du sie dir wieder runter.
- **Figur verloren ist kein Drama:** Neue Karte beschreiben, gleichen Inhalt zuordnen, weiter geht's.
- **Update mit Änderungsübersicht:** Vor der Installation siehst du in normaler Sprache, was neu ist, nicht nur kryptische Versions-Nummern.
- **Update-Rollback:** Wenn ein Update Probleme macht, kehrt die Box automatisch zur vorherigen Version zurück.
- **Offline-Update per USB-Stick:** Update-Paket auf einen USB-Stick ziehen, in die Box stecken — fertig. Praktisch, wenn die Box woanders steht als dein Computer.

## Was in Zukunft denkbar ist

Diese Ideen sammeln wir. Manche brauchen zusätzliche Hardware, manche mehr Entwicklungszeit, manche hängen an offenen Fragen.

- **Box-Name frei wählbar** — deine Box erreichbar unter z.B. `kinderzimmer.local`.
- **Farbthema** der App nach Lieblingsfarbe des Kindes einstellbar.
- **Fertiger Radio- und Podcast-Katalog** öffentlich-rechtlicher Kindersender — direkt in der App durchsuchen und hinzufügen.
- **Kategorien und Tags** für die Bibliothek — Einschlafen, Weihnachten, Lieblingshörbuch.
- **Gleicher Inhalt auf mehreren Figuren** — Lieblingshörbuch gibt's auf der Zimmer-Figur und auf der Auto-Figur.
- **Vollbackup inklusive Musik-Dateien** (nicht nur Konfiguration).
- **Tonado auf Englisch und weiteren Sprachen.**
- **Klopfen statt Kippen** als Alternative, falls Kippen zu kräftig für kleine Hände ist.
- **Startup-Sound** beim Einschalten, wenn gewünscht.
- **Kindersicherung für die physischen Tasten** — Lautstärke- oder Skip-Tasten per App deaktivieren.
- **Eltern-Dashboard** — was wurde heute gehört, wie lange.
- **Drag & Drop** in der Bibliothek, Batch-Upload ganzer Alben.
- **Mehrere Boxen in einer App** verwalten (Kinderzimmer und Wohnzimmer).
- **Box als AirPlay- oder Spotify-Connect-Empfänger** (nur als Abspielziel, nicht als eigener Player — die Kinder-Musikbox bleibt das Hauptziel).
- **Nachtlicht** über einen angeschlossenen LED-Ring.
- **Migration von Phoniebox** — bestehende Karten-Zuordnungen automatisch übernehmen.

## Was Tonado bewusst NICHT sein will

Damit die Box einfach bleibt, verzichten wir auf einige Dinge:

- **Kein Spotify-Player im Kinderzimmer.** Kein Streaming-Abo, kein Tracking.
- **Kein Smart-Home-Hub.** Tonado steuert keine Lampen, Rollläden oder Heizungen.
- **Keine Cloud-Pflicht.** Du kannst die Box komplett offline betreiben.
- **Keine laufenden Kosten** nach dem einmaligen Kauf der Hardware.

Diese Prinzipien stehen in der [Vision](../VISION.md).
