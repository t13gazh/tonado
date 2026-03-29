# Tonado UI Guidelines

Verbindliche Design-Guideline für die Tonado Web-App.
Referenz-Seiten: **Player** (`+page.svelte`) und **Einstellungen** (`settings/+page.svelte`).
Alle anderen Seiten müssen sich an diese Patterns anpassen.

---

## 1. Design Tokens

Definiert in `web/src/app.css` unter `@theme`.

### Farben

| Token | Hex | Verwendung |
|-------|-----|------------|
| `primary` | `#6366f1` | Primäre Aktionen, aktive Zustände, Akzent |
| `primary-light` | `#818cf8` | Hover-Zustand von Primary |
| `primary-dark` | `#4f46e5` | Pressed-Zustand (selten) |
| `surface` | `#1e1e2e` | Body-Hintergrund, Input-Hintergrund |
| `surface-light` | `#2a2a3e` | Karten/Sektionen, Nav-Bar |
| `surface-lighter` | `#363650` | Borders, Divider, deaktivierte Elemente |
| `text` | `#e2e2f0` | Primärer Text |
| `text-muted` | `#9393a8` | Sekundärer Text, Labels, Platzhalter |
| `accent` | `#f59e0b` | Warnhinweise, Update-Badges, Amber-Akzent |

### Semantische Farben (Tailwind-Defaults)

| Zweck | Klasse | Verwendung |
|-------|--------|------------|
| Erfolg | `green-500` | Checkmarks, Status-Dots (verbunden) |
| Fehler | `red-400` / `red-500` / `red-600` | Fehlermeldungen, Löschen, Shutdown |
| Warnung | `amber-400` / `amber-500` | Warnbanner, Timer-Anzeige |
| Info | `blue-400` / `blue-500` | Info-Banner |

### Schrift

- **Familie:** `Inter, system-ui, -apple-system, sans-serif`
- **Größen:** `text-xs` (10px), `text-sm` (14px), `text-lg` (18px), `text-xl` (20px)
- **Gewichte:** `font-medium` (500), `font-semibold` (600), `font-bold` (700)

### Radien

| Element | Radius |
|---------|--------|
| Karten/Sektionen | `rounded-xl` (12px) |
| Buttons (rechteckig) | `rounded-lg` (8px) |
| Buttons (Pill) | `rounded-full` |
| Inputs | `rounded-lg` (8px) |
| Modals | `rounded-2xl` (16px) bzw. `rounded-t-2xl` (mobile bottom sheet) |
| Progress bars | `rounded-full` |
| Thumbnails | `rounded-lg` (8px) |

### Abstände

| Kontext | Wert |
|---------|------|
| Seiten-Padding | `p-4` (16px) |
| Abstand zwischen Sektionen | `gap-4` (16px) |
| Padding innerhalb Karten | `p-4` (16px) |
| Abstand zwischen Buttons in einer Reihe | `gap-2` (8px) oder `gap-3` (12px) |
| Label über Input/Section | `mb-3` (12px) |

---

## 2. Button-Hierarchie

### Primary Action (Hauptaktion)

Für die wichtigste Aktion pro Bildschirm: Speichern, Weiter, Login, Figur anlegen.

```
class="px-4 py-2.5 bg-primary hover:bg-primary-light disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-white text-sm font-medium transition-colors"
```

**Variante: Full-Width (Wizard-Navigation, Setup)**
```
class="w-full py-3 bg-primary hover:bg-primary-light disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
```

**Variante: Play-Button (Player, rund)**
```
class="p-5 bg-primary hover:bg-primary-light rounded-full text-white transition-colors active:scale-95 shadow-lg disabled:opacity-40 disabled:cursor-not-allowed"
```

### Secondary Action (Nebenaktionen)

Für zurück, Abbrechen, alternative Aktionen. Visuell zurückgenommen.

```
class="px-4 py-2.5 bg-surface-light hover:bg-surface-lighter rounded-lg text-text-muted text-sm font-medium transition-colors"
```

**Variante: mit Border (Abbrechen in Modals)**
```
class="px-4 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text-muted text-sm font-medium"
```

### Danger Action (Löschen, Herunterfahren)

