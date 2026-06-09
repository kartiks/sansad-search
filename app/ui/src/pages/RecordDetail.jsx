import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useRecord } from '../hooks/useRecord.js'
import { useAdjacent } from '../hooks/useAdjacent.js'
import { getProceedingTypeLabel, getSourceLabel } from '../lib/constants.js'
import { toOrdinal } from '../lib/ordinal.js'

const NULL_FULL_TEXT_MESSAGE =
  'This record was delivered in Hindi. No English text is available.'

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
        {NULL_FULL_TEXT_MESSAGE}
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

// One adjacent record card: styled card with metadata, attribution, subject, and full text.
function AdjacentRecord({ record }) {
  const proceedingLabel = getProceedingTypeLabel(record.proceeding_type)
  const sourceLabel = getSourceLabel(record.source)
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
      className="record-adjacent-item"
      data-testid={`adjacent-record-${record.id}`}
    >
      <div className="record-adjacent-meta">
        {sourceLabel && <span>{sourceLabel}</span>}
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

export default function RecordDetail() {
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

  if (loading) {
    return (
      <div className="record-detail record-detail--loading" data-testid="record-loading">
        <p>Loading…</p>
      </div>
    )
  }

  if (notFound) {
    return (
      <div className="record-detail record-detail--not-found" data-testid="record-not-found">
        <p>Record not found.</p>
        <Link to="/">← Search</Link>
      </div>
    )
  }

  if (error) {
    return (
      <div className="record-detail record-detail--error" data-testid="record-error">
        <p>Unable to load record.</p>
        <button onClick={retry} className="record-retry-btn" data-testid="retry-button">
          Retry
        </button>
        <Link to="/">← Search</Link>
      </div>
    )
  }

  if (!data) return null

  const { sitting_total } = data

  const sourceLabel = getSourceLabel(data.source)
  const proceedingLabel = getProceedingTypeLabel(data.proceeding_type)
  const langLabel = LANG_ORIGINAL_LABELS[data.lang_original] || data.lang_original
  const speakerRoleLabel = data.speaker_role
    ? SPEAKER_ROLE_LABELS[data.speaker_role] || data.speaker_role
    : null

  // F09 (PRD v3.0): Lok Sabha term — LS records only, rendered with ordinal
  // suffix. Omitted entirely for RS and CA (no "Lok Sabha" text in those cards).
  const lokSabhaDisplay =
    data.source === 'LS' && data.lok_sabha_number != null
      ? `${toOrdinal(data.lok_sabha_number)} Lok Sabha`
      : null

  return (
    <div className="record-detail" data-testid="record-detail">
      {/* ── Top bar: back nav + position indicator ── */}
      <div className="record-detail-topbar">
        <div className="record-detail-backnav">
          {fromSearch ? (
            <button
              className="record-back-btn"
              data-testid="back-to-results"
              onClick={() => navigate(resultsPath || '/', { state: { filters: location.state?.filters } })}
            >
              ← Back to results
            </button>
          ) : (
            <Link to="/" className="record-back-link" data-testid="back-to-search">
              ← Search
            </Link>
          )}
        </div>

        {data.sequence_within_sitting != null && sitting_total > 0 && (
          <span className="record-position" data-testid="position-indicator">
            {data.sequence_within_sitting} of {sitting_total}
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
          {loadingPrev ? 'Loading…' : 'Load 5 previous'}
        </button>
        {errorPrev && (
          <p className="record-adjacent-error" data-testid="adjacent-error-prev">
            Unable to load previous records.
          </p>
        )}
      </div>

      {/* ── Loaded previous records (ascending, above focal) ── */}
      {prevRecords.length > 0 && (
        <div className="record-adjacent-list" data-testid="adjacent-prev-records">
          {prevRecords.map((r) => (
            <AdjacentRecord key={r.id} record={r} />
          ))}
        </div>
      )}

      {/* ── Focal record metadata ── */}
      <div className="record-detail-metadata">
        <MetaField label="Legislative body" value={sourceLabel} testId="field-source" />
        {lokSabhaDisplay && (
          <MetaField
            label="Lok Sabha term"
            value={lokSabhaDisplay}
            testId="field-lok-sabha-number"
          />
        )}
        <MetaField label="Proceeding type" value={proceedingLabel} testId="field-proceeding-type" />
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
                <span className="record-meta-value">
                  {data.speaker_name}
                </span>
              </div>
            )}
            <MetaField label="Role" value={speakerRoleLabel} testId="field-speaker-role" />
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
          <span className="record-meta-value">{langLabel}</span>
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
      <div className="record-detail-fulltext">
        {renderParagraphs(data.full_text_en)}
      </div>

      {/* ── Loaded next records (ascending, below focal) ── */}
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
          {loadingNext ? 'Loading…' : 'Load 5 next'}
        </button>
        {errorNext && (
          <p className="record-adjacent-error" data-testid="adjacent-error-next">
            Unable to load next records.
          </p>
        )}
      </div>
    </div>
  )
}
