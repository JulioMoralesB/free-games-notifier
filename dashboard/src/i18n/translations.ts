export type Locale = 'en' | 'es'

export interface Translations {
  // Header
  headerTitle: string
  headerSubtitle: string
  gamesTracked: (count: number) => string

  // Toolbar
  searchPlaceholder: string
  searchAriaLabel: string
  clearSearchAriaLabel: string
  sortBy: string
  sortByDate: string
  sortByTitle: string

  // Filter bar — status
  statusFilterLabel: string
  statusAll: string
  statusActive: string
  statusExpired: string

  // Filter bar — store
  storeFilterLabel: string
  storeAll: string
  storeEpic: string
  storeSteam: string

  // Loading / error / empty states
  loadingGames: string
  errorRetry: string
  noGamesMatch: (query: string) => string
  noGamesYet: string
  noActiveGames: string
  noExpiredGames: string

  // GameCard
  wasFreeUntil: string
  freeUntil: string
  viewOnStore: (storeName: string) => string
  dlcBadge: string
  expiredBadge: string
  originalPrice: string
  timeLeft: (days: number, hours: number, minutes: number) => string
  expiresSoon: string

  // Pagination
  paginationNavAriaLabel: string
  previousPage: string
  nextPage: string
  pageN: (n: number) => string

  // Footer
  footerText: string

  // Language selector
  languageLabel: string

  /** Localized display text for Steam user-review labels (keyed by lowercase English label). */
  steamReviewLabels: Record<string, string>
}

const en: Translations = {
  // Header
  headerTitle: 'Free Games History',
  headerSubtitle: 'All previously tracked free game promotions',
  gamesTracked: (count) => `${count} ${count === 1 ? 'game' : 'games'} tracked`,

  // Toolbar
  searchPlaceholder: 'Search by title or description…',
  searchAriaLabel: 'Search games',
  clearSearchAriaLabel: 'Clear search',
  sortBy: 'Sort by:',
  sortByDate: 'Date',
  sortByTitle: 'Title',

  // Filter bar — status
  statusFilterLabel: 'Status:',
  statusAll: 'All',
  statusActive: 'Currently Free',
  statusExpired: 'Previously Free',

  // Filter bar — store
  storeFilterLabel: 'Store:',
  storeAll: 'All',
  storeEpic: 'Epic',
  storeSteam: 'Steam',

  // Loading / error / empty states
  loadingGames: 'Loading games…',
  errorRetry: 'Retry',
  noGamesMatch: (query) => `No games match "${query}"`,
  noGamesYet: 'No games in history yet.',
  noActiveGames: 'No free games currently available.',
  noExpiredGames: 'No previously free games found.',

  // GameCard
  wasFreeUntil: 'Was free until',
  freeUntil: 'Free until',
  viewOnStore: (storeName) => `View on ${storeName} →`,
  dlcBadge: 'DLC',
  expiredBadge: 'Expired',
  originalPrice: 'Original price:',
  timeLeft: (days, hours, minutes) =>
    days > 0
      ? `⏰ ${days}d ${hours}h left`
      : hours > 0
        ? `⏰ ${hours}h ${minutes}m left`
        : `⏰ ${minutes}m left`,
  expiresSoon: '⏰ Expires soon!',

  // Pagination
  paginationNavAriaLabel: 'Pagination',
  previousPage: 'Previous page',
  nextPage: 'Next page',
  pageN: (n) => `Page ${n}`,

  // Footer
  footerText: 'Free Games Notifier — Game history dashboard',

  // Language selector
  languageLabel: 'Language',

  steamReviewLabels: {
    'overwhelmingly positive': 'Overwhelmingly Positive',
    'very positive':           'Very Positive',
    'mostly positive':         'Mostly Positive',
    'positive':                'Positive',
    'mixed':                   'Mixed',
    'mostly negative':         'Mostly Negative',
    'negative':                'Negative',
    'very negative':           'Very Negative',
    'overwhelmingly negative': 'Overwhelmingly Negative',
  },
}

