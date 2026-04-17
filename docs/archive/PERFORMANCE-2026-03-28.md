# Tonado Performance-Optimierung — 2026-03-28

## Pi Zero W System-Optimierung (angewendet)

### Deaktivierte Dienste
| Dienst | RAM-Ersparnis | Grund |
|--------|--------------|-------|
| bluetooth | ~5 MB | Nicht benötigt (WiFi-only) |
| triggerhappy | ~2 MB | Hotkey-Daemon, nicht benötigt |
| ModemManager | ~11 MB | Kein Modem vorhanden |

**Avahi bleibt aktiv** — nötig für .local Hostname-Auflösung.

### Disk-Bereinigung
| Maßnahme | Ersparnis |
|----------|-----------|
| apt-get clean | ~76 MB |
| pip/setuptools/pkg_resources aus venv | ~25 MB |
| __pycache__ bereinigt | ~2 MB |
| Journal auf 5MB begrenzt | ~4 MB |
| **Gesamt** | **~107 MB** |

### Netzwerk
- IPv6 deaktiviert (spart RAM + reduziert Kernel-Last)

### Ergebnis
| Metrik | Vorher (Session-Start) | Nachher |
|--------|----------------------|---------|
| Disk frei | 142 MB (96%) | 382 MB (88%) |
| MPD CPU idle | 25% | 1.2% |
| Tonado CPU idle | 12% | ~10% |
| Free RAM | 99 MB | 117 MB |

## Weitere Einsparpotentiale (nicht angewendet)

| Maßnahme | Potentielle Ersparnis | Risiko |
|----------|----------------------|--------|
| /usr/share/locale/ entfernen | 143 MB | Pakete könnten brechen |
| /usr/share/doc/ entfernen | 69 MB | Gering |
| /usr/share/man/ entfernen | 27 MB | Gering |
| MPD mit minimalen Plugins neu kompilieren | ~50 MB RAM | Hoher Aufwand |
| WiFi Power-Management deaktivieren | Bessere Latenz | Höherer Stromverbrauch |
| SD-Karte auf 16+ GB upgraden | Löst Platzproblem komplett | Hardware-Kosten |

## Software-Performance-Fixes (angewendet)

| Fix | Impact |
|-----|--------|
| MPD httpd always_on=no | CPU -24%, RAM -11 MB |
| Gyro-Polling 50Hz → 20Hz | CPU-Last halbiert |
| elapsed_loop nur bei Playing | CPU ~2% gespart |
| Playlist nur bei Längenänderung laden | Weniger MPD-Queries |
| RSS-Feed Size-Limit 5MB | OOM-Schutz |
