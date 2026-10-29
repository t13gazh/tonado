# Security Policy

Tonado läuft auf Geräten, die Kinder bedienen. Security-Bugs sind uns deshalb wichtig — bitte hilf uns, sie diskret zu melden.

## Unterstützte Versionen

| Version | Status |
|---------|--------|
| `main` (Entwicklungsstand) | ✅ aktive Security-Fixes |
| `v0.4.x` (Beta, aktuell `v0.4.1-beta`) | ✅ aktive Security-Fixes |
| `v0.3.x` (Beta) | ⚠️ bitte auf `v0.4.x` updaten |
| ältere Alpha-Tags (`v0.2.x` und früher) | ⚠️ bitte auf Beta updaten |

## Einen Security-Bug melden

**Nicht im öffentlichen Issue-Tracker.** Bitte über das GitHub-Security-Advisory-Formular melden:

- <https://github.com/t13gazh/tonado/security/advisories/new>

Das Formular ist privat — nur Maintainer sehen den Bericht. GitHub sendet eine Bestätigung, sobald der Bericht eingegangen ist.

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
| 2026-04-16 | Pre-Beta-Audit (8 KRITISCH + 12 HOCH + 10 MITTEL) | Alle Findings außer den unten genannten behoben (K1–K3, K5–K8, H1–H12, M1–M10). Offen: K4 (Captive-Portal-First-Boot E2E auf echter Hardware — der Pi-Image-Pfad ist im Feldtest) und die Live-E2E-Prüfung von K5. Bewusst akzeptiert: Das Setup-WLAN „Tonado-Setup" ist offen (die Eltern haben vor der Einrichtung noch keine Zugangsdaten) und schließt sich erst mit dem Ende der Einrichtung; ein Inaktivitäts-Timeout dafür steht im Backlog. |

Details: [`docs/archive/PRE-BETA-AUDIT.md`](docs/archive/PRE-BETA-AUDIT.md).

## Responsible Disclosure

Wir nennen Melder gern in den Release-Notes (mit deren Zustimmung). Bounty-Programm gibt es aktuell nicht — Tonado ist unfinanziert.