const es: Translations = {
  // Header
  headerTitle: 'Historial de Juegos Gratis',
  headerSubtitle: 'Todas las promociones de juegos gratis registradas',
  gamesTracked: (count) => `${count} ${count === 1 ? 'juego' : 'juegos'} registrados`,

  // Toolbar
  searchPlaceholder: 'Buscar por título o descripción…',
  searchAriaLabel: 'Buscar juegos',
  clearSearchAriaLabel: 'Limpiar búsqueda',
  sortBy: 'Ordenar por:',
  sortByDate: 'Fecha',
  sortByTitle: 'Título',

  // Filter bar — status
  statusFilterLabel: 'Estado:',
  statusAll: 'Todos',
  statusActive: 'Gratis Ahora',
  statusExpired: 'Anteriores',

  // Filter bar — store
  storeFilterLabel: 'Tienda:',
  storeAll: 'Todas',
  storeEpic: 'Epic',
  storeSteam: 'Steam',

  // Loading / error / empty states
  loadingGames: 'Cargando juegos…',
  errorRetry: 'Reintentar',
  noGamesMatch: (query) => `No se encontraron juegos para "${query}"`,
  noGamesYet: 'Aún no hay juegos en el historial.',
  noActiveGames: 'No hay juegos gratis disponibles en este momento.',
  noExpiredGames: 'No se encontraron juegos anteriormente gratuitos.',

  // GameCard
  wasFreeUntil: 'Estuvo gratis hasta el',
  freeUntil: 'Gratis hasta el',
  viewOnStore: (storeName) => `Ver en ${storeName} →`,
  dlcBadge: 'DLC',
  expiredBadge: 'Expirado',
  originalPrice: 'Precio original:',
  timeLeft: (days, hours, minutes) =>
    days > 0
      ? `⏰ Quedan ${days}d ${hours}h`
      : hours > 0
        ? `⏰ Quedan ${hours}h ${minutes}m`
        : `⏰ Quedan ${minutes}m`,
  expiresSoon: '⏰ ¡Expira pronto!',

  // Pagination
  paginationNavAriaLabel: 'Paginación',
  previousPage: 'Página anterior',
  nextPage: 'Página siguiente',
  pageN: (n) => `Página ${n}`,

  // Footer
  footerText: 'Free Games Notifier — Panel de historial de juegos',

  // Language selector
  languageLabel: 'Idioma',

  steamReviewLabels: {
    'overwhelmingly positive': 'Abrumadoramente Positivo',
    'very positive':           'Muy Positivo',
    'mostly positive':         'Mayormente Positivo',
    'positive':                'Positivo',
    'mixed':                   'Mixto',
    'mostly negative':         'Mayormente Negativo',
    'negative':                'Negativo',
    'very negative':           'Muy Negativo',
    'overwhelmingly negative': 'Abrumadoramente Negativo',
  },
}

export const translations: Record<Locale, Translations> = { en, es }

/**
 * Maps our short `Locale` codes to full BCP 47 language tags accepted by
 * `Intl.DateTimeFormat` (e.g. 'en' → 'en-US', 'es' → 'es-ES').
 * Add an entry here when registering a new locale.
 */
export const localeBcp47: Record<Locale, string> = {
  en: 'en-US',
  es: 'es-ES',
}

/**
 * Detect the preferred locale from the browser's language settings.
 * Falls back to 'en' if no supported locale is found.
 *
 * To add a new language:
 *   1. Add a new key to the `Locale` union type above.
 *   2. Create a translation object implementing `Translations`.
 *   3. Register it in the `translations` map.
 */
export function detectLocale(): Locale {
  const supported = Object.keys(translations) as Locale[]
  const preferredLanguages =
    navigator.languages && navigator.languages.length > 0
      ? navigator.languages
      : [navigator.language]
  for (const lang of preferredLanguages) {
    const base = lang.split('-')[0].toLowerCase()
    if (supported.includes(base as Locale)) return base as Locale
  }
  return 'en'
}
