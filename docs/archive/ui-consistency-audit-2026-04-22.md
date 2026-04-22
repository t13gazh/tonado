# UI-Konsistenz-Audit — Tonado Frontend

- Datum: 2026-04-22
- Auditor: Code-Analyzer-Agent (Claude Opus 4.7)
- Scope: `web/src/**` — Settings, Setup-Wizard, Figuren-Management, Library, Player, Layout, Design-Tokens
- Grundlagen: Nielsen 10 Heuristiken, Krug „Don't Make Me Think", Refactoring UI (Wathan/Schoger), UI/UX-Pro-Max (Token-Systeme)
- Modus: Read-only. Keine Code-Änderungen.

---

## Inhaltsverzeichnis

1. [Executive Summary (am Ende)](#executive-summary-für-user)
2. [Phase A — Inventar](#phase-a--inventar)
   - A.1 Design-Tokens
   - A.2 Button-Primitiven
   - A.3 Segment-/Chip-/Toggle-Group-Varianten
   - A.4 Boolean-Toggles (An/Aus)
   - A.5 Input-/Textfeld-Varianten
   - A.6 Settings-Row-Layouts
   - A.7 Error-/Feedback-Darstellungen
   - A.8 Card-Container / Section-Wrapper
3. [Phase B — Findings](#phase-b--findings-nach-severity)
4. [Phase C — Design-System-Spec](#phase-c--vorgeschlagenes-design-system)
5. [Executive Summary](#executive-summary-für-user)

---

## Phase A — Inventar

### A.1 Design-Tokens (`web/src/app.css`)

| Token | Wert | Nutzung | Bewertung |
|---|---|---|---|
| `--color-primary` | `#6366f1` | überall für Primary-Actions | konsistent |
| `--color-primary-light` | `#818cf8` | Hover | konsistent |
| `--color-primary-dark` | `#4f46e5` | **ungenutzt** | toter Token |
| `--color-surface` | `#1e1e2e` | Page-Background | konsistent |
| `--color-surface-light` | `#2a2a3e` | Card-Hintergrund | konsistent |
| `--color-surface-lighter` | `#363650` | Card-darin / Border | konsistent |
| `--color-text` | `#e2e2f0` | Body-Text | konsistent |
| `--color-text-muted` | `#a0a0b8` | Label, Meta | konsistent |
| `--color-accent` | `#f59e0b` | Sleep aktiv, „Update verfügbar" | konsistent |

Keine Spacing-/Radius-/Shadow-/Type-Tokens definiert — alles kommt aus Tailwind-Defaults. Heißt: die Spacing-Skala ist konsistent, aber **es gibt keine Tonado-eigene Skala**, die irgendwo dokumentiert oder geprüft werden könnte. Ergebnis: im Code koexistieren `rounded-lg`, `rounded-xl`, `rounded-2xl`, `rounded-full` nebeneinander ohne Regel (245 Treffer über 30 Dateien).

Semantische Farben für Status (green-500 „connected", red-500 „fehler", amber-500 „warn", accent „update") sind **inline verstreut**, kein Alias-Token.

**Befund:** Tokens existieren nur für Markenfarbe + Surface-Hierarchie. Alle Radius/Shadow/Spacing/Type/Status-Entscheidungen sind pro Komponente neu getroffen worden.

### A.2 Button-Primitiven

Ich habe fünf faktische Button-Rezepte im Codebase gefunden — ohne dass eine davon als Komponente existiert:

| Variante | Klassen-Pattern | Typischer Einsatz | Fundstellen (Beispiele) |
|---|---|---|---|
| **Primary XL** (CTA) | `py-3 bg-primary hover:bg-primary-light text-white rounded-lg font-medium transition-colors` | Setup-Wizard „Weiter", Login-Sheet „Anmelden" | `setup/+page.svelte:334,347,359,391,415,431,465,482,494`, `LoginSheet.svelte:94` |
| **Primary M** (Detail-Action) | `px-4 py-2.5 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors` | System-Seite: Update, Backup, Neustart | `settings/system/+page.svelte:301,325,341,358,374,406,418,425`, `cards/+page.svelte:274`, `GyroCalibration.svelte` |
| **Primary S** (Inline) | `px-4 py-2 bg-primary text-white rounded-lg text-sm` | Settings „Anmelden", „Sleep starten", „PIN setzen" | `settings/+page.svelte:336,368,556,589`, `FolderTab.svelte:403` |
| **Secondary** (Surface-Light) | `py-3 px-5 bg-surface-light hover:bg-surface-lighter text-text-muted rounded-lg text-sm font-medium transition-colors` | „Zurück", „Abbrechen" im Wizard | `setup/+page.svelte` (x15) |
| **Destructive** (Red-Tint) | `px-4 py-2 bg-red-500/20 text-red-400 rounded-lg text-sm hover:bg-red-500/30` | PIN entfernen | `settings/+page.svelte:566,596`, `settings/system/+page.svelte:441` |
| **Destructive solid** | `bg-red-600 hover:bg-red-500 rounded-lg text-white text-sm font-medium` | Herunterfahren bestätigen, Löschen bestätigen | `settings/system/+page.svelte:433`, `cards/+page.svelte:308` |
| **Ghost/Link** | `text-sm text-text-muted hover:text-text` | „Abmelden", „Formular schließen" | `settings/+page.svelte:350`, `FolderTab.svelte:395` |
| **Icon-only** | `p-2 text-text-muted hover:text-text` | Back-Chevron, Menü-Schließen, Chevron-Expand | `settings/system/+page.svelte:163`, `ContentPicker.svelte:155,229` |

Außerdem existieren **3 inkonsistente Größen für denselben primären Zweck**: `py-3`, `py-2.5`, `py-2`. Die Wahl folgt keinem Muster (Wizard: py-3, System: py-2.5, Settings-Inline: py-2 — aber auch Settings hat py-2.5 in der QR-Spalte). Das sind **3 Button-Höhen im selben visuellen Frame**.

### A.3 Segment-/Chip-/Toggle-Group-Varianten

Dies ist der **Hauptschauplatz der Inkonsistenz**. Mindestens **fünf** unterschiedliche Behandlungen desselben Interaktionsmusters (eine-aus-N) existieren:

| Variante | Pattern | Fundstelle | Besonderheit |
|---|---|---|---|
| **V1 — Segment mit Ring-Highlight** | `flex-1 px-2 py-1.5 rounded-lg text-xs font-medium` + bei aktiv: `ring-2 ring-primary ring-offset-2 ring-offset-surface-light` | `settings/+page.svelte:525-533` (WLAN-Rettung-Intervalle 2/5/10/20 Min) | Der **einzige** Ort mit Ring-Offset, optisch deutlich von allen anderen abweichend |
| **V2 — Chip ohne Ring** | `flex-1 px-3 py-2 rounded-lg text-sm transition-colors` + `bg-primary text-white` vs `bg-surface text-text-muted` | `settings/+page.svelte:406-416` (Figur wegnehmen: Pause/Weiter), `:438-444` (Gyro sanft/normal/wild) | Inline-Ternary ohne Snippet — dreimal dasselbe Klassen-Konstrukt an drei Zeilen |
| **V3 — Segmented-Control mit Container** | Wrapper `grid grid-cols-3 rounded-lg bg-surface-light p-0.5`, Kinder `min-h-11 rounded-md text-xs font-medium` | `library/FolderTab.svelte:377-393` (Sortierung alpha/recent/duration), ebenso RadioTab/PodcastTab/PlaylistTab | Klar die **sauberste** Variante; voll a11y-konform mit `role=radiogroup`, Arrow-Key-Navigation, roving tabindex |
| **V4 — Tab-Pills in Flex-Row** | `px-3 py-1.5 text-xs font-medium rounded-full` + `bg-primary text-white` vs `bg-surface-light text-text-muted` | `library/+page.svelte:145-153` (Ordner/Radio/Podcasts/Playlisten) | rounded-full statt rounded-lg — bewusste Abgrenzung als Tab, aber der Sprung zu anderen Segmenten ist optisch groß |
| **V5 — Icon+Label-Chips** | `flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium` | `ContentPicker.svelte:118-128` (Ordner/Radio/Podcast/Playlist/Kommando im Wizard) | Eigene Variante — Icon links, kleineres Padding |
| **V6 — Content-Type-Tabs im Wizard (andere Instanz)** | siehe V5 | `ContentPicker.svelte` | Überschneidet sich mit V4 semantisch (Inhalt-Filter), sieht aber anders aus |
| **V7 — Einfache Select** (`<select>`) | `w-full px-3 py-2 bg-surface border border-surface-lighter rounded-lg` | `settings/+page.svelte:613-622` (Idle-Abschaltung aus/15/30/60 Min) | Native HTML-Dropdown statt Segmented — **einziger Ort**, obwohl semantisch identisch zu WLAN-Rettung |

**Zusatz — Radio-List (auch „eine-aus-N"):**

| Variante | Pattern | Fundstelle |
|---|---|---|
| **V8 — Card-List mit Radio-Circle** | `bg-surface-light rounded-xl p-4 flex items-center gap-3` + 5×5 border-circle links | `setup/AudioStep.svelte:77-92` (Audio-Ausgang) |
| **V9 — Plain List mit Background-Tint** | `px-4 py-3 flex items-center justify-between` + `bg-primary/10` wenn ausgewählt | `setup/WifiStep.svelte:76-93` (WLAN-Netzwerk-Auswahl) |

→ **Für eine Auswahl aus einer Menge gibt es im Projekt 9 verschiedene visuelle Sprachen.**

### A.4 Boolean-Toggles (An/Aus)

Drei verschiedene Muster für dieselbe Semantik (einzelne boolesche Einstellung):

| Variante | Pattern | Fundstelle |
|---|---|---|
| **T1 — iOS-Style-Switch** | `<label class="relative inline-flex items-center cursor-pointer"><input type="checkbox" class="sr-only peer">…peer-checked:after:translate-x-full…` | `settings/+page.svelte:454-462` (WLAN-Rettung An/Aus) |
| **T2 — Chip-Button mit Zustandstext** | `px-3 py-1 rounded-full text-xs font-medium` mit Text „Aktiviert" / „Deaktiviert" | `settings/+page.svelte:427-432` (Bewegungssteuerung), `:631-636` (Expertenmodus) |
| **T3 — HTML-Checkbox mit Label** | `<label class="flex items-center gap-3"><input type="checkbox" class="w-4 h-4 rounded accent-primary">` | `setup/ButtonsStep.svelte:150-158` (Tasten auswählen, Mehrfachauswahl — streng genommen nicht Boolean-Toggle, aber Checkbox-Pattern gibt's nur hier) |

Die Toggle-Texte unterscheiden sich zusätzlich: „Aktiviert/Deaktiviert" (Bewegung), „An/Aus" (Experte), kein Text (WLAN, weil Schalter sich selbst erklärt). **Dasselbe Feature-Verhalten wird drei Mal anders präsentiert.**

### A.5 Input-/Textfeld-Varianten

| Variante | Pattern | Fundstelle |
|---|---|---|
| **I1 — Standard-Input** | `px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary` | `settings/+page.svelte:333,366,552,583` (Login-PIN, Sleep-Minuten, PIN setzen) |
| **I2 — Input mit höherem Padding** | `px-3 py-2.5 bg-surface border …` | `setup/WifiStep.svelte:103` (WLAN-Passwort), `cards/+page.svelte:250` (Figur umbenennen), `setup/CardStep.svelte:144` (Inhaltsname) |
| **I3 — Input auf Surface-Light-Background** | `bg-surface-light border border-surface-lighter` | `ContentPicker.svelte:311` (Experten-Pfad), `setup/CardStep.svelte:144` |
| **I4 — PIN-OTP-Cells** | `w-14 h-16 text-center text-2xl font-semibold … border-2 border-surface-lighter rounded-xl` | `setup/PinStep.svelte:226,259,293,321` — eigenes, durchgängiges System innerhalb PIN-Step |
| **I5 — Passwort-Input mit Eye-Toggle** | I2 + `pr-10` + absolut positionierter Button | `setup/WifiStep.svelte:101-110` — **einziger** Ort mit sichtbarer/verdeckter Passwort-Umschaltung. PIN-Login-Sheet und Settings-Login haben den **nicht**. |

**Befund:** Padding `py-2` vs `py-2.5` verteilt sich willkürlich. Die Eye-Toggle-Ergonomie nur an einer Stelle ist ein klares Inkonsistenz-Signal.

### A.6 Settings-Row-Layouts

Mindestens **vier** verschiedene Layout-Sprachen für „Einstellung mit Label + Control":

| Layout | Struktur | Fundstelle |
|---|---|---|
| **L1 — Label oben, Control voll** | `<h2 class="text-sm font-semibold mb-3">Label</h2>` + Control darunter | `settings/+page.svelte:357,376,403,612` (Sleep, Volume, Figur wegnehmen, Idle-Abschaltung) |
| **L2 — Label + Toggle rechts (justify-between)** | `<div class="flex items-center justify-between mb-3"><h2>…</h2><Toggle/></div>` + Description darunter | `settings/+page.svelte:425-432,452-462`, `settings/system/+page.svelte:395-402` (Gyro, WLAN-Rettung, Gyro-Kalibrierung) |
| **L3 — Label + Description-Stack + Toggle rechts** | `<div class="flex items-center justify-between"><div><h2>…</h2><p class="text-xs text-text-muted mt-0.5">…</p></div><Toggle/></div>` | `settings/+page.svelte:626-637` (Expertenmodus), `settings/system/+page.svelte:394-403` |
| **L4 — Grid-Liste** (Metadaten) | `grid grid-cols-2 gap-y-2 text-sm` + abwechselnd `text-text-muted`/`text-text` | `settings/system/+page.svelte:184-201` (System-Info) |

Description-Position ist besonders inkonsistent: mal **vor** dem Control (`settings/+page.svelte:464`), mal **nach** dem Control, mal **neben** der Überschrift, mal **gar nicht vorhanden** bei Einstellungen, die sie eigentlich brauchen (z.B. „Sleep-Timer" erklärt nicht, was passiert, aber „WLAN-Rettung" tut's).

### A.7 Error-/Feedback-Darstellungen

| Variante | Pattern | Fundstelle |
|---|---|---|
| **E1 — HealthBanner** (strukturiert) | `<HealthBanner type="warning\|error\|info">` — icon + message, farbcodiert | genutzt in `setup/`, `library/+page.svelte`, `cards/+page.svelte`, `settings/+page.svelte` |
| **E2 — InlineError** (strukturiert) | `<InlineError message=>` — `role=alert`, icon, red-tint | genutzt in `setup/PinStep.svelte` |
| **E3 — Inline text-red-400** | `<p class="text-sm text-red-400">{error}</p>` oder `text-xs text-red-400 mt-2` | überall verstreut: `settings/+page.svelte:321,342`, alle `setup/*Step.svelte`, `cards/+page.svelte:164`, `library/+page.svelte:159` |
| **E4 — Inline red mit X-Close** | `p-3 bg-red-400/10 rounded-lg` + X-Button | nur `library/+page.svelte:158-163` |
| **E5 — Toast** | `addToast(msg, 'error'\|'success'\|'info')` — global, oben rechts | Settings, Library-Tabs, Player |
| **E6 — Amber-500-Hinweis** (nicht-Fehler) | `text-xs text-amber-500` | `settings/system/+page.svelte:378` (Experten-Tier nötig) |

Drei komplett unterschiedliche Wege, denselben Fehler zu zeigen (E2/E3/E4), mit identischer Informationsdichte aber abweichender Ergonomie. Die Frage „Bleibt der Fehler stehen oder verschwindet er?" ist **pro Seite anders beantwortet**.

### A.8 Card-Container / Section-Wrapper

`bg-surface-light rounded-xl p-4` ist das faktische Pattern für Settings-Gruppen (21 Treffer), konsistent angewendet — **einer der wenigen Lichtblicke**. Aber:

- Modals benutzen `bg-surface-light … rounded-t-2xl sm:rounded-2xl p-5` — anderer Radius, anderes Padding.
- HelpSheet, LoginSheet, Edit-Card-Modal, Delete-Confirmation-Modal — jedes hat eigene Overlay/Sheet-Container (immerhin alle über `fixed inset-0 bg-black/60`).

### A.9 Zahlen

- 42 Button-Instanzen mit `bg-primary text-white rounded`-Pattern über 14 Files, keine wiederverwendbare Komponente.
- 21 Card-Instanzen mit `bg-surface-light rounded-xl p-4` über 6 Files, keine wiederverwendbare Komponente.
- 245 Radius-Tokens (`rounded-lg/xl/full/2xl/md`) verteilt — keine Regel, welche wann.

---

## Phase B — Findings (nach Severity)

### F-01 — Drei verschiedene Toggle-Darstellungen für dieselbe Boolean-Semantik [SEVERITY 3]

**Heuristik/Prinzip:** Nielsen 4 (Consistency and Standards); Refactoring UI „constrained scales"; Krug (ein Pattern = ein Aussehen).

**Betroffene Stellen:**
- `web/src/routes/settings/+page.svelte:454-462` — iOS-Switch für WLAN-Rettung
- `web/src/routes/settings/+page.svelte:427-432` — Chip-Button „Aktiviert/Deaktiviert" für Gyro
- `web/src/routes/settings/+page.svelte:631-636` — Chip-Button „An/Aus" für Expertenmodus
- `web/src/routes/settings/system/+page.svelte:395-408` — der Kalibrierungs-Bereich ist zwar kein Toggle, wiederholt aber das L3-Layout inkonsistent

**Warum es Nutzer verwirrt:** Der Elternteil muss pro Einstellung lernen, **wie** er sie ein-/ausschaltet: einmal Schieber, einmal Button-das-den-Zustand-ansagt, einmal Button-das-den-Zustand-ansagt-aber-anderes-Vokabular. Das bricht Nielsens Regel „same widget = same meaning" und führt zu 2–3 Sekunden Zögern pro Begegnung. Beim ersten Sehen ist unklar, ob der Chip-Button der aktuelle Zustand oder die nächste Aktion ist ("Aktiviert" — ist es aktiv oder aktiviere ich damit?).

**Fix-Empfehlung:** Ein kanonischer iOS-Switch für jedes An/Aus. Der Switch aus `settings/+page.svelte:454-462` ist bereits sauber umgesetzt — als gemeinsame Komponente extrahieren, die beiden Chip-Button-Toggles ersetzen. Zusätzlich die Label+Description+Toggle-Zeile standardisieren.

**Fix-Aufwand:** S (2–3 Stunden inkl. Komponente bauen + drei Call-Sites anpassen + Screenshot-Test).

---

### F-02 — Neun visuelle Sprachen für „Auswahl aus N" [SEVERITY 3]

**Heuristik/Prinzip:** Nielsen 4 (Consistency); Refactoring UI „constrained scales"; Krug „Don't Make Me Think".

**Betroffene Stellen:**
- `settings/+page.svelte:525-533` (V1 Ring-Offset — WLAN-Rettung-Intervalle)
- `settings/+page.svelte:406-416`, `:438-444` (V2 Chip ohne Ring — Figur wegnehmen, Gyro-Stärke)
- `library/FolderTab.svelte:377-393` + Schwester-Tabs (V3 Segmented-Control mit Container — saubere Variante)
- `library/+page.svelte:145-153` (V4 Rounded-Full-Pills — Library-Tabs)
- `ContentPicker.svelte:118-128` (V5 Icon-Chips — Inhalt-Typ-Filter)
- `settings/+page.svelte:613-622` (V7 Native `<select>` — Idle-Abschaltung)
- `setup/AudioStep.svelte:77-92` (V8 Radio-Card-List — Audio-Ausgang)
- `setup/WifiStep.svelte:76-93` (V9 Liste mit Tint — WLAN-Netzwerk)

**Warum es Nutzer verwirrt:** Der vom User berichtete Effekt („3 Stile auf einer Settings-Seite") ist ein Symptom — die Ursache ist, dass identische Interaktion (genau ein Wert aus 3–5 Optionen picken) neunmal visuell anders codiert ist. Der Benutzer muss für jede Variante neu entschlüsseln, ob sie anklickbar ist, welche aktiv ist, ob sie anders reagieren. Das ist besonders in Settings und WLAN-Rettung kritisch, weil diese Seiten oft besucht werden (Lautstärke, Timer).

**Fix-Empfehlung:** EINE kanonische `<SegmentSelect options bind:value>`-Komponente basierend auf Variante V3 (FolderTab). V3 hat bereits `role=radiogroup`, Arrow-Keyboard-Navigation (via `handleRadioKeydown`), `min-h-11` Touch-Target, sauberen Container-Style. Post-Beta-Migration:
- Idle-Abschaltung (V7 `<select>`) → SegmentSelect
- WLAN-Rettung-Intervalle (V1 Ring) → SegmentSelect
- Gyro-Stärke (V2) → SegmentSelect
- Figur-wegnehmen (V2) → SegmentSelect
- Library-Tabs (V4) bleiben als Tab-Pills — das ist semantisch Navigation, nicht Settings-Wert (richtige Unterscheidung beibehalten).
- Content-Typ-Picker (V5) bleibt ebenfalls, weil Icons die Unterscheidung tragen — aber technisch gleichen Container-Style verwenden.
- Audio-Ausgang (V8) und WLAN-Liste (V9) bleiben als Radio-List, weil Items Rich-Content haben (Badge, Signalstärke) — aber einheitliches Selected-Pattern.

**Fix-Aufwand:** M (halber Tag für die Komponente, nochmal einen halben Tag für die Migrations + Tests).

**Beta-Must (Minimal-Subset von F-02):** Den einen besonders auffälligen Stilbruch fixen: WLAN-Rettung-Intervalle (V1 Ring-Offset) an Gyro-Stärke (V2 kein Ring) angleichen. Beides auf dieselbe Einstellungsseite, beides selbe Semantik — einfach das `ring-2 ring-primary ring-offset-2 ring-offset-surface-light` entfernen. 15 Minuten.

---

### F-03 — Primary-Button in drei Höhen [SEVERITY 2]

**Heuristik/Prinzip:** Nielsen 4 (Consistency); Refactoring UI „constrained scales".

**Betroffene Stellen:** (42 Instanzen, hier Beispiele pro Größe)
- `py-3` (Wizard-Stil): `setup/+page.svelte:334,347,415`, `LoginSheet.svelte:94`
- `py-2.5`: `settings/system/+page.svelte:301,325,341,374`
- `py-2`: `settings/+page.svelte:336,368,556,589`, `FolderTab.svelte:403`

**Warum es Nutzer verwirrt:** Der Größensprung zwischen „Login"-Button (py-2, klein) und „Sleep starten" (py-2) vs. „Update installieren" (py-2.5) vs. „Weiter im Wizard" (py-3) ist sichtbar und fühlt sich willkürlich an. Auf dem Pi-Touchscreen wird py-2 bei ~40px hoch — unter dem 44px-Minimum für Touch-Targets (WCAG 2.5.5 / iOS HIG).

**Fix-Empfehlung:** Drei definierte Sizes `sm=py-2` (Inline-Actions in Listen), `md=py-2.5` (Page-Actions), `lg=py-3` (Primary CTA im Wizard + Submit in Modals). Regel: **Alle Settings-Gruppen-Actions verwenden `md`**. Dadurch ist PIN-Login in Settings dieselbe Höhe wie Update-Check — momentan ist sie kleiner.

**Fix-Aufwand:** S (1–2 Stunden, eine `<Button>`-Komponente + Migration der Settings-Inline-Aktionen).

---

### F-04 — Inkonsistente Fehler-Darstellung: 6 verschiedene Muster [SEVERITY 2]

**Heuristik/Prinzip:** Nielsen 9 (Help users recognize/diagnose/recover from errors); Krug „Don't Make Me Think".

**Betroffene Stellen:**
- `<HealthBanner>` (gut) vs. `<InlineError>` (gut) vs. plain `<p class="text-sm text-red-400">` (roh) vs. `<p class="text-xs text-red-400 mt-2">` (roh) vs. `text-xs text-amber-500` (Warnung) vs. Toast
- PinStep nutzt InlineError sauber. Settings-Seite nutzt plain `text-sm text-red-400` (`:321,342`). Setup-Wizard mischt plain und HealthBanner.

**Warum es Nutzer verwirrt:** Ein Fehler ist mal eine rote Banner-Box, mal ein rotes Textzeilchen, mal ein Toast der nach 3s weg ist. Der Nutzer lernt nicht „rote Meldung = Aktion nötig", weil die Darstellung wechselt. Der `text-xs`-Inline-Fehler wird auf dem kleinen Display leicht übersehen (14px ohne Border, ohne Icon).

**Fix-Empfehlung:**
- **Banner/Blockierend** (z.B. „Backend offline", „WLAN nicht verfügbar"): `<HealthBanner>` wie heute.
- **Feld-lokal** (z.B. „PIN zu kurz", „Passwort falsch"): `<InlineError>` — dieses Pattern auf alle Formulare ausrollen, plain `<p class="text-sm text-red-400">` abschaffen.
- **Ephemer** (z.B. „Gespeichert", „Upload fehlgeschlagen"): Toast.
Regel: Jede neue Fehlerausgabe muss sich für genau eine der drei Kategorien entscheiden.

**Fix-Aufwand:** S (2 Stunden — plain-Fehler durch `<InlineError>` ersetzen, sonst nichts verändern).

---

### F-05 — Login/PIN-Input ohne Eye-Toggle, nur WLAN-Passwort hat einen [SEVERITY 2]

**Heuristik/Prinzip:** Nielsen 7 (Flexibility and efficiency of use); Krug (Konsistenz).

**Betroffene Stellen:**
- `setup/WifiStep.svelte:101-110` — WLAN-Passwort MIT Eye-Toggle
- `settings/+page.svelte:329-334` (Login), `:548-553` (Parent-PIN), `:578-584` (Expert-PIN), `LoginSheet.svelte:76-85` — OHNE Eye-Toggle

**Warum es Nutzer verwirrt:** Der Nutzer hat an einer Stelle gelernt, dass er prüfen kann, was er getippt hat — und an der anderen nicht. Bei 4-stelligen PINs ist das Risiko, ohne Feedback einzutippen, hoch (Tippfehler → wrong-pin-Error → Shake → neu tippen). Die PIN-OTP-Zellen im Setup-Wizard (PinStep) lösen das über sichtbare Cells (Typ=password mit ein Zeichen pro Cell, Feedback durch Focus-Pulse), aber der **Login im Settings-Screen nutzt ein einzelnes Password-Feld ohne diese Eleganz**.

**Fix-Empfehlung:** PIN-Login im Settings und im LoginSheet auf dasselbe OTP-Zellen-Muster aus `PinStep.svelte` umstellen. Das ist semantisch konsistent (überall PIN = Cells) und entfernt die Notwendigkeit eines Eye-Toggles für PIN. WLAN-Passwort bleibt wie heute (freies Feld + Eye ist dort richtig).

**Fix-Aufwand:** M (halber Tag — Extrahieren der PIN-OTP-Cells aus PinStep in `<PinEntry>` Komponente, Login-Sheet + Settings-Login darauf umstellen).

---

### F-06 — Primary-Button-Destructive für „Herunterfahren" ist visuell gleichwertig zu „Neustart" [SEVERITY 2]

**Heuristik/Prinzip:** Nielsen 5 (Error Prevention); Refactoring UI (visual hierarchy matches consequence severity).

**Betroffene Stellen:** `settings/system/+page.svelte:418-444` — Restart / Reboot / Shutdown.

**Warum es Nutzer verwirrt:** Drei Knöpfe untereinander in ähnlicher Größe und Form. Der „Herunterfahren"-Button ist tint-rot (E-Destructive-red-500/20), also zumindest farblich markiert — aber die erste Klick-Hürde ist dieselbe (ein Tap). Nachdem man ihn tappt, kommt eine Confirm-Pressen mit rot-massiv — aber die Gefahr, aus Versehen draufzutippen, bleibt. Für eine Familie mit Kindern, die zum Pi greifen, ist das eine echte Sorge. „Neustart" und „App neu laden" wiederum sind visuell identisch, obwohl sie semantisch verschieden sind.

**Fix-Empfehlung:** Drei Ebenen etablieren:
- App neu laden → Secondary (wie heute).
- OS-Neustart → Secondary (wie heute), aber mit zusätzlicher Confirm-Stufe.
- Shutdown → Visuell stärker abgesetzt (eigener kleiner Abschnitt mit Trennlinie, oder Shutdown als kleiner „Weniger-häufige-Aktion"-Link darunter). Die aktuelle Confirm-Two-Step-Mechanik ist gut — sie sollte bleiben, aber die erste Stufe weniger dominant machen.

**Fix-Aufwand:** S (1 Stunde — Trennlinie, Shutdown in Sekundär-Variante).

---

### F-07 — Input-Padding-Inkonsistenz py-2 vs py-2.5 [SEVERITY 1]

**Heuristik/Prinzip:** Refactoring UI „constrained scales".

**Betroffene Stellen:** Verstreute Input-Klassen im ganzen Projekt. Ungefähr hälftig.

**Warum es Nutzer verwirrt:** Subtile Höhenunterschiede zwischen Eingabefeldern derselben Semantik (Text-Input). Nicht blockierend, aber auf einem Smartphone-Viewport sichtbar, wenn zwei Formulare hintereinander erlebt werden (Wizard Card→Pin).

**Fix-Empfehlung:** `py-2.5` als Standard festlegen (hebt Touch-Target sicher über 44px). `py-2` entfernen.

**Fix-Aufwand:** XS (20 Minuten search-replace).

---

### F-08 — Description-Position variiert zwischen vor/nach/neben dem Control [SEVERITY 2]

**Heuristik/Prinzip:** Nielsen 4; Refactoring UI (pattern-level consistency).

**Betroffene Stellen:**
- `settings/+page.svelte:464` — Description **unter** der Control-Row, zwischen Toggle und Action
- `settings/+page.svelte:626-630` — Description **neben** der Überschrift, links vom Toggle
- `settings/system/+page.svelte:371-372` — Description **unter** der Überschrift, über dem Button
- System-Info Grid — Description ist dort der Value (kein Description-Pattern)
- Viele Settings-Rows (Sleep, Volume, Idle-Abschaltung) haben **gar keine** Description, obwohl eine hülfe

**Warum es Nutzer verwirrt:** Die Rolle des „kleinen grauen Texts" ist unklar: mal erklärt er die Einstellung, mal den Zustand, mal fehlt er. Der Nutzer kann nicht scannen „erst Label, dann graue Hilfe, dann Control".

**Fix-Empfehlung:** Fixe Row-Struktur definieren:
```
[Label (h3)]  [Control rechts wenn 1-Zeile wie Toggle]
[Description (p, text-xs text-text-muted, mt-0.5)]
[Control unten wenn mehrzeilig wie Segmented, Slider, Input]
```
Description immer **direkt unter dem Label**, nie zwischen Label und Control.

**Fix-Aufwand:** M (halber Tag — `<SettingRow>`-Komponente bauen, 10–12 Row-Instanzen migrieren).

---

### F-09 — Rounded-Scale ohne Regel (rounded-lg / -xl / -2xl / -full / -md willkürlich) [SEVERITY 1]

**Heuristik/Prinzip:** Refactoring UI „constrained scales".

**Betroffene Stellen:** 245 Treffer verteilt. Beispiele für Willkür:
- Settings-Card: `rounded-xl`
- Modal-Sheet: `rounded-2xl`
- Button: `rounded-lg`
- Tab-Pill: `rounded-full`
- Sortier-Segment: `rounded-md` (innerhalb `rounded-lg` Container)
- Audio-Radio-Card: `rounded-xl`
- PIN-OTP-Cell: `rounded-xl`

**Warum es Nutzer verwirrt:** Nicht direkt, aber das UI fühlt sich „nicht aus einem Guss" an. Der Nutzer nimmt es als „leicht unfertig" wahr, ohne es benennen zu können.

**Fix-Empfehlung:** Drei Radii festlegen:
- `radius-sm` (=`rounded-md`, 6px) — Inner-Controls (Segment-Buttons in Container)
- `radius-md` (=`rounded-lg`, 8px) — Standard-Buttons, Inputs
- `radius-lg` (=`rounded-xl`, 12px) — Cards, Settings-Sections, PIN-Cells
- `radius-xl` (=`rounded-2xl`, 16px) — Modals/Sheets, Cover-Art-Container
- `radius-full` — Pills/Avatars

Im Tailwind-Theme als Aliasse definieren. Migration: nur dort anfassen, wo es offensichtlich falsch ist (Modal → immer 2xl, Settings-Card → immer xl). Nicht mit der Brechstange.

**Fix-Aufwand:** L (mehrere Stunden für Dokumentation + konservative Migration; **eher Post-Beta**).

---

### F-10 — CardWall (Figuren-Übersicht) bricht mit Settings-Row-Pattern [SEVERITY 1]

**Heuristik/Prinzip:** Nielsen 4.

**Betroffene Stellen:** `cards/+page.svelte:178-224` — Figuren werden als 2-Spalten-Grid mit Cover+Name+Type dargestellt, Actions erscheinen als Overlay-Icons oben rechts („Edit"/"Delete").

**Warum es Nutzer verwirrt:** Keine direkte Verwirrung — die Figuren-Wand IST das Konsum-Muster (Fotos großflächig anzeigen). Aber: der Löschen-Flow geht über ein separates Modal, während die Library-Ordner Löschen direkt im aufgeklappten Detail haben. Das ist eine andere Mental-Model-Ebene und verletzt die Memory-Regel „Löschen nur im aufgeklappten Detail, nie auf oberster Ebene".

**Fix-Empfehlung:** Delete-Icon im Overlay-Hover ist **technisch eine Oberflächen-Action** — entspricht dem User-Prinzip, dass Löschen nur im Detail passieren darf. Vorschlag: Overlay-Icons entfernen, stattdessen Klick auf die Card öffnet ein Edit-Panel (Sheet von unten), darin ist Löschen die sekundäre Aktion. Das ist aber eine Produkt-Entscheidung des POs.

**Fix-Aufwand:** M (halber Tag). **Nicht dringend — markiere als „User fragen".**

---

### F-11 — WLAN-Rettung Ring-Offset ist der einzige Ort mit ring-offset [SEVERITY 1]

**Heuristik/Prinzip:** Refactoring UI „constrained scales"; Nielsen 4.

**Betroffene Stellen:** `settings/+page.svelte:529` — `ring-2 ring-primary ring-offset-2 ring-offset-surface-light`.

**Warum es Nutzer verwirrt:** Der Offset-Ring wirkt wie ein Focus-Indikator, ist aber der Selected-State. Der Selected-State ist an allen anderen Orten des Projekts **ohne** Offset gelöst (nur Fill-Change + evtl. kleiner Ring).

**Fix-Empfehlung:** Ring-Offset entfernen, nur `bg-primary text-white` wie alle anderen Segmented-Controls. 1 Zeile.

**Fix-Aufwand:** XS (2 Minuten). **Beta-Must.**

---

### F-12 — Modal-Kombinationsinkonsistenz: 4 Modals, 4 leicht verschiedene Container [SEVERITY 1]

**Heuristik/Prinzip:** Nielsen 4.

**Betroffene Stellen:**
- `cards/+page.svelte:232-281` (Edit-Modal): `w-full sm:w-[28rem] max-h-[85vh] rounded-t-2xl sm:rounded-2xl p-5`
- `cards/+page.svelte:288-314` (Delete-Modal): `w-full sm:w-96 rounded-t-2xl sm:rounded-2xl p-6`
- `LoginSheet.svelte:71`: `w-full sm:w-[24rem] rounded-t-2xl sm:rounded-2xl p-5`
- `HelpSheet.svelte` (nicht eingelesen, aber aus context): eigene Klassen

Breite: 24rem / 28rem / 24rem, Padding: p-5 / p-6 / p-5. Alle nutzen die richtige Responsive-Logik (mobile: bottom-sheet, desktop: center-dialog), aber die Werte divergieren.

**Warum es Nutzer verwirrt:** Minimal sichtbar. Hauptsächlich Entwickler-Reibung.

**Fix-Empfehlung:** `<Sheet>` Wrapper-Komponente die das Responsive-Handling zentralisiert. Breiten: `sm` (24rem), `md` (28rem), `lg` (32rem), `xl` (36rem).

**Fix-Aufwand:** S (2 Stunden). **Post-Beta.**

---

### F-13 — Icon-Inkonsistenz: Inline-SVG überall, Icon-Komponente nur teilweise [SEVERITY 1]

**Heuristik/Prinzip:** Refactoring UI (deliberate icon sizing).

**Betroffene Stellen:** `Icon.svelte` gibt es als zentrale Komponente und wird in HardwareStep, ButtonsStep, Library, Setup-Page verwendet. Gleichzeitig gibt es **inline-SVGs** in Player, Settings, ContentPicker, CardStep, Card-Grid, Layout-Nav. Drei SVG-Styles (stroke-width 1.5, 2, 2.5) gemischt.

**Warum es Nutzer verwirrt:** Hauptsächlich Wartbarkeit. User-facing: die Stroke-Width-Variation ist bei kleinen Icons (w-3.5/h-3.5 vs w-5/h-5) teilweise sichtbar.

**Fix-Empfehlung:** Lucide-Icons (die Icon.svelte bereits liefert) auf alle Use-Cases ausweiten. Player-Controls können Custom-SVG bleiben (Play/Pause/Next/Prev haben ihre eigene visuelle Sprache). Aber Settings, Content-Picker, Card-Wall sollten Icon.svelte nutzen.

**Fix-Aufwand:** M (halber Tag). **Post-Beta.**

---

### F-14 — Settings-Seite mischt Control-Positionierung: Toggle rechts vs. Buttons voll unten [SEVERITY 1]

**Heuristik/Prinzip:** Nielsen 4; Refactoring UI (pattern consistency).

**Betroffene Stellen:**
- `settings/+page.svelte:425-433` Gyro-Toggle rechts, dann Segmented darunter
- `settings/+page.svelte:452-462` WLAN-Toggle rechts, dann Detail-Panel darunter
- `settings/+page.svelte:402-418` Figur wegnehmen — Segmented ohne Toggle (braucht keinen An/Aus)
- `settings/+page.svelte:375-398` Lautstärke — Slider (nicht Toggle)
- `settings/+page.svelte:355-370` Sleep-Timer — Input+Button auf einer Zeile

Das Layout-Pattern wechselt zwischen „Toggle-Primary, Detail-Secondary" und „Detail ist die Einstellung selbst, kein Toggle". Das ist an sich nicht schlimm — aber der Wechsel passiert in schneller Folge ohne visuelle Gruppierung.

**Warum es Nutzer verwirrt:** Der Scan-Rhythmus bricht. Als Nutzer scrollt man die Settings-Seite durch und sucht Header+Control auf derselben Höhe — stattdessen sind manche Cards „Header allein → Control darunter" und manche „Header und Toggle rechts → Detail darunter".

**Fix-Empfehlung:** Eine kanonische `<SettingRow>` (siehe Phase C).

**Fix-Aufwand:** M (als Teil von F-08).

---

### F-15 — Label-Ton variiert („Aktiviert/Deaktiviert" vs. „An/Aus" vs. „Bereit/Fertig") [SEVERITY 1]

**Heuristik/Prinzip:** Nielsen 2 (Match between system and real world); Krug „clever vs. clear".

**Betroffene Stellen:**
- `settings/+page.svelte:431` — `gyroEnabled ? t('settings.gyro_enabled') : t('settings.gyro_disabled')` → „Aktiviert" / „Deaktiviert"
- `settings/+page.svelte:635` — `… ? t('settings.on') : t('settings.off')` → „An" / „Aus"
- PIN-Status — „Aktiv" / „Nicht gesetzt"
- Hardware-Status — „Erkannt" / „Nicht erkannt" / „Nicht verbunden"

**Warum es Nutzer verwirrt:** „Aktiviert/Deaktiviert" ist länger und technischer als „An/Aus". Eltern erwarten Alltagssprache.

**Fix-Empfehlung:** „An/Aus" als Standard-Vokabular. Die Tier-Bezeichnung („Aktiv" bei PIN) ist korrekt, weil PIN wirklich einen anderen Zustand beschreibt.

**Fix-Aufwand:** XS (5 Minuten — zwei i18n-Schlüssel anpassen — `settings.gyro_enabled/disabled` → `settings.on/off` wiederverwenden).

---

## Phase C — Vorgeschlagenes Design-System

### C.1 Tokens (Tonado Design Tokens)

Keine Revolution, nur Festschreibung:

```js
// web/tailwind.config.ts (ergänzen oder per @theme in app.css)
colors: {
  primary: { DEFAULT: '#6366f1', light: '#818cf8', dark: '#4f46e5' }, // dark ungenutzt — streichen
  surface: { DEFAULT: '#1e1e2e', light: '#2a2a3e', lighter: '#363650' },
  text: { DEFAULT: '#e2e2f0', muted: '#a0a0b8' },
  accent: '#f59e0b',
  // Semantic (neu)
  success: '#22c55e',   // green-500
  warning: '#f59e0b',   // = accent, OK
  danger:  '#ef4444',   // red-500
  info:    '#3b82f6',   // blue-500
},
borderRadius: {
  // Regel: nur diese 5 verwenden
  sm:   '0.375rem', // 6px — inner-controls in segment containers
  md:   '0.5rem',   // 8px — buttons, inputs
  lg:   '0.75rem',  // 12px — cards, sections, pin cells
  xl:   '1rem',     // 16px — modals, sheets, cover
  full: '9999px',   // pills, avatars
},
// Spacing bleibt Tailwind-Default (das ist schon die konstriente Skala).
```

Auf Button-Höhen (44px Touch-Target), Input-Padding (`py-2.5`), Font-Größen (`text-xs`/`text-sm`/`text-base`/`text-lg`) explizit committen — dokumentieren, nicht neu definieren.

### C.2 Kanonische Komponenten

Vorschlag: ein neuer Ordner `web/src/lib/components/ui/` für die folgenden Primitiven. Jede ist schlank, Svelte-5-Runes-nativ, und ersetzt bestehende Patterns 1:1.

#### `<Button variant size>` (`ui/Button.svelte`)

```svelte
<script lang="ts">
  type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'danger-outline';
  type Size = 'sm' | 'md' | 'lg';
  // children, onclick, disabled, type, class, ...
</script>
```

- `variant=primary` → `bg-primary hover:bg-primary-light text-white`
- `variant=secondary` → `bg-surface-light hover:bg-surface-lighter text-text-muted`
- `variant=ghost` → `text-text-muted hover:text-text` (link-style)
- `variant=danger` → `bg-red-600 hover:bg-red-500 text-white`
- `variant=danger-outline` → `bg-red-500/20 hover:bg-red-500/30 text-red-400`
- `size=sm` → `px-3 py-2 text-sm rounded-md` (= 36px Höhe — **nur für Inline-Listen**, nicht Page-Actions)
- `size=md` → `px-4 py-2.5 text-sm rounded-lg` (= 44px — Standard)
- `size=lg` → `px-5 py-3 text-base rounded-lg` (= 48px — Wizard-CTA, Modal-Submit)

#### `<SettingRow label description>` (`ui/SettingRow.svelte`)

```svelte
<script lang="ts">
  // label: string
  // description?: string
  // trailing?: snippet  — für Toggle rechts
  // children: snippet   — für volle Control darunter (Slider, Segmented, Input)
</script>

<div class="bg-surface-light rounded-lg p-4">
  <div class="flex items-start justify-between gap-3 mb-2">
    <div class="flex-1 min-w-0">
      <h3 class="text-sm font-semibold text-text">{label}</h3>
      {#if description}
        <p class="text-xs text-text-muted mt-0.5">{description}</p>
      {/if}
    </div>
    {#if trailing}{@render trailing()}{/if}
  </div>
  {#if children}
    <div class="mt-3">{@render children()}</div>
  {/if}
</div>
```

#### `<SegmentSelect options bind:value>` (`ui/SegmentSelect.svelte`)

Basierend auf V3 (FolderTab). Enthält intern:
- `role="radiogroup"`, `aria-label`
- Jedes Segment: `role="radio"`, `aria-checked`, `tabindex={active ? 0 : -1}`, `min-h-11`
- Pfeil-Tasten-Navigation (Port von `radiogroup.ts`)
- Container: `grid grid-cols-{n} rounded-lg bg-surface-light p-0.5`
- Aktives Segment: `bg-primary text-white rounded-md`

Verwendung:
```svelte
<SegmentSelect
  options={[
    { id: 'gentle', label: t('settings.gyro_gentle') },
    { id: 'normal', label: t('settings.gyro_normal') },
    { id: 'wild',   label: t('settings.gyro_wild') },
  ]}
  bind:value={gyroSensitivity}
  onchange={(v) => saveSetting('gyro.sensitivity', v)}
  aria-label={t('settings.gyro')}
/>
```

#### `<ToggleRow label description bind:checked>` (`ui/ToggleRow.svelte`)

Wrapper um `<SettingRow>` mit einem iOS-Switch als `trailing`. Ersetzt die drei Toggle-Varianten.

```svelte
<SettingRow {label} {description}>
  {#snippet trailing()}
    <label class="relative inline-flex items-center cursor-pointer">
      <input type="checkbox" class="sr-only peer" bind:checked />
      <div class="w-11 h-6 bg-surface peer-focus:ring-2 peer-focus:ring-primary rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
    </label>
  {/snippet}
</SettingRow>
```

#### `<PinEntry length value onComplete>` (`ui/PinEntry.svelte`)

Extraktion der OTP-Cell-Logik aus `PinStep.svelte`. Wiederverwendbar für Settings-Login und LoginSheet.

#### Optional: `<Sheet>` (`ui/Sheet.svelte`) & `<InputRow>` (`ui/InputRow.svelte`)

Post-Beta — nicht kritisch für die erste Welle.

### C.3 Migrations-Karte

| Heutiges Pattern | Fundstelle | Ersatz |
|---|---|---|
| V1 Ring-Offset-Segment (WLAN-Rettung) | `settings/+page.svelte:522-534` | `<SegmentSelect>` |
| V2 Chip-Segment ohne Ring (Figur-wegnehmen, Gyro-Stärke) | `settings/+page.svelte:404-417, 434-446` | `<SegmentSelect>` |
| V3 Segmented (Library-Sort) | `FolderTab/RadioTab/PodcastTab/PlaylistTab` | **bleibt** (Blueprint) |
| V4 Rounded-Full-Tabs (Library) | `library/+page.svelte:137-154` | **bleibt** (Navigation, nicht Value) |
| V5 Icon-Chip (ContentPicker) | `ContentPicker.svelte:115-129` | **bleibt**, aber Container auf `<SegmentSelect>`-Style heben |
| V7 `<select>` Idle-Abschaltung | `settings/+page.svelte:613-622` | `<SegmentSelect>` mit 4 Optionen (Aus/15/30/60) |
| V8 Radio-Card Audio-Ausgang | `AudioStep.svelte:74-93` | **bleibt** (Rich-Card) |
| V9 WLAN-Liste | `WifiStep.svelte:76-94` | **bleibt** (Rich-List) |
| T1 iOS-Switch | `settings/+page.svelte:454-462` | `<ToggleRow>` (Blueprint) |
| T2 Chip-Button-Toggle (Gyro) | `settings/+page.svelte:427-432` | `<ToggleRow>` |
| T2 Chip-Button-Toggle (Expertenmodus) | `settings/+page.svelte:631-636` | `<ToggleRow>` |
| Inline Primary-Button py-2 | `settings/+page.svelte:336,368,556,589` | `<Button variant=primary size=md>` |
| Inline Primary-Button py-2.5 | `settings/system/+page.svelte:*` | `<Button variant=primary size=md>` (gleicher Output) |
| Inline Primary-Button py-3 | `setup/+page.svelte:*`, `LoginSheet.svelte:94` | `<Button variant=primary size=lg>` |
| Inline PIN-Input (Settings) | `settings/+page.svelte:329-340` | `<PinEntry length=4>` |
| Inline PIN-Input (LoginSheet) | `LoginSheet.svelte:76-88` | `<PinEntry length=4>` |
| Rohe `<p class="text-red-400">` Fehler | überall | `<InlineError>` |
| Setting-Card `bg-surface-light rounded-xl p-4` | 21 Stellen | `<SettingRow>` |

### C.4 Priorisierung — Beta-Must vs. Post-Beta

Der Kontext: Beta-Release kurz vor Abschluss. Schwere Refactorings sollen _nach_ Beta. Deshalb fällt die Beta-Must-Liste bewusst minimal aus — pro Kategorie der sichtbarste Bruch, der ohne Komponenten-Bau behoben werden kann.

**BETA-MUST (gesamt: 1,5 Stunden Arbeit)**

1. **F-11 — Ring-Offset entfernen:** `settings/+page.svelte:529` → `ring-2 ring-primary ring-offset-2 ring-offset-surface-light` wird zu `bg-primary text-white` (wie die Nachbar-Segmente). **2 Minuten.**
2. **F-15 — Toggle-Label-Vokabular:** `gyro_enabled/disabled` aus i18n durch `settings.on/off` ersetzen (i18n-Keys refaktorieren, 2 Call-Sites anpassen). **5 Minuten.**
3. **F-04 partial — Eine Fehler-Art konsolidieren:** Die „inline `<p class="text-sm text-red-400">` in Settings- und Setup-Seiten, die dauerhaft stehen bleiben sollen" durch `<InlineError>` ersetzen. Ephemere Fehler bleiben als Toast. **1 Stunde** (plain Fehler in Settings-Page, alle Setup-Steps außer PIN).
4. **F-06 — Shutdown visuell abtrennen:** In `settings/system/+page.svelte:415-446` eine Trennlinie `border-t border-surface-lighter mt-4 pt-4` vor dem Shutdown-Button einziehen. **10 Minuten.**

**POST-BETA (nachhaltige Arbeit, 2–3 Tage):**

1. `<Button>`, `<SettingRow>`, `<ToggleRow>`, `<SegmentSelect>` als Komponenten extrahieren — F-01, F-03, F-08, F-14 (ein halber Tag pro Komponente).
2. `<PinEntry>` extrahieren (F-05) — halber Tag.
3. Migrations-Welle: Settings-Seite vollständig auf neue Komponenten umstellen (ein Tag).
4. Setup-Wizard-Buttons auf `<Button size=lg>` umstellen (2 Stunden).
5. Content-Picker-Typ-Filter und Library-Tabs auf Container-Style des neuen SegmentSelect-Containers heben (F-02) — 2 Stunden.
6. `<Sheet>`-Komponente bauen und Edit-/Delete-/Login-/Help-Sheet darauf umstellen (F-12) — halber Tag.
7. Radius-Scale formell festschreiben + offensichtliche Ausreißer korrigieren (F-09) — 2 Stunden.
8. Icon-Konsolidierung (F-13) — halber Tag.
9. Open question: F-10 (CardWall-Löschen im Detail vs. Overlay) — Produktentscheidung PO.

### C.5 Nicht-Ziele dieses Audits

- Kein Redesign der Farbpalette, keine neue Markenidentität.
- Keine Änderung der Informationsarchitektur (welche Einstellung wo wohnt).
- Keine Überarbeitung der Animationen (Sleep-Pill-Bump, Marquee, Shake) — die sind hoch-poliert und bleiben.
- Keine Bewertung der Audio-Test-UX oder der Gyro-Kalibrierung — eigene Audits wert, aber out of scope.

---

## Executive Summary für User

**Was ich gefunden habe:** Tonados Frontend ist technisch sauber und funktional sehr weit — aber die Formular- und Einstellungs-Sprache ist auf der Strecke geblieben. Für dieselbe Interaktion („eine aus N wählen") existieren neun visuell verschiedene Lösungen. Für „An/Aus" gibt es drei. Für „Primary-Button" drei Höhen. Das macht Tonado technisch nicht kaputt, aber es fühlt sich für einen nicht-technischen Elternteil wie drei verschiedene Apps nebeneinander an.

**Die fünf wichtigsten Findings:**

1. **F-02** — 9 visuelle Sprachen für „Auswahl aus N" (Severity 3) — die saubere `FolderTab`-Segmented-Variante ist bereits da und sollte Blueprint werden.
2. **F-01** — 3 verschiedene An/Aus-Toggles auf EINER Settings-Seite (Severity 3) — der iOS-Switch für WLAN-Rettung ist Blueprint.
3. **F-04** — 6 Fehler-Darstellungs-Muster parallel (Severity 2) — `<HealthBanner>` + `<InlineError>` + Toast decken alles ab, die rohe rote Zeile gehört weg.
4. **F-05** — PIN-Login nutzt nicht die OTP-Cells, die der Setup-Wizard schon hat (Severity 2) — Extraktion als `<PinEntry>` wäre ein großer Konsistenzgewinn.
5. **F-08/F-14** — Settings-Row-Struktur ist pro Card anders (Severity 2) — eine `<SettingRow>`-Komponente würde 80% der Seite einheitlich machen.

**Beta-Must-Liste (ca. 1,5 Stunden, keine neuen Komponenten):**
- Ring-Offset der WLAN-Rettung-Chips entfernen (F-11, 2 Min)
- „Aktiviert/Deaktiviert" → „An/Aus" (F-15, 5 Min)
- Plain `<p class="text-red-400">`-Fehler durch `<InlineError>` ersetzen (F-04 Teil, 1 Std)
- Shutdown-Button mit `border-t` abtrennen (F-06, 10 Min)

**Post-Beta-Liste (~2–3 Tage):**
- `<Button>`, `<SettingRow>`, `<ToggleRow>`, `<SegmentSelect>`, `<PinEntry>` als Komponenten bauen und Settings + Wizard darauf migrieren.
- `<Sheet>` extrahieren, Radius-Scale formell festschreiben.
- Icon-Konsolidierung auf `<Icon>` überall.

**Eine offene Produktfrage an dich:** F-10 — Soll das Löschen einer Figur aus dem Overlay-Icon in der Card-Grid verschwinden (und nur im aufgeklappten Edit-Panel auftauchen, analog zur Library)? Das ist deine Regel aus Memory — die Card-Wall verletzt sie aktuell. Meine Empfehlung: ja, aber das ist deine Entscheidung.

**Soll ich die Beta-Must-Liste jetzt umsetzen — oder zuerst die Post-Beta-Komponenten skizzieren?**
