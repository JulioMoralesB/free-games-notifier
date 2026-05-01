/**
 * Vitest setup — runs once before all test files.
 *
 * - Loads jest-dom matchers (e.g. toBeInTheDocument, toHaveClass) so they are
 *   available on every `expect(...)`.
 * - Cleans up the DOM between tests (handled automatically by RTL when
 *   `globals: true` is set in vitest config — but we make it explicit here).
 */

import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
})