**Destructive Primary (Bestätigung im Modal):**
```
class="px-4 py-2.5 bg-red-600 hover:bg-red-500 rounded-lg text-white text-sm font-medium transition-colors"
```

**Destructive Secondary (erste Stufe, vor Bestätigung):**
```
class="px-4 py-2.5 bg-red-500/20 rounded-lg text-red-400 text-sm font-medium hover:bg-red-500/30 transition-colors"
```

**Inline Danger (z.B. PIN entfernen):**
```
class="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg text-sm hover:bg-red-500/30"
```

### Ghost/Link Action (Navigation, Abbrechen, Retry)

Für minimale visuelle Präsenz: textbasierte Links, Abbruch-Links, Retry.

```
class="text-sm text-primary font-medium"
```

**Muted Ghost (Logout, sekundäre Text-Actions):**
```
class="text-xs text-text-muted hover:text-text"
```

### Toggle Buttons

**Pill-Toggle (An/Aus, Gyro, Audio-Stream):**
```
// Aktiv:
class="px-3 py-1 rounded-full text-xs font-medium transition-colors bg-primary text-white"

// Inaktiv:
class="px-3 py-1 rounded-full text-xs font-medium transition-colors bg-surface text-text-muted"
```

**Segmented Control (Karte wegnehmen = Pause/Weiterspielen, Gyro-Sensitivity):**
```
// Aktiv:
class="flex-1 px-3 py-2 rounded-lg text-sm transition-colors bg-primary text-white"

// Inaktiv:
class="flex-1 px-3 py-2 rounded-lg text-sm transition-colors bg-surface text-text-muted"
```

**Tab-Buttons (Bibliothek-Tabs, Content-Type-Tabs):**
```
// Aktiv:
class="px-3 py-1.5 text-xs font-medium rounded-full whitespace-nowrap transition-colors bg-primary text-white"

// Inaktiv:
class="px-3 py-1.5 text-xs font-medium rounded-full whitespace-nowrap transition-colors bg-surface-light text-text-muted hover:text-text"
```

### Icon Buttons (Player-Controls, Edit, Delete)

**Player Steuerung (Skip, Shuffle, Repeat):**
```
class="p-2 transition-colors active:scale-95 text-text-muted hover:text-text"

// Aktiv (z.B. Shuffle an):
class="p-2 transition-colors active:scale-95 text-primary"
```

**Overlay-Icon (auf Karten, Edit/Delete):**
```
class="p-1.5 bg-surface/80 rounded-lg backdrop-blur-sm text-text-muted hover:text-text"
```

---

## 3. Karten / Sektionen

Alle inhaltlichen Bereiche auf Einstellungs-, System-, Figuren-Seiten.

### Standard-Sektion

```html
<div class="bg-surface-light rounded-xl p-4">
  <h2 class="text-sm font-semibold mb-3">Sektions-Titel</h2>
  <!-- Inhalt -->
</div>
```

### Klickbare Sektion (Navigation zu Unterseite)

```html
<a href="/target" class="flex items-center justify-between bg-surface-light rounded-xl p-4 hover:bg-surface-lighter transition-colors">
  <div>
    <h2 class="text-sm font-semibold">Titel</h2>
    <p class="text-xs text-text-muted mt-0.5">Beschreibung</p>
  </div>
  <svg class="w-5 h-5 text-text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M9 18l6-6-6-6"/>
  </svg>
</a>
```

### Card-Wall-Item (Figuren-Grid)

```html
<div class="bg-surface-light rounded-xl overflow-hidden">
  <div class="aspect-square bg-surface-lighter flex items-center justify-center">
    <!-- Cover oder Fallback-Icon -->
  </div>
  <div class="p-2.5">
    <p class="text-sm font-medium text-text truncate">Name</p>
    <p class="text-xs text-text-muted mt-0.5">Typ</p>
  </div>
</div>
```

### Sektionen innerhalb von Flex-Container

```html
<div class="flex flex-col gap-4">
  <!-- Mehrere Sektionen -->
</div>
```

---

## 4. Inputs

### Text-Input

```
class="w-full px-3 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
```

**Variante: mit Placeholder**
```
class="w-full px-3 py-2.5 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary placeholder:text-text-muted/50"
```

