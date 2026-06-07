import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'

import { useSearch, buildSearchRequestBody, SEARCH_ENDPOINT } from '../hooks/useSearch.js'
import { useCookieHistory } from '../hooks/useCookieHistory.js'
import { useSavedSearches, sanitizeStoredFilters } from '../hooks/useSavedSearches.js'
import {
  ALL_SOURCES,
  ALL_PROCEEDING_TYPES,
  SOURCE_LABELS,
  PROCEEDING_TYPE_LABELS,
  SEARCH_PLACEHOLDER,
  SORT_OPTIONS,
  VALIDATION_SHORT,
  MIN_QUERY_CHARS,
  MAX_QUERY_LEN,
  ERROR_STATE_TITLE,
  ERROR_STATE_BODY,
  NO_RESULTS_BODY,
} from '../lib/constants.js'
import {
  defaultFilterState,
  isDefaultFilterState,
} from '../lib/filterState.js'
import { formatExpansionNotice, hasExpansion } from '../lib/expansionNotice.js'
import ResultCard from '../components/ResultCard.jsx'
import SearchDebugPanel from '../components/SearchDebugPanel.jsx'
import Pagination, { formatResultCount } from '../components/Pagination.jsx'
import SkeletonCard from '../components/SkeletonCard.jsx'
import FilterChip from '../components/FilterChip.jsx'
import AdvancedSearchModal from '../components/AdvancedSearchModal.jsx'
import RecentSearchesDropdown from '../components/RecentSearchesDropdown.jsx'
import SavedSearchesPanel from '../components/SavedSearchesPanel.jsx'
import Toast from '../components/Toast.jsx'

const VALID_SORTS = new Set(['relevance', 'chronological', 'reverse_chronological'])

function clampPage(raw) {
  const n = Number(raw)
  if (!Number.isFinite(n) || n < 1) return 1
  return Math.floor(n)
}

function readUrl(params) {
  const q = (params.get('q') || '').slice(0, MAX_QUERY_LEN)
  const rawSort = params.get('sort')
  const sort = VALID_SORTS.has(rawSort) ? rawSort : 'relevance'
  const page = clampPage(params.get('page') || '1')
  return { q, sort, page }
}

function arraysMatch(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false
  if (a.length !== b.length) return false
  const sa = [...a].sort()
  const sb = [...b].sort()
  return sa.every((v, i) => v === sb[i])
}

function buildActiveChips(filters) {
  const chips = []

  if (!arraysMatch(filters.sources, ALL_SOURCES)) {
    const label = filters.sources.map((s) => SOURCE_LABELS[s] || s).join(' · ')
    chips.push({ key: 'sources', label })
  }

  if (filters.date_from || filters.date_to) {
    let label
    if (filters.date_from && filters.date_to) {
      label = `${filters.date_from} – ${filters.date_to}`
    } else if (filters.date_from) {
      label = `From ${filters.date_from}`
    } else {
      label = `To ${filters.date_to}`
    }
    chips.push({ key: 'date', label })
  }

  if (filters.speaker && filters.speaker.trim()) {
    chips.push({ key: 'speaker', label: `Speaker: ${filters.speaker.trim()}` })
  }

  if (filters.session && filters.session.trim()) {
    chips.push({ key: 'session', label: `Session: ${filters.session.trim()}` })
  }

  if (!arraysMatch(filters.proceeding_types, ALL_PROCEEDING_TYPES)) {
    const label = filters.proceeding_types
      .map((pt) => PROCEEDING_TYPE_LABELS[pt] || pt)
      .join(' · ')
    chips.push({ key: 'proceeding_types', label })
  }

  return chips
}

