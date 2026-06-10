import { Link } from 'react-router-dom'
import {
  getProceedingTypeLabel,
  SOURCE_LABELS,
  BODY_BADGE_STYLES,
  UNTRANSLATED_SPEECH_MESSAGE,
  SUPPLEMENTARY_PREFIX,
} from '../lib/constants.js'
import { sanitizeSnippet } from '../lib/sanitizeSnippet.js'

function LangBadge({ lang_original }) {
  if (lang_original === 'hi') {
    return (
      <span className="lang-badge lang-badge--hindi" data-testid="lang-badge">
        Hindi original
      </span>
    )
  }
  if (lang_original === 'mixed') {
    return (
      <span className="lang-badge lang-badge--mixed" data-testid="lang-badge">
        Mixed language
      </span>
    )
  }
  return null
}

function MetadataRow({ result }) {
  const ptypeLabel = getProceedingTypeLabel(result.proceeding_type)
  const bodyLabel = SOURCE_LABELS[result.source] || result.source || ''
  const badgeStyle = BODY_BADGE_STYLES[result.source] || {}
  const dateLabel = result.date_display || ''
  const sessionLabel = result.session_name || ''

  return (
    <div className="metadata-row" data-testid="metadata-row">
      {ptypeLabel && <span className="proceeding-badge">{ptypeLabel}</span>}
      {bodyLabel && (
        <>
          <span className="metadata-sep">·</span>
          <span
            className="body-badge"
            style={badgeStyle}
            data-testid="body-badge"
          >
            {bodyLabel}
          </span>
        </>
      )}
      {dateLabel && (
        <>
          <span className="metadata-sep">·</span>
          <span>{dateLabel}</span>
          {result.time_of_day != null && (
            <span className="time-of-day" data-testid="time-of-day">
              {result.time_of_day}
            </span>
          )}
        </>
      )}
      {sessionLabel && (
        <>
          <span className="metadata-sep">·</span>
          <span>{sessionLabel}</span>
        </>
      )}
    </div>
  )
}

export function formatQuestionerNames(names) {
  if (!Array.isArray(names) || names.length === 0) return ''
  const primary = names[0]
  if (names.length === 1) return primary
  return `${primary} +${names.length - 1} others`
}

export default function QACard({ result, detailTo, detailState }) {
  const subject = result.subject
  const questionNumber = result.question_number
  const questioners = result.questioner_names
  const questionerParty = result.questioner_party
  const ministerName = result.minister_name
  const ministry = result.ministry
  const fromSupplementary = result.snippet_from_supplementary === true
  const fullTextNull =
    result.snippet == null || result.snippet === undefined
  const isTranslated = result.is_translated === true
  const sourceUrl = result.source_url

  const questionerLine = formatQuestionerNames(questioners)
  const ministerLine =
    ministerName && ministry
      ? `Answered by ${ministerName}, ${ministry}`
      : ministerName
        ? `Answered by ${ministerName}`
        : ministry
          ? `Answered by ${ministry}`
          : null

  return (
    <article
      className={`result-card${result.source ? ` result-card--${result.source}` : ''}`}
      data-testid="qa-card"
    >
      <MetadataRow result={result} />

      {subject && (
        <Link
          to={detailTo}
          state={detailState}
          className="subject-line subject-two-lines card-detail-link"
          title={subject}
          data-testid="subject-detail-link"
        >
          {subject}
        </Link>
      )}

      {questionNumber != null && (
        <div className="question-number" data-testid="question-number">
          <Link
            to={detailTo}
            state={detailState}
            className="card-detail-link"
            data-testid="question-number-link"
          >
            Q. {questionNumber}
          </Link>
        </div>
      )}

      {questionerLine && (
        <div className="questioner-row" data-testid="questioner-row">
          <Link
            to={detailTo}
            state={detailState}
            className="card-detail-link"
            data-testid="questioner-detail-link"
          >
            {questionerLine}
          </Link>
          {questionerParty && (
            <span className="party-meta">· {questionerParty}</span>
          )}
        </div>
      )}

      {ministerLine && (
        <div className="minister-row" data-testid="minister-row">
          <Link
            to={detailTo}
            state={detailState}
            className="card-detail-link"
            data-testid="minister-detail-link"
          >
            {ministerLine}
          </Link>
        </div>
      )}

      {fullTextNull ? (
        <div className="snippet-placeholder" data-testid="untranslated-placeholder">
          {UNTRANSLATED_SPEECH_MESSAGE}
        </div>
      ) : (
        <div className="snippet" data-testid="snippet">
          {fromSupplementary && (
            <span
              className="snippet-supplementary-prefix"
              data-testid="supplementary-prefix"
            >
              {SUPPLEMENTARY_PREFIX}
            </span>
          )}
          <span
            data-testid="snippet-text"
            dangerouslySetInnerHTML={{ __html: sanitizeSnippet(result.snippet) }}
          />
        </div>
      )}

      {isTranslated && (
        <div className="translation-indicator" data-testid="translation-indicator">
          Translated from Hindi
        </div>
      )}

      <LangBadge lang_original={result.lang_original} />

      <div className="card-actions">
        <Link
          to={detailTo}
          state={detailState}
          className="card-details-link"
          data-testid="details-link"
        >
          Details
        </Link>
        {sourceUrl && (
          <a
            className="view-source"
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
          >
            View source ↗
          </a>
        )}
      </div>
    </article>
  )
}