**Variante: auf Surface-Light-Hintergrund (Wizard, ContentPicker)**
```
class="w-full px-3 py-2.5 bg-surface-light border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
```

### Number-Input

```
class="w-20 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm text-center focus:outline-none focus:border-primary"
```

### Select

```
class="w-full px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary"
```

### Range/Slider

```
class="w-full h-2 bg-surface-lighter rounded-full appearance-none cursor-pointer
  [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:h-5
  [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-primary"
```

### Password-Input (inline mit Button)

```html
<div class="flex gap-2">
  <input type="password"
    class="flex-1 px-3 py-2 bg-surface border border-surface-lighter rounded-lg text-text text-sm focus:outline-none focus:border-primary" />
  <button class="px-4 py-2 bg-primary text-white rounded-lg text-sm disabled:opacity-30 disabled:cursor-not-allowed">
    Aktion
  </button>
</div>
```

---

## 5. Seiten-Header

### Seiten-Titel (Top-Level)

```html
<h1 class="text-xl font-bold mb-4">Seitentitel</h1>
```

### Seiten-Titel mit Zurück-Button (Unterseiten)

```html
<div class="flex items-center gap-3 mb-4">
  <a href="/parent" class="p-2 text-text-muted hover:text-text">
    <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M19 12H5M12 19l-7-7 7-7"/>
    </svg>
  </a>
  <h1 class="text-xl font-bold">Titel</h1>
</div>
```

### Seiten-Titel mit Action-Button (Figuren: + Hinzufügen)

```html
<div class="flex items-center justify-between mb-4">
  <h1 class="text-xl font-bold text-text">Titel</h1>
  <a href="/target" class="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-light text-white rounded-lg text-sm font-medium transition-colors">
    <svg class="w-4 h-4" ...><!-- Plus-Icon --></svg>
    Aktion
  </a>
</div>
```

### Sektions-Header (innerhalb Karte)

```html
<h2 class="text-sm font-semibold mb-3">Sektions-Titel</h2>
```

### Sektions-Header mit Toggle

```html
<div class="flex items-center justify-between mb-3">
  <h2 class="text-sm font-semibold">Titel</h2>
  <!-- Pill-Toggle -->
</div>
```

---

## 6. Toast / Banner / Feedback

### Toast (Erfolgs-Meldung, Fixed)

Schwebt oben, verschiebt kein Layout.

```html
<div class="fixed top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 bg-green-500/90 text-white text-sm rounded-xl shadow-lg transition-all duration-300 pointer-events-none
  {showToast ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2'}">
  Gespeichert
</div>
```

### Inline-Meldung (Fehler)

```
class="text-sm text-red-400 mb-3 p-3 bg-red-400/10 rounded-lg"
```

### Inline-Meldung (Info/Status)

```
class="mb-3 px-3 py-2 bg-primary/10 border border-primary/20 rounded-lg text-primary text-sm"
```

### HealthBanner (Komponente)

Für systemweite Warnungen. Bereits als Shared Component vorhanden:

```html
<HealthBanner type="warning" message="..." />
<HealthBanner type="error" message="..." />
<HealthBanner type="info" message="..." />
```

---

## 7. Modals

### Bottom Sheet (Mobile-First)

```html
<div class="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50">
  <div class="bg-surface-light w-full sm:w-[28rem] max-h-[85vh] rounded-t-2xl sm:rounded-2xl p-5 flex flex-col overflow-hidden">
    <h2 class="text-lg font-bold mb-4">Titel</h2>
    <div class="flex-1 overflow-y-auto">
      <!-- Inhalt -->
    </div>
    <div class="flex gap-3 pt-4">
      <!-- Secondary + Primary Button -->
    </div>
  </div>
</div>
```

### Confirmation Dialog

```html
<div class="fixed inset-0 bg-black/60 flex items-end sm:items-center justify-center z-50">
  <div class="bg-surface-light w-full sm:w-96 rounded-t-2xl sm:rounded-2xl p-6">
    <h2 class="text-lg font-bold mb-2">Titel</h2>
    <p class="text-sm text-text-muted mb-4">Beschreibung</p>
    <div class="flex gap-3">
      <button class="flex-1 ...">Abbrechen</button>
      <button class="flex-1 ...">Aktion</button>
    </div>
  </div>
</div>
```

