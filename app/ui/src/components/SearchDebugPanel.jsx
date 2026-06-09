import { useState } from 'react'
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
 * F10 global search debug panel.
 *
 * Shown above the result list when ?debug=1 is active. Contains five
 * independently collapsible sections. All sections start collapsed.
 *
 * Props:
 *   debugEnvelope  — the `debug` key from the search API response
 *                    (processed_query, meilisearch_request, meilisearch_response)
 *   apiRequest     — {method, url, body} captured by the frontend
 *   apiResponse    — the full search API response body
 */
export default function SearchDebugPanel({ debugEnvelope, apiRequest, apiResponse }) {
  const [processedQueryOpen, setProcessedQueryOpen] = useState(false)
  const [apiRequestOpen, setApiRequestOpen] = useState(false)
  const [apiResponseOpen, setApiResponseOpen] = useState(false)
  const [meiliRequestOpen, setMeiliRequestOpen] = useState(false)
  const [meiliResponseOpen, setMeiliResponseOpen] = useState(false)

  return (
    <div className="search-debug-panel" data-testid="search-debug-panel">
      <div className="search-debug-panel-title">Search debug trace</div>

      <DebugSection
        title="Processed query"
        isOpen={processedQueryOpen}
        onToggle={() => setProcessedQueryOpen((o) => !o)}
        testId="search-debug-processed-query"
      >
        <div className="debug-pre" data-testid="search-debug-processed-query-content">
          <JsonTree data={debugEnvelope?.processed_query ?? ''} />
        </div>
      </DebugSection>

      <DebugSection
        title="API request"
        isOpen={apiRequestOpen}
        onToggle={() => setApiRequestOpen((o) => !o)}
        testId="search-debug-api-request"
      >
        <div className="debug-pre" data-testid="search-debug-api-request-content">
          <JsonTree data={apiRequest} />
        </div>
      </DebugSection>

      <DebugSection
        title="API response"
        isOpen={apiResponseOpen}
        onToggle={() => setApiResponseOpen((o) => !o)}
        testId="search-debug-api-response"
      >
        <div className="debug-pre" data-testid="search-debug-api-response-content">
          <JsonTree data={apiResponse} />
        </div>
      </DebugSection>

      <DebugSection
        title="Meilisearch request"
        isOpen={meiliRequestOpen}
        onToggle={() => setMeiliRequestOpen((o) => !o)}
        testId="search-debug-meili-request"
      >
        <div className="debug-pre" data-testid="search-debug-meili-request-content">
          <JsonTree data={debugEnvelope?.meilisearch_request} />
        </div>
      </DebugSection>

      <DebugSection
        title="Meilisearch response"
        isOpen={meiliResponseOpen}
        onToggle={() => setMeiliResponseOpen((o) => !o)}
        testId="search-debug-meili-response"
      >
        <div className="debug-pre" data-testid="search-debug-meili-response-content">
          <JsonTree data={debugEnvelope?.meilisearch_response} />
        </div>
      </DebugSection>
    </div>
  )
}
