<<<<<<< HEAD
import { useEffect, useState } from 'react'
=======
import { useEffect, useRef, useState } from 'react'
>>>>>>> 286b750 (Checkpointing Phase 7 build.)
import { useNavigate } from 'react-router-dom'
import {
  SEARCH_PLACEHOLDER,
  TAGLINE,
  VALIDATION_SHORT,
  MIN_QUERY_CHARS,
  MAX_QUERY_LEN,
  STATUS_ENDPOINT,
} from '../lib/constants.js'
import { defaultFilterState, isDefaultFilterState } from '../lib/filterState.js'
import { formatCount, formatLongDate } from '../lib/statusFormat.js'
<<<<<<< HEAD
import AdvancedSearchModal from '../components/AdvancedSearchModal.jsx'
=======
import { useCookieHistory } from '../hooks/useCookieHistory.js'
import { useSavedSearches, sanitizeStoredFilters } from '../hooks/useSavedSearches.js'
import AdvancedSearchModal from '../components/AdvancedSearchModal.jsx'
import RecentSearchesDropdown from '../components/RecentSearchesDropdown.jsx'
import SavedSearchesPanel from '../components/SavedSearchesPanel.jsx'
import Toast from '../components/Toast.jsx'
>>>>>>> 286b750 (Checkpointing Phase 7 build.)

function formatStatusStrip(status) {
  if (!status || status.status !== 'ok') {
    return 'Status unavailable'
  }
  const sources = status.sources || {}
  const ca = (sources.ca && sources.ca.count) || 0
  const ls = (sources.ls && sources.ls.count) || 0
  const rs = (sources.rs && sources.rs.count) || 0
  const lastUpdated = formatLongDate(status.last_updated)
  return `Indexed: ${formatCount(ca)} Constituent Assembly records · ${formatCount(ls)} Lok Sabha records · ${formatCount(rs)} Rajya Sabha records · Last updated: ${lastUpdated}`
}

