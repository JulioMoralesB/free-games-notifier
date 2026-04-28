import { useState, useEffect } from 'react'
import type { GameItem } from '../types'
import { useTranslation } from '../i18n'
import type { Locale } from '../i18n/translations'
import { localeBcp47 } from '../i18n/translations'

const STORE_META: Record<string, { label: string; icon: string }> = {
  epic:  { label: 'Epic Games', icon: '🏪' },
  steam: { label: 'Steam',      icon: '🎮' },
}

function getStoreMeta(store: string) {
  return STORE_META[store] ?? { label: store, icon: '🏪' }
}

/** Steam user-review label → display emoji */
const STEAM_REVIEW_EMOJIS: Record<string, string> = {
  'overwhelmingly positive': '🔥',
  'very positive':           '😄',
  'mostly positive':         '👍',
  'positive':                '👍',
  'mixed':                   '😐',
  'mostly negative':         '👎',
  'negative':                '👎',
  'very negative':           '😞',
  'overwhelmingly negative': '💀',
}

/**
 * Steam labels that indicate no meaningful score data — omitted from the UI
 * rather than shown as an unhelpful chip.
 */
const STEAM_NO_DATA_LABELS = new Set([
  'no user reviews',
  'no reviews',
])

/** Metacritic score value → display emoji */
function metacriticEmoji(score: number): string {
  if (score >= 90) return '🏆'
  if (score >= 75) return '⭐'
  if (score >= 61) return '👍'
  if (score >= 40) return '⚖️'
  return '👎'
}

interface TimeLeft {
  days: number
  hours: number
  minutes: number
}

function calcTimeLeft(endDate: string): TimeLeft | null {
  if (!endDate) return null
  const ms = new Date(endDate).getTime()
  if (isNaN(ms)) return null
  const diff = ms - Date.now()
  if (diff <= 0) return null
  const days    = Math.floor(diff / 86_400_000)
  const hours   = Math.floor((diff % 86_400_000) / 3_600_000)
  const minutes = Math.floor((diff % 3_600_000) / 60_000)
  return { days, hours, minutes }
}

interface Props {
  game: GameItem
}

function formatDate(iso: string, locale: Locale): string {
  if (!iso) return '—'
  try {
    const date = new Date(iso)
    if (isNaN(date.getTime())) return '—'
    return new Intl.DateTimeFormat(localeBcp47[locale], {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZoneName: 'short',
    }).format(date)
  } catch {
    return iso
  }
}

export default function GameCard({ game }: Props) {
  const { t, locale } = useTranslation()
  const [imgError, setImgError] = useState(false)
  const [timeLeft, setTimeLeft] = useState<TimeLeft | null>(() => calcTimeLeft(game.end_date))

  // Treat missing or unparseable end_date as expired
  const endMs = game.end_date ? new Date(game.end_date).getTime() : NaN
  const isPastPromotion = isNaN(endMs) || endMs < Date.now()
  const storeMeta = getStoreMeta(game.store)
  const isDlc = game.game_type === 'dlc'

  // Countdown: update every minute for active promotions
  useEffect(() => {
    if (isPastPromotion) return
    const timer = setInterval(() => {
      setTimeLeft(calcTimeLeft(game.end_date))
    }, 60_000)
    return () => clearInterval(timer)
  }, [game.end_date, isPastPromotion])

  return (
    <article className={`card${isPastPromotion ? ' card--expired' : ''}`}>
      <div className="card-image-wrapper">
        {isDlc && (
          <span className="card-dlc-badge" aria-label={t.dlcBadge}>
            {t.dlcBadge}
          </span>
        )}
        {isPastPromotion && (
          <div className="card-expired-overlay" aria-hidden="true">
            <span className="card-expired-label">
              {t.expiredBadge}
            </span>
          </div>
        )}
        {game.thumbnail && !imgError ? (
          <img
            className="card-image"
            src={game.thumbnail}
            alt={game.title}
            loading="lazy"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="card-image-fallback" aria-hidden="true">
            🎮
          </div>
        )}
      </div>

      <div className="card-body">
        <h2 className="card-title" title={game.title}>
          {game.title}
        </h2>

        {game.description && (
          <p className="card-description" title={game.description}>
            {game.description}
          </p>
        )}

        {/* Review scores — skip non-informative Steam labels like "No user reviews" */}
        {game.review_scores && game.review_scores.some(s =>
          s.startsWith('Metascore: ') || !STEAM_NO_DATA_LABELS.has(s.toLowerCase())
        ) && (
          <div className="card-reviews">
            {game.review_scores
              .filter(score =>
                score.startsWith('Metascore: ') || !STEAM_NO_DATA_LABELS.has(score.toLowerCase())
              )
              .map((score, i) => {
                if (score.startsWith('Metascore: ')) {
                  const val = parseInt(score.replace('Metascore: ', ''), 10)
                  return (
                    <span key={i} className="card-review card-review--meta">
                      {metacriticEmoji(val)} {score}
                    </span>
                  )
                }
                const key = score.toLowerCase()
                const emoji = STEAM_REVIEW_EMOJIS[key] ?? '🎮'
                const label = t.steamReviewLabels[key] ?? score
                return (
                  <span key={i} className="card-review card-review--steam">
                    {emoji} {label}
                  </span>
                )
              })}
          </div>
        )}

        <div className="card-meta">
          {/* Original price */}
          {game.original_price && (
            <div className="card-price">
              <span className="card-price-label">{t.originalPrice}</span>
              <span className="card-price-value">{game.original_price}</span>
            </div>
          )}

          {/* Countdown or date */}
          <div className="card-date">
            <span className="card-date-icon">📅</span>
            <span>
              {isPastPromotion ? t.wasFreeUntil : t.freeUntil}:{' '}
              {formatDate(game.end_date, locale)}
            </span>
          </div>

          {/* Active countdown badge */}
          {!isPastPromotion && timeLeft && (
            <div className="card-countdown">
              {timeLeft.days === 0 && timeLeft.hours < 6
                ? t.expiresSoon
                : t.timeLeft(timeLeft.days, timeLeft.hours, timeLeft.minutes)}
            </div>
          )}

          <span className="card-store">{storeMeta.icon} {storeMeta.label}</span>
        </div>
      </div>

      <div className="card-footer">
        <a
          href={game.link}
          className="card-link"
          target="_blank"
          rel="noopener noreferrer"
        >
          {t.viewOnStore(storeMeta.label)}
        </a>
      </div>
    </article>
  )
}
