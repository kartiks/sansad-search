import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { STATUS_ENDPOINT, getSourceLabel } from '../lib/constants.js'
import {
  formatCount,
  formatLongDate,
  formatCoverage,
} from '../lib/statusFormat.js'

// Render order for the per-source table: CA, Lok Sabha, Rajya Sabha.
const PANEL_SOURCES = [
  { key: 'ca', code: 'CA' },
  { key: 'ls', code: 'LS' },
  { key: 'rs', code: 'RS' },
]

const ZERO_SOURCE_TEXT = '0 records – not yet indexed'

// A payload is usable only when status === 'ok' and the per-source map exists.
// Anything else (status:'unavailable', missing sources, fetch failure) renders
// the "Status unavailable" message in place of counts and dates.
function isUsable(status) {
  return Boolean(status && status.status === 'ok' && status.sources)
}

export default function IndexingStatusPage() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetch(STATUS_ENDPOINT)
      .then((r) => r.json())
      .then((s) => {
        if (cancelled) return
        setStatus(s)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setFailed(true)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const usable = !failed && isUsable(status)

  return (
    <div className="status-page">
      <header className="status-page-header" role="banner">
        <div className="status-page-header-inner">
          <Link to="/" className="wordmark-header">
            SansadSearch
          </Link>
        </div>
      </header>

      <main className="status-page-content">
        <h1 className="status-panel-title">Search Index Status</h1>

        {loading && (
          <p className="status-panel-loading" data-testid="status-panel-loading">
            Loading index status…
          </p>
        )}

        {!loading && !usable && (
          <p
            className="status-panel-unavailable"
            data-testid="status-panel-unavailable"
          >
            Status unavailable
          </p>
        )}

        {!loading && usable && (
          <div className="status-panel" data-testid="status-panel">
            <p className="status-panel-total" data-testid="status-panel-total">
              Total records indexed: {formatCount(status.total_records)}
            </p>

            <table className="status-panel-table" data-testid="status-panel-table">
              <tbody>
                {PANEL_SOURCES.map(({ key, code }) => {
                  const src = (status.sources && status.sources[key]) || {}
                  const count = src.count || 0
                  return (
                    <tr key={key} data-testid={`status-row-${key}`}>
                      <th scope="row" className="status-row-label">
                        {getSourceLabel(code)}
                      </th>
                      {count === 0 ? (
                        <td className="status-row-empty" colSpan={2}>
                          {ZERO_SOURCE_TEXT}
                        </td>
                      ) : (
                        <>
                          <td className="status-row-count">
                            {formatCount(count)} records
                          </td>
                          <td className="status-row-coverage">
                            {formatCoverage(src.date_from, src.date_to)}
                          </td>
                        </>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>

            <p
              className="status-panel-updated"
              data-testid="status-panel-updated"
            >
              Last updated: {formatLongDate(status.last_updated)}
            </p>
          </div>
        )}

        <p className="status-page-back">
          <Link to="/" data-testid="status-page-home-link">
            ← Back to search
          </Link>
        </p>
      </main>
    </div>
  )
}
