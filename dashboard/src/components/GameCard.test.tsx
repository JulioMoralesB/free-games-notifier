import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import GameCard from './GameCard'
import { I18nProvider } from '../i18n'
import type { GameItem } from '../types'

/**
 * GameCard component tests.
 *
 * Focus areas (each maps to a real-world regression we want to prevent):
 *  - Countdown logic: NaN guard, expired branch, "expires soon" branch
 *  - Expired styling: dimmed card class + overlay badge
 *  - Steam review chip filtering: empty / "no user reviews" labels are hidden
 *  - Locale switching: Steam labels render in the active locale
 *  - DLC badge: shown only for game_type === 'dlc'
 *  - Original price: shown only when present
 */

// Render helper that wraps the component in the i18n provider so useTranslation works.
function renderCard(game: GameItem, locale: 'en' | 'es' = 'en') {
  // Persist desired locale in localStorage before mounting; the provider reads it on init.
  try {
    localStorage.setItem('fgn_locale', locale)
  } catch {
    // ignore in environments where localStorage is unavailable
  }
  return render(
    <I18nProvider>
      <GameCard game={game} />
    </I18nProvider>,
  )
}

function makeGame(overrides: Partial<GameItem> = {}): GameItem {
  return {
    title: 'Sample Game',
    link: 'https://example.com/game',
    end_date: '',
    description: 'A short description',
    thumbnail: '',
    store: 'epic',
    ...overrides,
  }
}

beforeEach(() => {
  // Pin "now" to a known instant so countdown / expired branches are deterministic.
  // 2026-04-28T12:00:00Z
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-04-28T12:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
  try {
    localStorage.clear()
  } catch {
    // ignore
  }
})

// ---------------------------------------------------------------------------
// Countdown logic
// ---------------------------------------------------------------------------

describe('GameCard — countdown', () => {
  it('shows the time-left badge for an active promo > 6h away', () => {
    const game = makeGame({
      end_date: '2026-05-01T12:00:00Z', // 3 days from "now"
    })

    renderCard(game)

    // Countdown badge should display "3d Xh Ymin remaining" (en locale)
    const badge = screen.getByText(/\bleft\b/i)
    expect(badge).toBeInTheDocument()
    expect(badge.textContent).toMatch(/3d/)
  })

  it('shows the "expires soon" badge when < 6h are left', () => {
    const game = makeGame({
      end_date: '2026-04-28T16:00:00Z', // 4h from "now"
    })

    renderCard(game)

    // English copy: "Expires soon!"
    expect(screen.getByText(/expires soon/i)).toBeInTheDocument()
  })

  it('renders no countdown badge when end_date is in the past', () => {
    const game = makeGame({
      end_date: '2026-04-27T12:00:00Z', // 1 day before "now"
    })

    renderCard(game)

    expect(screen.queryByText(/\bleft\b/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/expires soon/i)).not.toBeInTheDocument()
  })

  it('does not crash and shows no countdown when end_date is empty', () => {
    // Regression for "Quedan NaNm" bug where NaN < Date.now() === false treated
    // empty end_dates as active, then rendered NaN in the countdown text.
    const game = makeGame({ end_date: '' })

    renderCard(game)

    expect(screen.queryByText(/\bleft\b/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument()
    // Date display should fall back to em-dash, not "Invalid Date"
    expect(screen.getByText(/—/)).toBeInTheDocument()
  })

  it('treats unparseable end_date strings as expired without crashing', () => {
    const game = makeGame({ end_date: 'not-a-date' })

    renderCard(game)

    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Expired card styling
// ---------------------------------------------------------------------------

describe('GameCard — expired state', () => {
  it('applies the card--expired class for past promos', () => {
    const game = makeGame({ end_date: '2026-04-27T12:00:00Z' })
    const { container } = renderCard(game)

    const article = container.querySelector('article.card')
    expect(article).toHaveClass('card--expired')
  })

  it('does not apply the expired class for active promos', () => {
    const game = makeGame({ end_date: '2026-05-01T12:00:00Z' })
    const { container } = renderCard(game)

    const article = container.querySelector('article.card')
    expect(article).not.toHaveClass('card--expired')
  })

  it('shows the expired badge overlay for past promos', () => {
    // Regression for the overlay showing the long "Was free until" string instead
    // of the short "Expired" badge. The badge text comes from t.expiredBadge.
    const game = makeGame({ end_date: '2026-04-27T12:00:00Z' })
    renderCard(game)

    expect(screen.getByText('Expired')).toBeInTheDocument()
  })

  it('localizes the expired badge in Spanish', () => {
    const game = makeGame({ end_date: '2026-04-27T12:00:00Z' })
    renderCard(game, 'es')

    expect(screen.getByText('Expirado')).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Review chips
// ---------------------------------------------------------------------------

describe('GameCard — review scores', () => {
  it('renders a Steam review chip with a localized label', () => {
    const game = makeGame({
      store: 'steam',
      review_scores: ['Mostly Positive'],
    })

    renderCard(game, 'es')

    // Spanish translation defined in translations.ts
    expect(screen.getByText(/Mayormente Positivo/i)).toBeInTheDocument()
  })

  it('renders a Metacritic chip with the score string preserved', () => {
    const game = makeGame({
      review_scores: ['Metascore: 87'],
    })

    renderCard(game)

    expect(screen.getByText(/Metascore: 87/)).toBeInTheDocument()
  })

  it('hides the review chip section when only "no user reviews" is present', () => {
    // Regression: "No user reviews" used to render as an unhelpful chip.
    const game = makeGame({
      store: 'steam',
      review_scores: ['No user reviews'],
    })

    const { container } = renderCard(game)

    expect(container.querySelector('.card-reviews')).toBeNull()
    expect(screen.queryByText(/no user reviews/i)).not.toBeInTheDocument()
  })

  it('renders nothing for review_scores when the array is empty', () => {
    const game = makeGame({ review_scores: [] })

    const { container } = renderCard(game)

    expect(container.querySelector('.card-reviews')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// DLC badge
// ---------------------------------------------------------------------------

describe('GameCard — DLC badge', () => {
  it('shows the DLC badge when game_type === "dlc"', () => {
    const game = makeGame({ game_type: 'dlc' })
    renderCard(game)

    expect(screen.getByText('DLC')).toBeInTheDocument()
  })

  it('omits the DLC badge for regular games', () => {
    const game = makeGame({ game_type: 'game' })
    renderCard(game)

    expect(screen.queryByText('DLC')).not.toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Original price
// ---------------------------------------------------------------------------

describe('GameCard — original price', () => {
  it('shows the original price label and value when set', () => {
    const game = makeGame({ original_price: '$19.99' })
    renderCard(game)

    expect(screen.getByText('$19.99')).toBeInTheDocument()
  })

  it('hides the original price section when not set', () => {
    const game = makeGame({ original_price: undefined })
    const { container } = renderCard(game)

    expect(container.querySelector('.card-price')).toBeNull()
  })
})
