# Security Policy

Tonado läuft auf Geräten, die Kinder bedienen. Security-Bugs sind uns deshalb wichtig — bitte hilf uns, sie diskret zu melden.

## Unterstützte Versionen

| Version | Status |
|---------|--------|
| `main` (Entwicklungsstand) | ✅ aktive Security-Fixes |
| `v0.2.x` (Alpha → Beta) | ✅ aktive Security-Fixes |
| ältere Alpha-Tags | ⚠️ bitte updaten |

Sobald die erste Beta (`v0.2.0-beta`) stabil ist, wird diese Tabelle entsprechend gepflegt.

## Einen Security-Bug melden

**Nicht im öffentlichen Issue-Tracker.** Bitte per Mail an:

- `https://github.com/t13gazh/tonado/security/advisories/new`

Bitte in die Betreffzeile `[Tonado Security]` aufnehmen.

Enthalten sein sollte:
- Betroffene Komponente (Backend / Frontend / Install-Script / Hardware-Layer)
- Reproduktions-Schritte oder Minimal-PoC
- Vermutete Auswirkung (lokaler Lesezugriff? Netzwerkzugriff? Code-Execution auf dem Pi?)
- Optional: CVE-Klassifizierung oder Score (CVSS 3.1)

Wir bestätigen den Eingang innerhalb von **72 Stunden** und planen einen Fix innerhalb von **14 Tagen**, je nach Schweregrad schneller.

## Was als Security-Issue zählt

- Unauthentifizierter Zugriff auf schreibende API-Endpoints im lokalen Netz
- Privilege-Escalation zwischen Tiers (`open` → `parent` → `expert`)
- Code-Execution durch manipulierte RSS-Feeds, Karten-IDs, Datei-Uploads
- Path-Traversal durch Library- oder Player-Endpoints
- SSRF / interne IPs aus Nutzer-Input erreichbar
- Captive-Portal-Phase: Kompromittierung der WLAN-Credentials während Setup
- Update-Mechanismus: Unauthentifizierter Update-Trigger, Rollback-Bypass, manipulierte Releases

## Was *nicht* als Security-Issue zählt (aber gerne als Bug)

- Crashes ohne Ausnutzbarkeit
- DoS durch extrem lange Inputs (akzeptieren wir als Bug, nicht als CVE)
- UI-Fehler ohne Daten-Exposition

## Historie

| Datum | Finding | Status |
|-------|---------|--------|
| 2026-04-16 | Pre-Beta-Audit (8 KRITISCH + 12 HOCH-Findings) | K1–K8 + H1–H3 behoben (Commits 5366ebe – 91a5109, 27f1585) |

Details: [`docs/PRE-BETA-AUDIT.md`](docs/PRE-BETA-AUDIT.md).

## Responsible Disclosure

Wir nennen Melder gern in den Release-Notes (mit deren Zustimmung). Bounty-Programm gibt es aktuell nicht — Tonado ist unfinanziert.
