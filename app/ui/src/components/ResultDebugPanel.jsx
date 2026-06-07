import { useState } from 'react'
import { useDebugDetail } from '../hooks/useDebugDetail.js'

function DebugSection({ title, isOpen, onToggle, testId, children }) {
  return (
    <div className="debug-section" data-testid={testId}>
      <button
        type="button"
        className="debug-section-header"
        onClick={onToggle}
        aria-expanded={isOpen}
        data-testid={`${testId}-toggle`}
      >
        <span className="debug-section-title">{title}</span>
        <span className="debug-section-chevron">{isOpen ? '▲' : '▼'}</span>
      </button>
      {isOpen && (
        <div className="debug-section-body" data-testid={`${testId}-body`}>
          {children}
        </div>
      )}
    </div>
  )
}

/**
 * F10 per-result debug panel.
 *
 * Rendered below a result card when ?debug=1 is active. Has a top-level
 * "Debug" toggle; expanding it shows 4 independently collapsible sections.
 * Sections 3 (Processed record) and 4 (Raw document) lazy-fetch on first
 * expand and cache the result — subsequent expands produce no additional
 * requests.
 */
export default function ResultDebugPanel({ result }) {
  const [panelOpen, setPanelOpen] = useState(false)
  const [scoringOpen, setScoringOpen] = useState(false)
  const [documentOpen, setDocumentOpen] = useState(false)
  const [processedOpen, setProcessedOpen] = useState(false)
  const [rawOpen, setRawOpen] = useState(false)

  const {
    processedData, processedError, processedLoading, fetchProcessed,
    rawData, rawError, rawLoading, fetchRaw,
  } = useDebugDetail(result.id)

  const handleProcessedToggle = () => {
    const opening = !processedOpen
    setProcessedOpen(opening)
    if (opening) fetchProcessed()
  }

  const handleRawToggle = () => {
    const opening = !rawOpen
    setRawOpen(opening)
    if (opening) fetchRaw()
  }

  return (
    <div className="result-debug-panel-wrap" data-testid="result-debug-panel-wrap">
      <button
        type="button"
        className="debug-panel-toggle"
        onClick={() => setPanelOpen((o) => !o)}
        aria-expanded={panelOpen}
        data-testid="debug-panel-toggle"
      >
        Debug
      </button>

      {panelOpen && (
        <div className="result-debug-panel" data-testid="result-debug-panel">
          <DebugSection
            title="Scoring details"
            isOpen={scoringOpen}
            onToggle={() => setScoringOpen((o) => !o)}
            testId="debug-section-scoring"
          >
            <pre className="debug-pre" data-testid="debug-scoring-content">
              {JSON.stringify(
                {
                  _rankingScore: result._rankingScore,
                  ...(result._rankingScoreDetails !== undefined
                    ? { _rankingScoreDetails: result._rankingScoreDetails }
                    : {}),
                },
                null,
                2,
              )}
            </pre>
          </DebugSection>

          <DebugSection
            title="Document in index"
            isOpen={documentOpen}
            onToggle={() => setDocumentOpen((o) => !o)}
            testId="debug-section-document"
          >
            <pre className="debug-pre" data-testid="debug-document-content">
              {JSON.stringify(result._meili_document ?? result, null, 2)}
            </pre>
          </DebugSection>

          <DebugSection
            title="Processed record"
            isOpen={processedOpen}
            onToggle={handleProcessedToggle}
            testId="debug-section-processed"
          >
            {processedLoading && (
              <span className="debug-loading" data-testid="debug-processed-loading">
                Loading…
              </span>
            )}
            {processedError && (
              <span className="debug-error" data-testid="debug-processed-error">
                {processedError.status === 404
                  ? 'Record not found.'
                  : 'Error loading processed record.'}
              </span>
            )}
            {processedData && (
              <pre className="debug-pre" data-testid="debug-processed-content">
                {JSON.stringify(processedData, null, 2)}
              </pre>
            )}
          </DebugSection>

          <DebugSection
            title="Raw document"
            isOpen={rawOpen}
            onToggle={handleRawToggle}
            testId="debug-section-raw"
          >
            {rawLoading && (
              <span className="debug-loading" data-testid="debug-raw-loading">
                Loading…
              </span>
            )}
            {rawError && (
              <span className="debug-error" data-testid="debug-raw-error">
                Raw document not available.
              </span>
            )}
            {rawData && (
              <pre className="debug-pre" data-testid="debug-raw-content">
                {JSON.stringify(rawData, null, 2)}
              </pre>
            )}
          </DebugSection>
        </div>
      )}
    </div>
  )
}
