import {
  getProceedingTypeLabel,
  getSourceLabel,
  UNTRANSLATED_SPEECH_MESSAGE,
  SUPPLEMENTARY_PREFIX,
} from '../lib/constants.js'
import { sanitizeSnippet } from '../lib/sanitizeSnippet.js'

function MetadataRow({ result }) {
  const ptypeLabel = getProceedingTypeLabel(result.proceeding_type)
  const bodyLabel = getSourceLabel(result.source)
  const dateLabel = result.date_display || ''
  const sessionLabel = result.session_name || ''

  return (
    <div className="metadata-row" data-testid="metadata-row">
      {ptypeLabel && <span className="proceeding-badge">{ptypeLabel}</span>}
      {bodyLabel && (
        <>
          <span className="metadata-sep">·</span>
          <span>{bodyLabel}</span>
        </>
      )}
      {dateLabel && (
        <>
          <span className="metadata-sep">·</span>
          <span>{dateLabel}</span>
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

export default function QACard({ result }) {
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
    <article className="result-card" data-testid="qa-card">
      <MetadataRow result={result} />

      {subject && (
        <div className="subject-line subject-two-lines" title={subject}>
          {subject}
        </div>
      )}

      {questionNumber != null && (
        <div className="question-number" data-testid="question-number">
          Q. {questionNumber}
        </div>
      )}

      {questionerLine && (
        <div className="questioner-row" data-testid="questioner-row">
          {questionerLine}
          {questionerParty && (
            <span className="party-meta">· {questionerParty}</span>
          )}
        </div>
      )}

      {ministerLine && (
        <div className="minister-row" data-testid="minister-row">
          {ministerLine}
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
    </article>
  )
}
