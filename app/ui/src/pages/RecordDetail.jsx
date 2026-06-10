import { useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useRecord } from '../hooks/useRecord.js'
import { useAdjacent } from '../hooks/useAdjacent.js'
import { useCookieHistory } from '../hooks/useCookieHistory.js'
import { useSavedSearches, sanitizeStoredFilters } from '../hooks/useSavedSearches.js'
import {
  getProceedingTypeLabel,
  getSourceLabel,
  SEARCH_PLACEHOLDER,
  MAX_QUERY_LEN,
  DEBUG_BADGE_LABEL,
  NO_ENGLISH_TEXT_RECORD,
  RECORD_NOT_FOUND,
  RECORD_NOT_FOUND_DETAIL,
  BACK_TO_RESULTS,
  BACK_TO_SEARCH,
  LOAD_PREVIOUS,
  LOAD_NEXT,
  ADJACENT_ERROR,
} from '../lib/constants.js'
import { defaultFilterState, isDefaultFilterState } from '../lib/filterState.js'
import { toOrdinal } from '../lib/ordinal.js'
import AdvancedSearchModal from '../components/AdvancedSearchModal.jsx'
import SavedSearchesPanel from '../components/SavedSearchesPanel.jsx'

const LANG_ORIGINAL_LABELS = {
  en: 'English',
  hi: 'Hindi',
  mixed: 'Bilingual',
}

const SPEAKER_ROLE_LABELS = {
  member: 'Member',
  minister: 'Minister',
  presiding_officer: 'Presiding Officer',
}

function MetaField({ label, value, testId }) {
  if (value == null || value === false) return null
  return (
    <div className="record-meta-field" data-testid={testId}>
      <span className="record-meta-label">{label}</span>
      <span className="record-meta-value">{value}</span>
    </div>
  )
}

function renderParagraphs(fullText) {
  if (!fullText) {
    return (
      <p className="record-null-text" data-testid="null-full-text-message">
        {NO_ENGLISH_TEXT_RECORD}
      </p>
    )
  }
  return fullText
    .split('\n')
    .filter((p) => p.trim())
    .map((para, i) => (
      <p key={i} className="record-text-para">
        {para}
      </p>
    ))
}

function AdjacentRecord({ record }) {
  const proceedingLabel = getProceedingTypeLabel(record.proceeding_type)
  const sourceClass = record.source ? ` record-adjacent-item--${record.source}` : ''
  const attribution =
    record.record_type === 'qa'
      ? [
          record.questioner_names && record.questioner_names.length > 0
            ? record.questioner_names.join(', ')
            : null,
          record.minister_name ? `Answered by ${record.minister_name}` : null,
        ]
          .filter(Boolean)
          .join(' · ')
      : record.speaker_name || 'Speaker unknown'

  return (
    <article
      className={`record-adjacent-item${sourceClass}`}
      data-testid={`adjacent-record-${record.id}`}
    >
      <div className="record-adjacent-meta">
        {proceedingLabel && (
          <span className="proceeding-badge">{proceedingLabel}</span>
        )}
        {record.date_display && (
          <span className="record-adjacent-date">{record.date_display}</span>
        )}
      </div>
      <div className="record-adjacent-attribution">{attribution}</div>
      {record.subject && (
        <div className="record-adjacent-subject">{record.subject}</div>
      )}
      <div className="record-adjacent-fulltext">
        {renderParagraphs(record.full_text_en)}
      </div>
    </article>
  )
}

function RecordDetailHeader({ debugMode }) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [savedPanelOpen, setSavedPanelOpen] = useState(false)
  const [filters, setFilters] = useState(defaultFilterState)

  const bookmarkBtnRef = useRef(null)

  const { recordSearch } = useCookieHistory()
  const { entries: savedEntries, atLimit, deleteEntry: deleteSaved, renameEntry } = useSavedSearches()

  const handleSearch = (q, f) => {
    const trimmed = (q || '').trim()
    if (trimmed.length < 2) return
    recordSearch(trimmed)
    const sp = new URLSearchParams()
    sp.set('q', trimmed)
    sp.set('page', '1')
    navigate(`/search?${sp.toString()}`, {
      state: f && !isDefaultFilterState(f) ? { filters: f } : undefined,
    })
  }

  const onSubmit = (e) => {
    e.preventDefault()
    handleSearch(query, filters)
  }

  const handleSavedRun = (entry) => {
    setSavedPanelOpen(false)
    const sanitized = sanitizeStoredFilters(entry.filters)
    handleSearch(entry.query, sanitized)
  }

  return (
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
          <div className="search-bar compact">
            <input
              type="text"
              className="search-bar-input"
              placeholder={SEARCH_PLACEHOLDER}
              aria-label="Search parliamentary records"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              maxLength={MAX_QUERY_LEN}
              data-testid="detail-search-input"
            />
            <button
              type="submit"
              className="search-submit"
              aria-label="Submit search"
              data-testid="detail-search-submit"
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
        </form>

        <div className="results-header-right">
          <button
            type="button"
            className="advanced-search-link-btn"
            onClick={() => setModalOpen(true)}
            data-testid="detail-advanced-search-link"
          >
            Advanced Search
          </button>
          <div className="bookmark-wrap" ref={bookmarkBtnRef}>
            <button
              type="button"
              className="bookmark-btn"
              aria-label="Saved searches"
              title="Saved searches"
              onClick={() => setSavedPanelOpen((o) => !o)}
              data-testid="detail-bookmark-btn"
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
              onToast={() => {}}
              onDismiss={() => setSavedPanelOpen(false)}
            />
          </div>
          {debugMode && (
            <span className="debug-badge" data-testid="detail-debug-badge">
              {DEBUG_BADGE_LABEL}
            </span>
          )}
        </div>
      </div>

      <AdvancedSearchModal
        isOpen={modalOpen}
        initialFilters={filters}
        onApply={(newFilters) => {
          setFilters(newFilters)
          setModalOpen(false)
        }}
        onClose={() => setModalOpen(false)}
      />
    </header>
  )
}

