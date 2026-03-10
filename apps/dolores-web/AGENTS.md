# AGENTS.md - dolores-web (Svelte/Capacitor)

Cross-platform web/mobile frontend for the Dolores assistant.

## Project Overview
- **Role:** Web and Mobile UI for text/voice interactions.
- **Tech Stack:** Svelte 5, Vite, TypeScript, Capacitor.
- **Framework:** Uses modern Svelte 5 APIs (Runes).

## Build and Run
- **Install deps:** `npm install` (within `apps/dolores-web/`).
- **Dev mode:** `npm run dev` or `vite`.
- **Build assets:** `npm run build`.
- **Mobile sync:** `npx cap sync`.

## Core Logic
- `src/lib/`: Svelte components and stores.
- `src/routes/`: App pages (routing via standard SvelteKit/Vite).
- `capacitor.config.ts`: Native iOS/Android bridge config.

## Testing Instructions
- **Run tests:** `npm run test` (Vitest).

## Code Style
- **Svelte 5 Runes:** Prefer `$state`, `$derived`, `$effect` over legacy Svelte 4 code.
- **Tailwind CSS:** Used for all styling.
- **TypeScript:** Use strict typing and interfaces for API responses.

## Deployment Notes
- Served via **Nginx** in the `Dockerfile`.
- Always check `proxy` settings in `vite.config.ts` for API backend.
