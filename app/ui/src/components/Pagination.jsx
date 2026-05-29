import React from 'react'

export const MAX_TOTAL_PAGE_COUNT_DISPLAY = 500

export function formatResultCount(total) {
  if (total == null) return ''
  const n = Number(total)
  if (!Number.isFinite(n) || n <= 0) return '0 results'
  if (n >= 10000) return '10,000+ results'
  return `${n.toLocaleString('en-US')} results`
}

export function buildPageList(currentPage, totalPages) {
  const pages = new Set()
  const current = Math.max(1, currentPage)
  const total = Math.max(1, totalPages)

  pages.add(1)
  pages.add(total)
  pages.add(current)
  if (current - 1 >= 1) pages.add(current - 1)
  if (current + 1 <= total) pages.add(current + 1)

  const sorted = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b)

  const out = []
  let prev = 0
  for (const p of sorted) {
    if (p - prev > 1) out.push('…')
    out.push(p)
    prev = p
  }
  return out
}

export default function Pagination({ currentPage, totalPages, onPageChange }) {
  const current = Math.max(1, Number(currentPage) || 1)
  const total = Math.max(1, Number(totalPages) || 1)

  if (total <= 1) return null

  const pages = buildPageList(current, total)
  const showTotalPageHint = total <= MAX_TOTAL_PAGE_COUNT_DISPLAY

  const goTo = (p) => {
    if (typeof onPageChange === 'function' && p !== current) onPageChange(p)
  }

  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        className="pagination-btn"
        onClick={() => goTo(current - 1)}
        disabled={current <= 1}
        aria-label="Previous page"
      >
        Previous
      </button>

      {pages.map((p, i) =>
        p === '…' ? (
          <span key={`ell-${i}`} className="pagination-ellipsis" aria-hidden="true">
            …
          </span>
        ) : (
          <button
            type="button"
            key={`page-${p}`}
            className={`pagination-btn${p === current ? ' is-current' : ''}`}
            aria-current={p === current ? 'page' : undefined}
            onClick={() => goTo(p)}
          >
            {p}
          </button>
        )
      )}

      <button
        type="button"
        className="pagination-btn"
        onClick={() => goTo(current + 1)}
        disabled={current >= total}
        aria-label="Next page"
      >
        Next
      </button>

      {showTotalPageHint && (
        <span className="pagination-ellipsis" data-testid="total-pages-hint">
          of {total.toLocaleString('en-US')}
        </span>
      )}
    </nav>
  )
}
