import {
  getProceedingTypeLabel,
  getSourceLabel,
  UNTRANSLATED_SPEECH_MESSAGE,
} from '../lib/constants.js'
import { sanitizeSnippet } from '../lib/sanitizeSnippet.js'

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
