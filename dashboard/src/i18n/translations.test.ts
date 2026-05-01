import { describe, it, expect } from 'vitest'
import { translations } from './translations'

/**
 * Translation parity tests.
 *
 * The Translations interface enforces required keys at compile time, but it
 * does not catch:
 *   - Asymmetric optional keys (e.g. extra entries in steamReviewLabels)
 *   - Empty string values that pass the type check but render blank UI
 *
 * These runtime tests guard against both classes of bug.
 */

describe('translations', () => {
  it('has the same top-level keys for every locale', () => {
    const locales = Object.keys(translations) as Array<keyof typeof translations>
    expect(locales.length).toBeGreaterThanOrEqual(2)

    const referenceKeys = Object.keys(translations.en).sort()
    for (const locale of locales) {
      const keys = Object.keys(translations[locale]).sort()
      expect(keys).toEqual(referenceKeys)
    }
  })

  it('has no empty string values in any locale', () => {
    for (const [locale, t] of Object.entries(translations)) {
      for (const [key, value] of Object.entries(t)) {
        if (typeof value === 'string') {
          expect(value, `translations.${locale}.${key} must not be empty`).not.toBe('')
        }
      }
    }
  })

  it('has matching steamReviewLabels keys across locales', () => {
    const enKeys = Object.keys(translations.en.steamReviewLabels).sort()
    const esKeys = Object.keys(translations.es.steamReviewLabels).sort()

    expect(esKeys).toEqual(enKeys)
  })

  it('produces non-empty output for the timeLeft formatter in every locale', () => {
    for (const [locale, t] of Object.entries(translations)) {
      const result = t.timeLeft(2, 5, 30)
      expect(result, `translations.${locale}.timeLeft should produce non-empty output`).toBeTruthy()
      expect(result.length).toBeGreaterThan(3)
    }
  })

  it('produces non-empty output for the gamesTracked formatter in every locale', () => {
    for (const [locale, t] of Object.entries(translations)) {
      const result = t.gamesTracked(42)
      expect(result, `translations.${locale}.gamesTracked should mention the count`).toMatch(/42/)
    }
  })
})
