# Dashboard — Developer Guide

The dashboard is a React/TypeScript SPA built with Vite. Source lives in `dashboard/`. When deploying via Docker, the Dockerfile builds it automatically in a multi-stage build (Node.js builder → Python runtime).

## Building locally

```bash
cd dashboard
npm install
npm run build   # output goes to dashboard/dist/
```

Then start the Python service normally — FastAPI will detect and serve `dashboard/dist/`.

## Hot-reload development

```bash
# Terminal 1 — Python API
python main.py

# Terminal 2 — Vite dev server (proxies /games → localhost:8000)
cd dashboard
npm install
npm run dev     # http://localhost:5173/dashboard/
```

## Testing

The dashboard uses [Vitest](https://vitest.dev/) with [React Testing Library](https://testing-library.com/docs/react-testing-library/intro). Tests live alongside the code they cover (`*.test.ts` / `*.test.tsx`).

```bash
cd dashboard
npm test           # one-shot run (used in CI)
npm run test:watch # interactive watch mode for development
```

Current coverage focuses on `GameCard` (countdown logic, expired styling, review-chip filtering, locale switching) and `translations.ts` (key parity across locales). When adding a new component, prefer behavior-driven tests using `screen.getByText` / `getByRole` over snapshot tests.

## Language support (i18n)

The dashboard auto-detects the visitor's preferred language from `navigator.languages` and falls back to English. A language selector in the header lets users switch manually; the choice is persisted in `localStorage`.

### Adding a new language

All translation strings live in `dashboard/src/i18n/translations.ts`.

1. **Add your locale code** to the `Locale` union type:
   ```ts
   export type Locale = 'en' | 'es' | 'fr'   // ← add 'fr'
   ```

2. **Create a translation object** implementing the `Translations` interface:
   ```ts
   const fr: Translations = {
     headerTitle: 'Historique des jeux gratuits',
     headerSubtitle: 'Toutes les promotions de jeux gratuits suivies',
     gamesTracked: (count) => `${count} jeux suivis`,
     // … fill in all remaining keys …
   }
   ```

3. **Register it** in the `translations` map and add its BCP 47 tag:
   ```ts
   export const translations: Record<Locale, Translations> = { en, es, fr }

   export const localeBcp47: Record<Locale, string> = {
     en: 'en-US',
     es: 'es-ES',
     fr: 'fr-FR',
   }
   ```

4. **Add a label** in `dashboard/src/components/LanguageSelector.tsx`:
   ```ts
   const LOCALE_LABELS: Record<Locale, string> = {
     en: '🇺🇸 EN',
     es: '🇲🇽 ES',
     fr: '🇫🇷 FR',
   }
   ```

5. Rebuild the dashboard (`npm run build`) — no other changes required.

TypeScript will report missing translation keys at compile time.
