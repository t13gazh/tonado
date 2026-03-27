# Tonado — Produktvision

## Elevator Pitch

> Eine Musikbox für Kinder — sofort zu verstehen, auch für Kleinkinder bedienbar. Eltern steuern alles vom Smartphone. Open Source, selbst gebaut, für immer deins. Besser als die sauteure Musikbox.

## Kernprinzip

```
Kind legt Karte auf → Musik spielt sofort.
Eltern öffnen App → steuern alles vom Smartphone.
```

Alles andere ist Infrastruktur, die diese zwei Momente ermöglicht.

## Zielgruppe

### Primär: Technik-affine Eltern
- Haben einen Raspberry Pi oder trauen sich, einen zu kaufen
- Ärgern sich über Musikbox-Kosten (30 Figuren × 18 € = 540 €)
- Wollen eigene Hörbücher, Podcasts, Musik ohne Limits abspielen
- Schätzen Open Source und Datenschutz

### Sekundär: Datenschutz-bewusste Eltern
- Wollen keine Cloud-Abhängigkeit im Kinderzimmer
- Kein Tracking, kein Abo, keine Account-Pflicht
- DSGVO-sauber by Design

### Tertiär: Maker und Bastler
- Community, die Hardware-Erweiterungen baut
- 3D-Druck-Gehäuse, Custom-Buttons, LED-Integration
- Beiträge zur Software

## Wettbewerbs-Positionierung

```
          Einfachheit
              ▲
              │
   Musikbox ●─┤─────── Tonado (Ziel) ●
              │                        \
   andere Box ●     │                         \
              │                          \
   kommerzielle Box ● │                           \
              │                            ● DIY-Box
              │
   anderes DIY-Projekt ●  │
              │
   Vorgängerprojekt ●│
              │
              └─────────────────────────► Freiheit
```

**Tonado besetzt den Quadranten oben-rechts:** Hohe Einfachheit UND hohe Freiheit.

## UX-Prinzipien

### 1. Kein Tutorial nötig
Das Interface erklärt sich selbst. Keine Overlay-Guides, keine "Tipp hier"-Popups. Wenn ein Element eine Erklärung braucht, ist das Element falsch designt.

### 2. Onboarding durch Tun
Wie ein Spiel, das Mechaniken durch kleine Aufgaben lehrt:
- "Leg eine Karte auf den Reader." ✓
- "Wähle ein Hörbuch dafür aus." ✓
- "Die Karte ist fertig! Leg sie nochmal auf — hörst du?" ✓

Kein separater Tutorial-Modus. Das Setup IST das Lernen.

### 3. Progressive Disclosure
- **Player-Ansicht:** Nur Play/Pause, Volume, Cover Art. Sofort verstanden.
- **Eltern-Bereich:** Bibliothek, Karten, Einstellungen. PIN-geschützt.
- **Experten-Bereich:** Hardware, System, Debug. Separate PIN.

Jeder sieht nur, was er braucht.

### 4. Fehler verzeihen
- Karte falsch zugewiesen? Ein Tipp zum Ändern.
- Upload abgebrochen? Wird beim nächsten Mal fortgesetzt.
- WiFi weg? Lokale Musik spielt weiter.

### 5. Mobile First
90% der Eltern-Interaktion passiert am Smartphone. Desktop ist nett, aber nicht die Priorität.

## Der "Wow"-Moment

Ein Elternteil erzählt einer Freundin:

> "Schau mal, mein Kind hat so eine Musikbox. Karte drauf, Musik läuft. Und ich kann hier auf dem Handy alles steuern — neue Hörbücher draufladen, Karten zuweisen, Lautstärke begrenzen. Hat mich 70 Euro gekostet, nicht 500 wie bei der Musikbox. Und kein Abo."

Die Freundin: *"Kann ich auch so eine haben?"*

Das ist der Moment. Dafür bauen wir.

## Was Tonado NICHT ist

- **Keine Musikbox-Kopie.** Wir kopieren nicht das Design, wir lösen das gleiche Problem besser.
- **Kein Bastelprojekt.** Es soll sich anfühlen wie ein Produkt, nicht wie ein Hack.
- **Keine eierlegende Wollmilchsau.** Kein Spotify-Player, kein Smart-Home-Hub, kein Bluetooth-Speaker. Es ist eine Musikbox für Kinder.
- **Kein kommerzielles Produkt.** Open Source, Community-getrieben, MIT-Lizenz.

## Marktlücke

| Problem | Wer hat es | Tonado löst es |
|---------|-----------|----------------|
| Teuer auf Dauer | Musikbox (Figuren), kommerzielle Box (Abo) | Eigene MP3s, kein Abo |
| Cloud-Pflicht | Musikbox, kommerzielle Box, andere Box | Komplett offline möglich |
| Content-Limits | Musikbox (90 Min/Kreativ-Figur) | Unbegrenzt |
| Komplexes Setup | Vorgängerprojekt (SSH, Terminal) | Hardware-Wizard im Browser |
| Veraltetes UI | Vorgängerprojekt (jQuery 1.12) | Svelte 5, Mobile-First |
| Nicht erweiterbar | Alle kommerziellen | GPIO, Gyro, Plugins |

## Phase 2+ (Zukunft, nicht jetzt)

- Spotify Connect (Box als Receiver)
- TeddyCloud/TAF-Kompatibilität (Musikbox-Umsteiger)
- BLE-Provisioning (Setup via App statt Captive Portal)
- 3D-Druck-Gehäuse-Vorlagen
- Community-Plugins (LED-Ring, Display, NFC-Figuren)
- Mehrsprachigkeit (Englisch, Französisch, ...)
