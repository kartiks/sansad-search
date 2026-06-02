import {
  getProceedingTypeLabel,
  getSourceLabel,
  UNTRANSLATED_SPEECH_MESSAGE,
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
  const parts = []
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

export default function SpeechCard({ result }) {
  const speakerName = result.speaker_name
  const party = result.speaker_party
  const constituency = result.speaker_constituency_or_state
  const subject = result.subject
  const fullTextNull =
    result.snippet == null || result.snippet === undefined
  const isTranslated = result.is_translated === true
  const sourceUrl = result.source_url

  const meta = []
  if (party) meta.push(party)
  if (constituency) meta.push(constituency)
  const metaText = meta.join(' · ')

  return (
    <article className="result-card" data-testid="speech-card">
      <MetadataRow result={result} />

      <div className="speaker-row">
        {speakerName ? speakerName : 'Speaker unknown'}
        {metaText && <span className="speaker-meta">· {metaText}</span>}
      </div>

      {subject && (
        <div className="subject-line" title={subject}>
          {subject}
        </div>
      )}

      {fullTextNull ? (
        <div className="snippet-placeholder" data-testid="untranslated-placeholder">
          {UNTRANSLATED_SPEECH_MESSAGE}
        </div>
      ) : (
        <div
          className="snippet"
          data-testid="snippet"
          dangerouslySetInnerHTML={{ __html: sanitizeSnippet(result.snippet) }}
        />
      )}

      {isTranslated && (
        <div className="translation-indicator" data-testid="translation-indicator">
          Translated from Hindi
        </div>
      )}

      <LangBadge lang_original={result.lang_original} />

      {sourceUrl && (
        <a
          className="view-source"
          href={sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
        >
          View source ↗
        </a>
      )}
    </article>
  )
}
