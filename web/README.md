# Tonado Web-App

Frontend von Tonado: Svelte 5 + SvelteKit (`adapter-static`) + Tailwind CSS v4, als PWA ausgeliefert.

```sh
npm install
npm run dev      # Dev-Server mit Hot-Reload (Backend auf 127.0.0.1:8080)
npm run check    # svelte-check
npm run build    # statischer Build nach web/build/
```

`web/build/` ist im Repository eingecheckt, weil auf dem Pi kein Node installiert ist. Nach UI-Änderungen also lokal bauen und den Build mit committen.

Mehr dazu: [Entwicklung](../docs/fuer-entwickler/entwicklung.md) · [UI-Guidelines](../docs/fuer-entwickler/UI-GUIDELINES.md)