export default function Results() {
  const navigate = useNavigate()
  const location = useLocation()
  const [params, setParams] = useSearchParams()
  const { q: urlQuery, sort: urlSort, page: urlPage } = readUrl(params)

  const [inputValue, setInputValue] = useState(urlQuery)
  const [validation, setValidation] = useState('')
  const [dropdownVisible, setDropdownVisible] = useState(false)
  const [savedPanelOpen, setSavedPanelOpen] = useState(false)
  const [toast, setToast] = useState('')

  const [filters, setFilters] = useState(() => {
    const stateFilters = location.state?.filters
    if (stateFilters && !isDefaultFilterState(stateFilters)) return stateFilters
    return defaultFilterState()
  })

  const [modalOpen, setModalOpen] = useState(false)

  const { entries: recentEntries, cookiesEnabled, recordSearch, deleteEntry: deleteRecent, clearAll: clearRecent } = useCookieHistory()
  const { entries: savedEntries, atLimit, saveSearch, deleteEntry: deleteSaved, renameEntry } = useSavedSearches()

  useEffect(() => {
    setInputValue(urlQuery)
    setValidation('')
  }, [urlQuery])

  const enabled = urlQuery.trim().length > 0

  // F10: debug mode activated by ?debug=1 or ?debug=true in the URL
  const debugMode = params.get('debug') === '1' || params.get('debug') === 'true'

  const { data, error, loading, retry } = useSearch({
    query: urlQuery,
    filters,
    sort: urlSort,
    page: urlPage,
    debug: debugMode,
    enabled,
  })

  useEffect(() => {
    if (!enabled) navigate('/', { replace: true })
  }, [enabled, navigate])

  const onSubmit = (e) => {
    if (e && typeof e.preventDefault === 'function') e.preventDefault()
    const cleaned = (inputValue || '').slice(0, MAX_QUERY_LEN)
    const trimmedCount = cleaned.replace(/\s+/g, '').length
    if (trimmedCount < MIN_QUERY_CHARS) {
      setValidation(VALIDATION_SHORT)
      return
    }
    setValidation('')
    setDropdownVisible(false)
    recordSearch(cleaned.trim())
    const next = new URLSearchParams()
    next.set('q', cleaned.trim())
    next.set('page', '1')
    if (urlSort && urlSort !== 'relevance') next.set('sort', urlSort)
    setParams(next, { state: { filters } })
  }

  const onInputChange = (e) => {
    setInputValue(e.target.value)
    if (validation) setValidation('')
    if (e.target.value.length > 0) setDropdownVisible(false)
    else if (cookiesEnabled) setDropdownVisible(true)
  }

  const onInputFocus = () => {
    if (cookiesEnabled && inputValue.length === 0) setDropdownVisible(true)
  }

  const onSortChange = (e) => {
    const nextSort = e.target.value
    const next = new URLSearchParams(params)
    next.set('q', urlQuery)
    next.set('page', '1')
    if (nextSort === 'relevance') {
      next.delete('sort')
    } else {
      next.set('sort', nextSort)
    }
    setParams(next, { state: { filters } })
  }

  const onPageChange = (nextPage) => {
    const next = new URLSearchParams(params)
    next.set('q', urlQuery)
    next.set('page', String(nextPage))
    if (urlSort && urlSort !== 'relevance') {
      next.set('sort', urlSort)
    }
    setParams(next, { state: { filters } })
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }

  const onModalApply = (newFilters) => {
    setFilters(newFilters)
    setModalOpen(false)
    const next = new URLSearchParams(params)
    next.set('q', inputValue.trim() || urlQuery)
    next.set('page', '1')
    if (urlSort && urlSort !== 'relevance') next.set('sort', urlSort)
    else next.delete('sort')
    setParams(next, { state: { filters: newFilters } })
  }

  const removeFilter = (dimension) => {
    let newFilters
    switch (dimension) {
      case 'sources':
        newFilters = { ...filters, sources: [...ALL_SOURCES] }
        break
      case 'date':
        newFilters = { ...filters, date_from: null, date_to: null }
        break
      case 'speaker':
        newFilters = { ...filters, speaker: null }
        break
      case 'session':
        newFilters = { ...filters, session: null }
        break
      case 'proceeding_types':
        newFilters = { ...filters, proceeding_types: [...ALL_PROCEEDING_TYPES] }
        break
      default:
        newFilters = filters
    }
    setFilters(newFilters)
    const next = new URLSearchParams(params)
    next.set('q', urlQuery)
    next.set('page', '1')
    if (urlSort && urlSort !== 'relevance') next.set('sort', urlSort)
    else next.delete('sort')
    setParams(next, { state: { filters: newFilters } })
  }

  const clearAllFilters = () => {
    const newFilters = defaultFilterState()
    setFilters(newFilters)
    const next = new URLSearchParams(params)
    next.set('q', urlQuery)
    next.set('page', '1')
    if (urlSort && urlSort !== 'relevance') next.set('sort', urlSort)
    else next.delete('sort')
    setParams(next, { state: { filters: newFilters } })
  }

  const handleRecentSelect = (query) => {
    setDropdownVisible(false)
    setInputValue(query)
    recordSearch(query)
    const next = new URLSearchParams()
    next.set('q', query)
    next.set('page', '1')
    const newFilters = defaultFilterState()
    setFilters(newFilters)
    setParams(next, { state: { filters: newFilters } })
  }

  const handleSavedRun = (entry) => {
    setSavedPanelOpen(false)
    const sanitized = sanitizeStoredFilters(entry.filters)
    recordSearch(entry.query)
    setFilters(sanitized)
    setInputValue(entry.query)
    const next = new URLSearchParams()
    next.set('q', entry.query)
    next.set('page', '1')
    setParams(next, { state: { filters: sanitized } })
  }

  const handleSaveCurrentSearch = () => {
    saveSearch({ query: urlQuery, filters, name: urlQuery })
  }

  const activeChips = useMemo(() => buildActiveChips(filters), [filters])

  return (
    <div className="results-page">
      <header className="results-header" role="banner">
        <div className="results-header-inner">
          <Link to="/" className="wordmark-header">
            SansadSearch
          </Link>

          <form
            onSubmit={onSubmit}
            role="search"
            aria-label="Site search"
            className="results-header-search"
          >
            <div className="search-bar-wrap">
              <div className="search-bar compact">
                <input
                  type="text"
                  className="search-bar-input"
                  placeholder={SEARCH_PLACEHOLDER}
                  aria-label="Search parliamentary records"
                  value={inputValue}
                  onChange={onInputChange}
                  onFocus={onInputFocus}
                  maxLength={MAX_QUERY_LEN}
                  data-testid="results-search-input"
                />
                <button
                  type="submit"
                  className="search-submit"
                  aria-label="Submit search"
                  data-testid="results-search-submit"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 20 20"
                    fill="none"
                    aria-hidden="true"
                  >
                    <circle
                      cx="9"
                      cy="9"
                      r="6"
                      stroke="currentColor"
                      strokeWidth="2"
                    />
                    <path
                      d="M14 14L18 18"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                    />
                  </svg>
                </button>
              </div>
              <RecentSearchesDropdown
                entries={recentEntries}
                visible={dropdownVisible}
                onSelect={handleRecentSelect}
                onDeleteEntry={(q) => deleteRecent(q)}
                onClearAll={() => { clearRecent(); setDropdownVisible(false) }}
                onDismiss={() => setDropdownVisible(false)}
              />
            </div>
            {validation && (
              <p
                className="validation-message"
                role="alert"
                data-testid="results-validation"
              >
                {validation}
              </p>
            )}
          </form>

          <div className="results-header-right">
            <button
              type="button"
              className="advanced-search-link-btn"
              onClick={() => setModalOpen(true)}
              data-testid="results-advanced-search-link"
            >
              Advanced Search
            </button>
            <div className="bookmark-wrap">
              <button
                type="button"
                className="bookmark-btn"
                aria-label="Saved searches"
                title="Saved searches"
                onClick={() => setSavedPanelOpen((o) => !o)}
                data-testid="results-bookmark-btn"
              >
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 20 20"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="M5 3h10v14l-5-3-5 3V3z"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
              <SavedSearchesPanel
                entries={savedEntries}
                atLimit={atLimit}
                visible={savedPanelOpen}
                showSaveButton={true}
                onRunSearch={handleSavedRun}
                onSave={handleSaveCurrentSearch}
                onDelete={(id) => deleteSaved(id)}
                onRename={(id, name) => renameEntry(id, name)}
                onToast={setToast}
                onDismiss={() => setSavedPanelOpen(false)}
              />
            </div>
          </div>
        </div>
      </header>

      <main className="results-content">
        {activeChips.length > 0 && (
          <div
            className="filter-chips-row"
            role="region"
            aria-label="Active filters"
            data-testid="filter-chips-row"
          >
            {activeChips.map((chip) => (
              <FilterChip
                key={chip.key}
                label={chip.label}
                onRemove={() => removeFilter(chip.key)}
              />
            ))}
            <button
              type="button"
              className="filter-chips-clear-all"
              onClick={clearAllFilters}
              data-testid="filter-chips-clear-all"
            >
              Clear all
            </button>
          </div>
        )}

        {data && hasExpansion(data.expansion_notice) && (
          <p className="expansion-notice" data-testid="expansion-notice">
            {formatExpansionNotice(data.expansion_notice)}
          </p>
        )}

        {!loading && !error && data && (
          <div className="results-header-row" data-testid="results-header-row">
            <span className="result-count" data-testid="result-count">
              {(data.total_display === '10,000+'
                ? '10,000+ results'
                : formatResultCount(data.total))}{' '}
              for &quot;{urlQuery}&quot;
            </span>
            <div className="sort-dropdown-wrap">
              <label htmlFor="sort" className="sort-dropdown-label">
                Sort:
              </label>
              <select
                id="sort"
                className="sort-dropdown"
                value={urlSort}
                onChange={onSortChange}
                data-testid="sort-dropdown"
              >
                {SORT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {loading && (
          <div data-testid="loading-state">
            {[0, 1, 2, 3, 4].map((i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}

        {!loading && error && (
          <div className="error-state" data-testid="error-state">
            <h2 className="error-state-title">{ERROR_STATE_TITLE}</h2>
            <p className="error-state-body">{ERROR_STATE_BODY}</p>
            <button
              type="button"
              className="retry-button"
              onClick={retry}
              data-testid="retry-button"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && !error && data && debugMode && (
          <SearchDebugPanel
            debugEnvelope={data.debug}
            apiRequest={{
              method: 'POST',
              url: `${SEARCH_ENDPOINT}?debug=1`,
              body: buildSearchRequestBody({ query: urlQuery, filters, sort: urlSort, page: urlPage }),
            }}
            apiResponse={data}
          />
        )}

        {!loading && !error && data && (
          <>
            {data.results && data.results.length > 0 ? (
              <>
                <div data-testid="results-list">
                  {data.results.map((r) => (
                    <ResultCard key={r.id} result={r} filters={filters} debug={debugMode} />
                  ))}
                </div>
                <Pagination
                  currentPage={urlPage}
                  totalPages={data.total_pages || 1}
                  onPageChange={onPageChange}
                />
              </>
            ) : (
              <div className="empty-state" data-testid="empty-state">
                <h2 className="empty-state-title">
                  No results found for &quot;{urlQuery}&quot;.
                </h2>
                <p className="empty-state-body">{NO_RESULTS_BODY}</p>
              </div>
            )}
          </>
        )}
      </main>

      <footer className="results-footer">
        <Link to="/index-status" data-testid="index-status-link">
          Index status
        </Link>
      </footer>

      <AdvancedSearchModal
        isOpen={modalOpen}
        initialFilters={filters}
        onApply={onModalApply}
        onClose={() => setModalOpen(false)}
      />

      <Toast message={toast} onDismiss={() => setToast('')} />
    </div>
  )
}
