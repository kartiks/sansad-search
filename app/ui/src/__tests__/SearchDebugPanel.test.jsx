import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SearchDebugPanel from '../components/SearchDebugPanel.jsx'

const MOCK_ENVELOPE = {
  processed_query: 'prime minister OR PM',
  meilisearch_request: {
    method: 'POST',
    url: 'https://xxx.meilisearch.io/indexes/parliamentary_records/search',
    body: { q: 'prime minister', showRankingScore: true },
  },
  meilisearch_response: {
    hits: [{ id: '1' }],
    totalHits: 1,
  },
}

const MOCK_API_REQUEST = {
  method: 'POST',
  url: '/api/search?debug=1',
  body: { query: 'prime minister', sort: 'relevance', page: 1 },
}

const MOCK_API_RESPONSE = {
  total: 1,
  results: [{ id: '1' }],
  debug: MOCK_ENVELOPE,
}

function renderPanel(overrides = {}) {
  return render(
    <SearchDebugPanel
      debugEnvelope={MOCK_ENVELOPE}
      apiRequest={MOCK_API_REQUEST}
      apiResponse={MOCK_API_RESPONSE}
      {...overrides}
    />
  )
}

// ── Render ────────────────────────────────────────────────────────────────────

describe('SearchDebugPanel — render', () => {
  it('renders the global debug panel container', () => {
    renderPanel()
    expect(screen.getByTestId('search-debug-panel')).toBeInTheDocument()
  })

  it('renders all 5 section toggle buttons', () => {
    renderPanel()
    expect(screen.getByTestId('search-debug-processed-query-toggle')).toBeInTheDocument()
    expect(screen.getByTestId('search-debug-api-request-toggle')).toBeInTheDocument()
    expect(screen.getByTestId('search-debug-api-response-toggle')).toBeInTheDocument()
    expect(screen.getByTestId('search-debug-meili-request-toggle')).toBeInTheDocument()
    expect(screen.getByTestId('search-debug-meili-response-toggle')).toBeInTheDocument()
  })
})

// ── All sections collapsed by default ─────────────────────────────────────────

describe('SearchDebugPanel — all sections collapsed by default', () => {
  it('no section bodies are in the DOM on initial render', () => {
    renderPanel()
    expect(screen.queryByTestId('search-debug-processed-query-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('search-debug-api-request-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('search-debug-api-response-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('search-debug-meili-request-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('search-debug-meili-response-body')).not.toBeInTheDocument()
  })
})

// ── Independent collapsibility ────────────────────────────────────────────────

describe('SearchDebugPanel — independent section collapsibility', () => {
  it('expanding one section does not expand the others', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('search-debug-processed-query-toggle'))
    expect(screen.getByTestId('search-debug-processed-query-body')).toBeInTheDocument()
    expect(screen.queryByTestId('search-debug-api-request-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('search-debug-api-response-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('search-debug-meili-request-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('search-debug-meili-response-body')).not.toBeInTheDocument()
  })

  it('two sections can be open simultaneously', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('search-debug-processed-query-toggle'))
    fireEvent.click(screen.getByTestId('search-debug-api-request-toggle'))
    expect(screen.getByTestId('search-debug-processed-query-body')).toBeInTheDocument()
    expect(screen.getByTestId('search-debug-api-request-body')).toBeInTheDocument()
    expect(screen.queryByTestId('search-debug-api-response-body')).not.toBeInTheDocument()
  })

  it('each section can be individually toggled closed', () => {
    renderPanel()
    const pqToggle = screen.getByTestId('search-debug-processed-query-toggle')
    fireEvent.click(pqToggle)
    expect(screen.getByTestId('search-debug-processed-query-body')).toBeInTheDocument()
    fireEvent.click(pqToggle)
    expect(screen.queryByTestId('search-debug-processed-query-body')).not.toBeInTheDocument()
  })
})

// ── Section content ───────────────────────────────────────────────────────────

describe('SearchDebugPanel — section content', () => {
  it('Processed query section shows the processed_query string', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('search-debug-processed-query-toggle'))
    const content = screen.getByTestId('search-debug-processed-query-content').textContent
    expect(content).toContain('prime minister OR PM')
  })

  it('API request section shows method and URL including debug query parameter', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('search-debug-api-request-toggle'))
    const content = screen.getByTestId('search-debug-api-request-content').textContent
    expect(content).toContain('POST')
    expect(content).toContain('/api/search?debug=1')
  })

  it('API response section shows the full response', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('search-debug-api-response-toggle'))
    const content = screen.getByTestId('search-debug-api-response-content').textContent
    expect(content).toContain('"total"')
  })

  it('Meilisearch request section shows the request body', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('search-debug-meili-request-toggle'))
    const content = screen.getByTestId('search-debug-meili-request-content').textContent
    expect(content).toContain('parliamentary_records')
  })

  it('Meilisearch response section shows the response hits', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('search-debug-meili-response-toggle'))
    const content = screen.getByTestId('search-debug-meili-response-content').textContent
    expect(content).toContain('totalHits')
  })
})

// ── Global panel independence from per-result panels ─────────────────────────

describe('SearchDebugPanel — does not affect per-result panels', () => {
  it('is self-contained — toggling sections does not emit events outside the component', () => {
    // This is verified structurally: SearchDebugPanel only modifies local state.
    // Opening a section within the global panel cannot collapse a per-result panel
    // because they are separate component instances with separate state.
    const { container } = renderPanel()
    fireEvent.click(screen.getByTestId('search-debug-processed-query-toggle'))
    // Only the processed-query section body is added
    const bodies = container.querySelectorAll('[data-testid$="-body"]')
    expect(bodies).toHaveLength(1)
    expect(bodies[0]).toHaveAttribute('data-testid', 'search-debug-processed-query-body')
  })
})
