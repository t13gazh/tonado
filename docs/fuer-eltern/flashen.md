# Tonado auf eine SD-Karte spielen

Du hast einen Raspberry Pi und eine leere SD-Karte und möchtest Tonado das erste Mal aufspielen? Das ist einfacher, als es klingt. Du überträgst dafür eine fertige Tonado-Datei auf die SD-Karte und startest die Box danach einmal — den Rest erledigt die Box selbst. Plane etwa eine Viertelstunde ein, das meiste davon ist Warten.

## 1. Was du brauchst

- Eine **SD-Karte** mit mindestens 8 GB. Alles, was vorher darauf war, wird gelöscht.
- Einen **SD-Kartenleser** an deinem Computer (viele Laptops haben einen eingebaut, sonst tut ein kleiner USB-Adapter).
- Den **Raspberry Pi** deiner Box — also die kleine Platine, die später in der Box steckt.
- Die **Tonado-Datei** zum Aufspielen. Sie heißt ungefähr `tonado-...-.img.xz` und du lädst sie von der Veröffentlichungs-Seite des Projekts herunter (siehe nächster Schritt).
- Das kostenlose Programm **„Raspberry Pi Imager"** auf deinem Computer. Es überträgt die Datei auf die SD-Karte. Du findest es unter [raspberrypi.com/software](https://www.raspberrypi.com/software/) für Windows, Mac und Linux.

## 2. Die Tonado-Datei herunterladen

1. Öffne die **Veröffentlichungs-Seite** von Tonado: [github.com/t13gazh/tonado/releases](https://github.com/t13gazh/tonado/releases).
2. Lade die Datei herunter, die zu deiner Box passt. Es gibt zwei Varianten:
   - eine für **neuere, schnellere** Raspberry Pis,
   - eine für den **kleinen, sparsamen** Raspberry Pi Zero W.

   Im Zweifel die Variante für dein eigenes Modell — auf der Platine steht meist, welcher Pi es ist.
3. Lege die heruntergeladene Datei `tonado-...-.img.xz` an einen Ort, den du wiederfindest (z.B. den Download-Ordner). Du musst sie **nicht** entpacken.

Falls auf der Seite eine kleine Prüfsumme angegeben ist, kannst du sie vergleichen — nötig ist das nicht, der „Raspberry Pi Imager" prüft die Datei beim Schreiben selbst.

## 3. Auf die SD-Karte spielen

1. Stecke die SD-Karte in den Kartenleser an deinem Computer.
2. Öffne den **„Raspberry Pi Imager"**.
3. Beim Betriebssystem ganz nach unten gehen und **„Eigenes Image wählen"** (englisch: „Use custom") antippen. Dann die heruntergeladene Datei `tonado-...-.img.xz` auswählen.
4. Als Ziel deine **SD-Karte** auswählen. Schau genau hin, dass es wirklich die SD-Karte ist und nicht versehentlich eine andere Festplatte.
5. **Wichtig — den Einrichtungs-Dialog gibt es hier nicht.** Bei einem eigenen Tonado-Image zeigt der Imager **keinen** Fragebogen für Benutzername, Passwort oder WLAN. Diesen Dialog kennst du vielleicht von den offiziellen Raspberry-Pi-Systemen — bei Tonado fehlt er **mit Absicht**. Du richtest Tonado später bequem über die App ein, nicht hier. Falls der Imager trotzdem fragt, ob er Einstellungen anpassen soll, wähle **„Nein, Einstellungen nicht anpassen"**.
6. Auf **Schreiben** tippen und bestätigen, dass die SD-Karte komplett überschrieben wird.
7. Warten, bis der Imager „fertig" meldet. Das dauert je nach Karte einige Minuten. Danach kannst du die SD-Karte auswerfen und herausnehmen.

## 4. Die Box zum ersten Mal starten

1. Stecke die fertige SD-Karte in den Raspberry Pi.
2. Schließe den Strom an.
3. Beim **allerersten Start** richtet sich die Box ein paar Minuten lang selbst ein — rechne mit ein bis zwei Minuten. Es kann sein, dass sie sich dabei einmal von selbst neu startet. Das ist normal, einfach abwarten.

Du hörst keinen Startton und siehst höchstens eine kleine Leuchte. Sobald die Box bereit ist, geht es am Handy weiter.

## 5. Mit dem Tonado-WLAN verbinden

Beim ersten Mal kennt die Box dein Heim-WLAN noch nicht. Darum spannt sie ein eigenes, kleines WLAN auf, über das du ihr alles Weitere mitteilst.

1. Öffne am Handy die **WLAN-Liste**.
2. Wähle das Netz **„Tonado-Setup"** aus.
3. Es ist **offen — kein Passwort nötig**. Das ist Absicht: Du hast ja noch keine Zugangsdaten, und gleich im Assistenten vergibst du selbst eine PIN.

**„Kein Internet"? Keine Sorge — das ist richtig so.**
Sobald du mit „Tonado-Setup" verbunden bist, warnt dein Handy meist: „Dieses WLAN hat keinen Internetzugang" und fragt, ob die Verbindung gehalten werden soll. Antworte mit **„Ja"** bzw. **„Verbindung behalten"** (bei Android). Auf dem iPhone tippe gegebenenfalls auf die entsprechende Benachrichtigung. Das ist völlig normal — die Box ist kein Internet-Router, sie öffnet nur ihre eigene Einrichtungs-Seite. In aller Regel öffnet sich die Tonado-Einrichtung danach von selbst im Browser. Falls nicht: Browser öffnen und `http://192.168.4.1` eingeben (mit `http`, **nicht** `https`).

## 6. Der Einrichtungs-Assistent

Jetzt führt dich die Box Schritt für Schritt durch die Einrichtung. Sie fragt dich nach:

- **Deinem Heim-WLAN** — du wählst es aus der Liste und gibst das Passwort ein.
- **Dem Audio-Ausgang** — also wo der Ton herauskommt.
- **Einer Eltern-PIN** — vier Ziffern, mit denen du später die Einstellungen schützt.
- **Einem Notfall-WLAN** — ein Netzwerkname und ein Passwort, das die Box später selbst aufspannt, falls sie dein Heim-WLAN einmal nicht findet. **Schreib dir beides gut auf** (z.B. an den Kühlschrank) — du brauchst es nur im Notfall, dann aber sofort griffbereit.

Am Ende wechselt die Box von ihrem eigenen WLAN in dein Heim-WLAN. **Verbinde dann auch dein Handy wieder mit dem Heim-WLAN** — die Einrichtungs-Seite findet die Box danach von selbst wieder. Ein angezeigter QR-Code hilft dir, die Box jederzeit schnell aufzurufen.

Mehr zu den ersten Schritten mit der fertig eingerichteten Box findest du unter **[Erste Schritte](ERSTE-SCHRITTE.md)**.

## Klappt nicht?

**Das WLAN „Tonado-Setup" taucht nicht auf.**
Warte ein bis zwei Minuten länger und aktualisiere die WLAN-Liste am Handy. Hilft das nicht: Stecker kurz ziehen, wieder anschließen und erneut versuchen.

**Die Einrichtungs-Seite öffnet sich nicht von selbst.**
Öffne den Browser am Handy und gib `http://192.168.4.1` ein (mit `http`, nicht `https`).

Weitere Antworten findest du in den **[Häufigen Fragen](FAQ.md)**.
