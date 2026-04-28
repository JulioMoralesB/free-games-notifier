import { useState, useEffect, useCallback } from 'react'
import type { GameItem, GamesHistoryResponse, SortField, SortDirection, StoreFilter, StatusFilter } from './types'
import GameCard from './components/GameCard'
import Pagination from './components/Pagination'
import LanguageSelector from './components/LanguageSelector'
import { useTranslation } from './i18n'

const PAGE_SIZE = 12

export default function App() {
  const { t } = useTranslation()
  const [games, setGames] = useState<GameItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [sortBy, setSortBy] = useState<SortField>('end_date')
  const [sortDir, setSortDir] = useState<SortDirection>('desc')
  const [storeFilter, setStoreFilter] = useState<StoreFilter>(() => {
    try {
      return (sessionStorage.getItem('storeFilter') as StoreFilter) || 'all'
    } catch {
      // sessionStorage unavailable (restricted privacy settings, etc.)
      return 'all'
    }
  })
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(() => {
    try {
      return (sessionStorage.getItem('statusFilter') as StatusFilter) || 'all'
    } catch {
      // sessionStorage unavailable
      return 'all'
    }
  })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const offset = (page - 1) * PAGE_SIZE

  // Persist filter selections across page refreshes within the same session
  useEffect(() => {
    try {
      sessionStorage.setItem('storeFilter', storeFilter)
    } catch {
      // sessionStorage unavailable — persistence is best-effort
    }
  }, [storeFilter])

  useEffect(() => {
    try {
      sessionStorage.setItem('statusFilter', statusFilter)
    } catch {
      // sessionStorage unavailable — persistence is best-effort
    }
  }, [statusFilter])

  const fetchGames = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const url =
        `/games/history?limit=${PAGE_SIZE}&offset=${offset}` +
        `&sort_by=${sortBy}&sort_dir=${sortDir}` +
        `&store=${storeFilter}&status=${statusFilter}`
      const res = await fetch(url)
      if (!res.ok) throw new Error(`Server responded with ${res.status}`)
      const data: GamesHistoryResponse = await res.json()
      setGames(data.games)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch games')
    } finally {
      setLoading(false)
    }
  }, [offset, sortBy, sortDir, storeFilter, statusFilter])

  useEffect(() => {
    fetchGames()
  }, [fetchGames])

  // Reset to page 1 when search changes
  const handleSearch = (value: string) => {
    setSearch(value)
    setPage(1)
  }

  const handleSort = (field: SortField) => {
    if (sortBy === field) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortBy(field)
      setSortDir('desc')
    }
    setPage(1)
  }

  const handleStoreFilter = (store: StoreFilter) => {
    setStoreFilter(store)
    setPage(1)
  }

  const handleStatusFilter = (status: StatusFilter) => {
    setStatusFilter(status)
    setPage(1)
  }

  // Client-side search filter — sorting and store/status filtering are done server-side
  const filtered = games.filter(g => {
    if (!search) return true
    const q = search.toLowerCase()
    return (
      g.title.toLowerCase().includes(q) ||
      g.description.toLowerCase().includes(q)
    )
  })

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const SortButton = ({
    field,
    label,
  }: {
    field: SortField
    label: string
  }) => (
    <button
      className={`sort-btn${sortBy === field ? ' active' : ''}`}
      onClick={() => handleSort(field)}
      aria-pressed={sortBy === field}
    >
      {label}
      {sortBy === field && (
        <span className="sort-icon">{sortDir === 'asc' ? ' ↑' : ' ↓'}</span>
      )}
    </button>
  )

  const getEmptyIcon = () => {
    if (search) return '🔍'
    if (statusFilter === 'active') return '🎮'
    if (statusFilter === 'expired') return '🏛️'
    return '🕹️'
  }

  const getEmptyMessage = () => {
    if (search) return t.noGamesMatch(search)
    if (statusFilter === 'active') return t.noActiveGames
    if (statusFilter === 'expired') return t.noExpiredGames
    return t.noGamesYet
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-inner">
          <div className="header-title">
            <span className="header-icon">🎮</span>
            <div>
              <h1>{t.headerTitle}</h1>
              <p>{t.headerSubtitle}</p>
            </div>
          </div>
          <div className="header-actions">
            {!loading && !error && (
              <div className="header-stats">
                <span className="stat-badge">{t.gamesTracked(total)}</span>
              </div>
            )}
            <LanguageSelector />
          </div>
        </div>
      </header>

      <main className="main">
        {/* Filter bar: status tabs + store pills */}
        <div className="filter-bar">
          <div className="filter-group">
            <span className="filter-label">{t.statusFilterLabel}</span>
            <div className="filter-tabs">
              {(['all', 'active', 'expired'] as StatusFilter[]).map(s => (
                <button
                  key={s}
                  className={`filter-tab${statusFilter === s ? ' active' : ''}`}
                  onClick={() => handleStatusFilter(s)}
                  aria-pressed={statusFilter === s}
                >
                  {s === 'all' ? t.statusAll : s === 'active' ? t.statusActive : t.statusExpired}
                </button>
              ))}
            </div>
          </div>

          <div className="filter-group">
            <span className="filter-label">{t.storeFilterLabel}</span>
            <div className="filter-tabs">
              {(['all', 'epic', 'steam'] as StoreFilter[]).map(s => (
                <button
                  key={s}
                  className={`filter-tab${storeFilter === s ? ' active' : ''}`}
                  onClick={() => handleStoreFilter(s)}
                  aria-pressed={storeFilter === s}
                >
                  {s === 'all' ? t.storeAll : s === 'epic' ? t.storeEpic : t.storeSteam}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="toolbar">
          <div className="search-wrapper">
            <span className="search-icon">🔍</span>
            <input
              type="text"
              className="search-input"
              placeholder={t.searchPlaceholder}
              value={search}
              onChange={e => handleSearch(e.target.value)}
              aria-label={t.searchAriaLabel}
            />
            {search && (
              <button
                className="clear-btn"
                onClick={() => handleSearch('')}
                aria-label={t.clearSearchAriaLabel}
              >
                ✕
              </button>
            )}
          </div>
          <div className="sort-controls">
            <span className="sort-label">{t.sortBy}</span>
            <SortButton field="end_date" label={t.sortByDate} />
            <SortButton field="title" label={t.sortByTitle} />
          </div>
        </div>

        {loading && (
          <div className="state-container">
            <div className="spinner" />
            <p>{t.loadingGames}</p>
          </div>
        )}

        {error && (
          <div className="state-container error">
            <span className="state-icon">⚠️</span>
            <p>{error}</p>
            <button className="retry-btn" onClick={fetchGames}>
              {t.errorRetry}
            </button>
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <div className="state-container">
            <span className="state-icon">{getEmptyIcon()}</span>
            <p>{getEmptyMessage()}</p>
          </div>
        )}

        {!loading && !error && filtered.length > 0 && (
          <div className="grid">
            {filtered.map((game, i) => (
              <GameCard key={game.link || `${game.title}-${i}`} game={game} />
            ))}
          </div>
        )}

        {!loading && !error && totalPages > 1 && (
          <Pagination
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
          />
        )}
      </main>

      <footer className="footer">
        <p>{t.footerText}</p>
      </footer>
    </div>
  )
}
