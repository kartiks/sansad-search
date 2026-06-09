import { useState } from 'react'
import { useDebugDetail } from '../hooks/useDebugDetail.js'
import JsonTree from './JsonTree.jsx'

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
            <div className="debug-pre" data-testid="debug-scoring-content">
              <JsonTree
                data={{
                  _rankingScore: result._rankingScore,
                  ...(result._rankingScoreDetails !== undefined
                    ? { _rankingScoreDetails: result._rankingScoreDetails }
                    : {}),
                }}
              />
            </div>
          </DebugSection>

          <DebugSection
            title="Document in index"
            isOpen={documentOpen}
            onToggle={() => setDocumentOpen((o) => !o)}
            testId="debug-section-document"
          >
            <div className="debug-pre" data-testid="debug-document-content">
              <JsonTree data={result._meili_document ?? result} />
            </div>
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
              <div className="debug-pre" data-testid="debug-processed-content">
                <JsonTree data={processedData} />
              </div>
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
              <div className="debug-pre" data-testid="debug-raw-content">
                <JsonTree data={rawData} />
              </div>
            )}
          </DebugSection>
        </div>
      )}
    </div>
  )
}