---

## 8. Listen-Zeilen (Bibliothek-Pattern)

Einheitliches Zeilen-Layout für alle Listen:

```
[ Play-Kreis ] [ Thumbnail ] Titel + Subtitle + Dauer [ Chevron ]
```

### Play-Kreis (Snippet)

```
// Normal:
class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 bg-primary/10 hover:bg-primary/20 text-primary"

// Aktiv (gerade spielend):
class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 bg-primary text-white"
```

### Thumbnail

```
class="w-10 h-10 rounded-lg bg-surface-lighter flex-shrink-0 overflow-hidden flex items-center justify-center"
```

### Selectable List-Item (ContentPicker)

```
// Normal:
class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors bg-surface-light text-text hover:bg-surface-lighter"

// Ausgewählt:
class="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-left transition-colors bg-primary text-white"
```

---

## 9. Step-Indikatoren (Wizard, Setup)

### Einfache Balken (Wizard)

```html
<div class="flex items-center gap-2 mb-6 px-4">
  {#each steps as s, i}
    <div class="flex-1 h-1 rounded-full {active || completed ? 'bg-primary' : 'bg-surface-lighter'}"></div>
  {/each}
</div>
```

### Beschriftete Balken (Setup)

```html
<div class="flex items-center gap-1.5 px-4 pb-3">
  {#each steps as step, i}
    <div class="flex-1 flex flex-col items-center gap-1">
      <div class="w-full h-1.5 rounded-full {isActive ? 'bg-primary' : isCompleted ? 'bg-primary/60' : 'bg-surface-lighter'}"></div>
      <span class="text-[10px] {isActive ? 'text-primary font-medium' : 'text-text-muted'}">{label}</span>
    </div>
  {/each}
</div>
```

---

## 10. Status-Indikatoren

### Connection Dot

```
// Verbunden:
class="w-2 h-2 rounded-full bg-green-500"

// Nicht verbunden:
class="w-2 h-2 rounded-full bg-red-500"
```

### Hardware-Status (System-Seite)

```html
<span class="flex items-center gap-1.5">
  <span class="w-2 h-2 rounded-full {detected ? 'bg-green-500' : 'bg-red-500'}"></span>
  Label
</span>
```

---

## 11. Empty States

```html
<div class="text-center py-20 text-text-muted">
  <svg class="w-16 h-16 mx-auto mb-4 opacity-30" ...><!-- Fallback-Icon --></svg>
  <p class="text-sm font-medium">Primär-Text</p>
  <p class="text-xs mt-1">Sekundär-Text</p>
</div>
```

---

## 12. Loading States

### Spinner (zentriert)

```html
<div class="flex justify-center py-12">
  <Spinner />
</div>
```

### Inline Spinner (in Button)

```html
<button class="... flex items-center gap-2">
  <Spinner size="sm" />
  Lade...
</button>
```

### Indeterminate Progress Bar

```html
<div class="w-full h-2 bg-surface-lighter rounded-full overflow-hidden">
  <div class="h-full w-1/3 bg-primary rounded-full animate-indeterminate"></div>
</div>
```

---

## 13. Bekannte Inkonsistenzen (zu beheben)

Keine bekannten Inkonsistenzen. Stand: 2026-03-29.

### Allgemeine Regeln

1. **Buttons sehen NICHT wie Inputs aus.** Buttons haben keinen `border border-surface-lighter` auf `bg-surface` Hintergrund. Das ist Input-Styling.
2. **Full-width Buttons sind zentriert** (`text-center` ist Default, kein `text-left`).
3. **Jeder Button hat einen Hover-State.** Mindestens `hover:bg-*` oder `hover:text-*`.
4. **Disabled-State:** `disabled:opacity-50 disabled:cursor-not-allowed` (oder `disabled:opacity-40` für primäre Buttons).
5. **Touch-Feedback:** `active:scale-95` für Player-Controls. Für andere Buttons reicht `transition-colors`.
6. **Konsistente Padding-Höhe:** `py-2` bis `py-2.5` für inline Buttons, `py-3` für full-width Wizard/Setup Buttons.