export default function RecordDetail() {
  const [searchParams] = useSearchParams()
  const debugMode = searchParams.get('debug') === '1' || searchParams.get('debug') === 'true'

  const { id } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { data, error, loading, notFound, retry } = useRecord(id)

  const fromSearch = location.state?.from === 'search'
  const resultsPath = location.state?.resultsPath

  const {
    prevRecords,
    nextRecords,
    canLoadPrev,
    canLoadNext,
    loadingPrev,
    loadingNext,
    errorPrev,
    errorNext,
    loadPrev,
    loadNext,
  } = useAdjacent(id, data)

  const sourceClass = (base, src) =>
    src ? `${base} ${base}--${src}` : base

  const lokSabhaDisplay =
    data?.source === 'LS' && data?.lok_sabha_number != null
      ? `${toOrdinal(data.lok_sabha_number)} Lok Sabha`
      : null

  return (
    <div className="results-page">
      <RecordDetailHeader debugMode={debugMode} />

      <main className="results-content">
        {loading && (
          <div
            className="record-detail record-detail--loading"
            data-testid="record-loading"
          >
            <p>Loading…</p>
          </div>
        )}

        {notFound && (
          <div
            className="record-detail record-detail--not-found"
            data-testid="record-not-found"
          >
            <p>{RECORD_NOT_FOUND}.</p>
            <p className="record-meta-note">{RECORD_NOT_FOUND_DETAIL}</p>
            <Link to="/">{BACK_TO_SEARCH}</Link>
          </div>
        )}

        {error && !notFound && (
          <div
            className="record-detail record-detail--error"
            data-testid="record-error"
          >
            <p>Unable to load record.</p>
            <button onClick={retry} className="record-retry-btn" data-testid="retry-button">
              Retry
            </button>
            <Link to="/">{BACK_TO_SEARCH}</Link>
          </div>
        )}

        {data && (
          <div className="record-detail" data-testid="record-detail">
            {/* ── Top bar: back nav + position indicator ── */}
            <div className="record-detail-topbar">
              <div className="record-detail-backnav">
                {fromSearch ? (
                  <button
                    className="record-back-btn"
                    data-testid="back-to-results"
                    onClick={() =>
                      navigate(resultsPath || '/', {
                        state: { filters: location.state?.filters },
                      })
                    }
                  >
                    {BACK_TO_RESULTS}
                  </button>
                ) : (
                  <Link to="/" className="record-back-link" data-testid="back-to-search">
                    {BACK_TO_SEARCH}
                  </Link>
                )}
              </div>

              {data.sequence_within_sitting != null && data.sitting_total > 0 && (
                <span className="record-position" data-testid="position-indicator">
                  {data.sequence_within_sitting} of {data.sitting_total}
                </span>
              )}
            </div>

            {/* ── Load 5 previous ── */}
            <div className="record-adjacent-controls record-adjacent-controls--prev">
              <button
                className="record-load-btn"
                data-testid="load-prev-button"
                disabled={!canLoadPrev || loadingPrev}
                onClick={loadPrev}
              >
                {loadingPrev ? 'Loading…' : LOAD_PREVIOUS}
              </button>
              {errorPrev && (
                <p className="record-adjacent-error" data-testid="adjacent-error-prev">
                  {ADJACENT_ERROR}
                </p>
              )}
            </div>

            {/* ── Loaded previous records ── */}
            {prevRecords.length > 0 && (
              <div className="record-adjacent-list" data-testid="adjacent-prev-records">
                {prevRecords.map((r) => (
                  <AdjacentRecord key={r.id} record={r} />
                ))}
              </div>
            )}

            {/* ── Focal record metadata ── */}
            <div
              className={sourceClass('record-detail-metadata', data.source)}
              data-testid="record-metadata"
            >
              <MetaField label="Legislative body" value={getSourceLabel(data.source)} testId="field-source" />
              {lokSabhaDisplay && (
                <MetaField
                  label="Lok Sabha term"
                  value={lokSabhaDisplay}
                  testId="field-lok-sabha-number"
                />
              )}
              <MetaField label="Proceeding type" value={getProceedingTypeLabel(data.proceeding_type)} testId="field-proceeding-type" />
              <MetaField label="Date" value={data.date_display} testId="field-date" />
              <MetaField label="Time" value={data.time_of_day} testId="field-time-of-day" />
              <MetaField label="Session" value={data.session_name} testId="field-session-name" />
              <MetaField label="Session number" value={data.session_number} testId="field-session-number" />
              <MetaField label="Sitting number" value={data.sitting_number} testId="field-sitting-number" />
              {data.source === 'CA' && (
                <MetaField label="Volume" value={data.volume} testId="field-volume" />
              )}
              <MetaField label="Subject" value={data.subject} testId="field-subject" />

              {/* Speech fields */}
              {data.record_type === 'speech' && (
                <>
                  {data.speaker_name != null && (
                    <div className="record-meta-field" data-testid="field-speaker-name">
                      <span className="record-meta-label">Speaker</span>
                      <span className="record-meta-value">{data.speaker_name}</span>
                    </div>
                  )}
                  <MetaField
                    label="Role"
                    value={
                      data.speaker_role
                        ? SPEAKER_ROLE_LABELS[data.speaker_role] || data.speaker_role
                        : null
                    }
                    testId="field-speaker-role"
                  />
                  <MetaField label="Party" value={data.speaker_party} testId="field-speaker-party" />
                  {data.source !== 'CA' && (
                    <MetaField
                      label="Constituency / State"
                      value={data.speaker_constituency_or_state}
                      testId="field-constituency"
                    />
                  )}
                </>
              )}

              {/* Q+A fields */}
              {data.record_type === 'qa' && (
                <>
                  {data.question_number != null && (
                    <div className="record-meta-field" data-testid="field-question-number">
                      <span className="record-meta-label">Question number</span>
                      <span className="record-meta-value">Q. {data.question_number}</span>
                    </div>
                  )}
                  {data.questioner_names && data.questioner_names.length > 0 && (
                    <div className="record-meta-field" data-testid="field-questioner-names">
                      <span className="record-meta-label">Questioner(s)</span>
                      <span className="record-meta-value">
                        {data.questioner_names.join(', ')}
                      </span>
                    </div>
                  )}
                  <MetaField label="Questioner party" value={data.questioner_party} testId="field-questioner-party" />
                  <MetaField label="Minister" value={data.minister_name} testId="field-minister-name" />
                  <MetaField label="Ministry" value={data.ministry} testId="field-ministry" />
                </>
              )}

              {/* Common trailing fields */}
              <div className="record-meta-field" data-testid="field-lang-original">
                <span className="record-meta-label">Language</span>
                <span className="record-meta-value">
                  {LANG_ORIGINAL_LABELS[data.lang_original] || data.lang_original}
                </span>
              </div>

              {data.is_translated && (
                <div className="record-meta-field" data-testid="field-is-translated">
                  <span className="record-meta-value record-meta-note">
                    Includes official English translation
                  </span>
                </div>
              )}

              {data.has_untranslated_content && (
                <div className="record-meta-field" data-testid="field-has-untranslated">
                  <span className="record-meta-value record-meta-note">
                    Some content unavailable in English
                  </span>
                </div>
              )}

              {data.page_reference != null && (
                <div className="record-meta-field" data-testid="field-page-reference">
                  <span className="record-meta-value">PDF page {data.page_reference}</span>
                </div>
              )}

              {data.word_count != null && (
                <div className="record-meta-field" data-testid="field-word-count">
                  <span className="record-meta-label">Word count</span>
                  <span className="record-meta-value">{data.word_count} words</span>
                </div>
              )}

              {data.source_url && (
                <div className="record-meta-field" data-testid="field-source-url">
                  <a
                    href={data.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="record-view-source"
                  >
                    View source ↗
                  </a>
                </div>
              )}
            </div>

            {/* ── Focal full text ── */}
            <div
              className={sourceClass('record-detail-fulltext', data.source)}
            >
              {renderParagraphs(data.full_text_en)}
            </div>

            {/* ── Loaded next records ── */}
            {nextRecords.length > 0 && (
              <div className="record-adjacent-list" data-testid="adjacent-next-records">
                {nextRecords.map((r) => (
                  <AdjacentRecord key={r.id} record={r} />
                ))}
              </div>
            )}

            {/* ── Load 5 next ── */}
            <div className="record-adjacent-controls record-adjacent-controls--next">
              <button
                className="record-load-btn"
                data-testid="load-next-button"
                disabled={!canLoadNext || loadingNext}
                onClick={loadNext}
              >
                {loadingNext ? 'Loading…' : LOAD_NEXT}
              </button>
              {errorNext && (
                <p className="record-adjacent-error" data-testid="adjacent-error-next">
                  {ADJACENT_ERROR}
                </p>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
