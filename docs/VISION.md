# Tonado — Produktvision

## Elevator Pitch

> Eine Musikbox für Kinder — sofort zu verstehen, auch für Kleinkinder bedienbar. Eltern steuern alles vom Smartphone. Open Source, selbst gebaut, für immer deins.

## Kernprinzip

```
Kind legt Figur oder Karte auf → Musik spielt sofort.
Eltern öffnen App → steuern alles vom Smartphone.
```

Alles andere ist Infrastruktur, die diese zwei Momente ermöglicht.

## Zielgruppe

### Primär: Technik-affine Eltern
- Haben einen Raspberry Pi oder trauen sich, einen zu kaufen
- Wollen eigene Hörbücher, Podcasts, Musik ohne Limits abspielen
- Schätzen Open Source und Datenschutz
- Wollen keine laufenden Kosten für Inhalte

### Sekundär: Datenschutz-bewusste Eltern
- Wollen keine Cloud-Abhängigkeit im Kinderzimmer
- Kein Tracking, kein Abo, keine Account-Pflicht
- DSGVO-sauber by Design

### Tertiär: Maker und Bastler
- Community, die Hardware-Erweiterungen baut
- 3D-Druck-Gehäuse, Custom-Buttons, LED-Integration
- Beiträge zur Software

## Positionierung

Tonado vereint das Beste aus zwei Welten: Die Einfachheit und das polierte Erlebnis kommerzieller Kinder-Musikboxen mit der Freiheit und Erweiterbarkeit eines Open-Source-Projekts. Kein Vendor-Lock-in, keine laufenden Kosten, volle Kontrolle.

## UX-Prinzipien

### 1. Kein Tutorial nötig
Das Interface erklärt sich selbst. Keine Overlay-Guides, keine "Tipp hier"-Popups. Wenn ein Element eine Erklärung braucht, ist das Element falsch designt.

### 2. Onboarding durch Tun
Wie ein Spiel, das Mechaniken durch kleine Aufgaben lehrt:
- "Leg eine Figur auf die Box." ✓
- "Wähle ein Hörbuch dafür aus." ✓
- "Fertig! Leg sie nochmal auf — hörst du?" ✓

Kein separater Tutorial-Modus. Das Setup IST das Lernen.

### 3. Progressive Disclosure
- **Player-Ansicht:** Nur Play/Pause, Volume, Cover Art. Sofort verstanden.
- **Eltern-Bereich:** Bibliothek, Figuren, Einstellungen. PIN-geschützt.
- **Experten-Bereich:** Hardware, System, Debug. Separate PIN.

Jeder sieht nur, was er braucht.

### 4. Fehler verzeihen
- Figur falsch zugewiesen? Ein Tipp zum Ändern.
- Upload abgebrochen? Wird beim nächsten Mal fortgesetzt.
- WiFi weg? Lokale Musik spielt weiter.

### 5. Mobile First
90% der Eltern-Interaktion passiert am Smartphone. Desktop ist nett, aber nicht die Priorität.

## Der "Wow"-Moment

Ein Elternteil erzählt einer Freundin:

> "Schau mal, mein Kind hat so eine Musikbox. Figur drauf, Musik läuft. Und ich kann hier auf dem Handy alles steuern — neue Hörbücher draufladen, Figuren zuweisen, Lautstärke begrenzen. Hat mich 70 Euro gekostet und keine laufenden Kosten. Kein Abo."

Die Freundin: *"Kann ich auch so eine haben?"*

Das ist der Moment. Dafür bauen wir.

## Was Tonado NICHT ist

- **Keine Kopie.** Wir lösen das gleiche Problem — besser und günstiger.
- **Kein Bastelprojekt.** Es soll sich anfühlen wie ein Produkt, nicht wie ein Hack.
- **Keine eierlegende Wollmilchsau.** Kein Spotify-Player, kein Smart-Home-Hub, kein Bluetooth-Speaker. Es ist eine Musikbox für Kinder.
- **Kein kommerzielles Produkt.** Open Source, Community-getrieben, MIT-Lizenz.

## Warum Tonado?

| Problem | Tonado |
|---------|--------|
| Teure Inhalte / laufende Kosten | Eigene MP3s, kein Abo |
| Cloud-Pflicht | Komplett offline möglich |
| Content-Limits | Unbegrenzt |
| Komplexes Setup | Hardware-Wizard im Browser |
| Nicht erweiterbar | GPIO, Gyro, Plugins |

## Zukunft

- Spotify Connect (Box als Receiver)
- BLE-Provisioning (Setup via App statt Captive Portal)
- 3D-Druck-Gehäuse-Vorlagen
- Community-Plugins (LED-Ring, Display, NFC-Figuren)
- Mehrsprachigkeit (Englisch, Französisch, ...)