function StatusStrip() {
  const [statusText, setStatusText] = useState('Loading index status…')

  useEffect(() => {
    let cancelled = false
    fetch(STATUS_ENDPOINT)
      .then((r) => r.json())
      .then((s) => {
        if (cancelled) return
        setStatusText(formatStatusStrip(s))
      })
      .catch(() => {
        if (cancelled) return
        setStatusText('Status unavailable')
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="status-strip" data-testid="status-strip">
      {statusText}
    </div>
  )
}

export default function Home() {
  const navigate = useNavigate()
  const [value, setValue] = useState('')
  const [validation, setValidation] = useState('')
  const [filters, setFilters] = useState(defaultFilterState())
  const [modalOpen, setModalOpen] = useState(false)
<<<<<<< HEAD
=======
  const [dropdownVisible, setDropdownVisible] = useState(false)
  const [savedPanelOpen, setSavedPanelOpen] = useState(false)
  const [toast, setToast] = useState('')

  const searchBarRef = useRef(null)
  const bookmarkBtnRef = useRef(null)

  const { entries: recentEntries, cookiesEnabled, recordSearch, deleteEntry: deleteRecent, clearAll: clearRecent } = useCookieHistory()
  const { entries: savedEntries, atLimit, saveSearch, deleteEntry: deleteSaved, renameEntry } = useSavedSearches()

  const submitSearch = (query, navFilters) => {
    const searchParams = new URLSearchParams()
    searchParams.set('q', query)
    searchParams.set('page', '1')
    const navState = navFilters && !isDefaultFilterState(navFilters) ? { filters: navFilters } : undefined
    navigate(`/search?${searchParams.toString()}`, { state: navState })
  }
>>>>>>> 286b750 (Checkpointing Phase 7 build.)

  const onSubmit = (e) => {
    if (e && typeof e.preventDefault === 'function') e.preventDefault()
    const cleaned = (value || '').slice(0, MAX_QUERY_LEN)
    const trimmed = cleaned.replace(/\s+/g, '').length
    if (trimmed < MIN_QUERY_CHARS) {
      setValidation(VALIDATION_SHORT)
      return
    }
    setValidation('')
<<<<<<< HEAD
    const searchParams = new URLSearchParams()
    searchParams.set('q', cleaned.trim())
    searchParams.set('page', '1')
    const navState = !isDefaultFilterState(filters) ? { filters } : undefined
    navigate(`/search?${searchParams.toString()}`, { state: navState })
=======
    setDropdownVisible(false)
    recordSearch(cleaned.trim())
    submitSearch(cleaned.trim(), filters)
>>>>>>> 286b750 (Checkpointing Phase 7 build.)
  }

  const onChange = (e) => {
    setValue(e.target.value)
    if (validation) setValidation('')
<<<<<<< HEAD
=======
    if (e.target.value.length > 0) setDropdownVisible(false)
  }

  const onFocus = () => {
    if (cookiesEnabled && value.length === 0) setDropdownVisible(true)
  }

  const handleRecentSelect = (query) => {
    setDropdownVisible(false)
    setValue(query)
    recordSearch(query)
    submitSearch(query, null)
  }

  const handleSavedRun = (entry) => {
    setSavedPanelOpen(false)
    const sanitized = sanitizeStoredFilters(entry.filters)
    recordSearch(entry.query)
    submitSearch(entry.query, sanitized)
>>>>>>> 286b750 (Checkpointing Phase 7 build.)
  }

  return (
    <div className="home-page">
      <main className="home-main">
        <div className="home-column">
          <h1 className="wordmark-home">SansadSearch</h1>
          <p className="tagline">{TAGLINE}</p>

          <form onSubmit={onSubmit} role="search" aria-label="Site search">
<<<<<<< HEAD
            <div className="search-bar">
              <input
                type="text"
                className="search-bar-input"
                placeholder={SEARCH_PLACEHOLDER}
                aria-label="Search parliamentary records"
                value={value}
                onChange={onChange}
                maxLength={MAX_QUERY_LEN}
                data-testid="home-search-input"
              />
              <button
                type="submit"
                className="search-submit"
                aria-label="Submit search"
                data-testid="home-search-submit"
              >
                <svg
                  width="16"
                  height="16"
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
=======
            <div className="search-bar-wrap" ref={searchBarRef}>
              <div className="search-bar">
                <input
                  type="text"
                  className="search-bar-input"
                  placeholder={SEARCH_PLACEHOLDER}
                  aria-label="Search parliamentary records"
                  value={value}
                  onChange={onChange}
                  onFocus={onFocus}
                  maxLength={MAX_QUERY_LEN}
                  data-testid="home-search-input"
                />
                <button
                  type="submit"
                  className="search-submit"
                  aria-label="Submit search"
                  data-testid="home-search-submit"
                >
                  <svg
                    width="16"
                    height="16"
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
>>>>>>> 286b750 (Checkpointing Phase 7 build.)
            </div>
            {validation && (
              <p
                className="validation-message"
                role="alert"
                data-testid="home-validation"
              >
                {validation}
              </p>
            )}
          </form>

          <div className="below-bar-row">
            <button
              type="button"
              className="advanced-search-link-btn"
              onClick={() => setModalOpen(true)}
              data-testid="home-advanced-search-link"
            >
              Advanced Search
            </button>
<<<<<<< HEAD
            <button
              type="button"
              className="bookmark-btn"
              aria-label="Saved searches"
              title="Saved searches"
              data-testid="home-bookmark-btn"
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
=======
            <div className="bookmark-wrap" ref={bookmarkBtnRef}>
              <button
                type="button"
                className="bookmark-btn"
                aria-label="Saved searches"
                title="Saved searches"
                onClick={() => setSavedPanelOpen((o) => !o)}
                data-testid="home-bookmark-btn"
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
                showSaveButton={false}
                onRunSearch={handleSavedRun}
                onSave={() => {}}
                onDelete={(id) => deleteSaved(id)}
                onRename={(id, name) => renameEntry(id, name)}
                onToast={setToast}
                onDismiss={() => setSavedPanelOpen(false)}
              />
            </div>
>>>>>>> 286b750 (Checkpointing Phase 7 build.)
          </div>
        </div>
      </main>
      <StatusStrip />

      <AdvancedSearchModal
        isOpen={modalOpen}
        initialFilters={filters}
        onApply={(newFilters) => {
          setFilters(newFilters)
          setModalOpen(false)
        }}
        onClose={() => setModalOpen(false)}
      />
<<<<<<< HEAD
=======

      <Toast message={toast} onDismiss={() => setToast('')} />
>>>>>>> 286b750 (Checkpointing Phase 7 build.)
    </div>
  )
}
