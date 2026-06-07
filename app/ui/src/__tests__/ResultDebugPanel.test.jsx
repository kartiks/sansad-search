import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ResultDebugPanel from '../components/ResultDebugPanel.jsx'
import { makeSpeechResult } from './fixtures.js'

// Default debug-mode result fixture (includes _rankingScore, _meili_document)
function makeDebugResult(overrides = {}) {
  return {
    ...makeSpeechResult(),
    _rankingScore: 0.87,
    _rankingScoreDetails: { words: { order: 0 } },
    _meili_document: { id: 'speech-1', source: 'LS', subject: 'Test subject' },
    ...overrides,
  }
}

function renderPanel(result) {
  return render(
    <MemoryRouter>
      <ResultDebugPanel result={result || makeDebugResult()} />
    </MemoryRouter>
  )
}

function mockFetch(url, payload, status = 200) {
  global.fetch = vi.fn((fetchUrl) => {
    if (fetchUrl.includes(url)) {
      return Promise.resolve({
        ok: status === 200,
        status,
        json: async () => payload,
      })
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
  })
}

beforeEach(() => { vi.clearAllMocks() })
afterEach(() => { delete global.fetch })

// ── Render / toggle ───────────────────────────────────────────────────────────

describe('ResultDebugPanel — render and top-level toggle', () => {
  it('renders the "Debug" toggle button', () => {
    renderPanel()
    expect(screen.getByTestId('debug-panel-toggle')).toBeInTheDocument()
  })

  it('panel is closed by default — inner sections not in DOM', () => {
    renderPanel()
    expect(screen.queryByTestId('result-debug-panel')).not.toBeInTheDocument()
  })

  it('clicking "Debug" opens the panel showing all 4 section headers', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    expect(screen.getByTestId('result-debug-panel')).toBeInTheDocument()
    expect(screen.getByTestId('debug-section-scoring')).toBeInTheDocument()
    expect(screen.getByTestId('debug-section-document')).toBeInTheDocument()
    expect(screen.getByTestId('debug-section-processed')).toBeInTheDocument()
    expect(screen.getByTestId('debug-section-raw')).toBeInTheDocument()
  })

  it('clicking "Debug" again closes the panel', () => {
    renderPanel()
    const toggle = screen.getByTestId('debug-panel-toggle')
    fireEvent.click(toggle)
    fireEvent.click(toggle)
    expect(screen.queryByTestId('result-debug-panel')).not.toBeInTheDocument()
  })
})

// ── Section collapse/expand ───────────────────────────────────────────────────

describe('ResultDebugPanel — sections all collapsed by default', () => {
  it('all 4 sections start collapsed (bodies not in DOM)', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    expect(screen.queryByTestId('debug-section-scoring-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-document-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-processed-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-raw-body')).not.toBeInTheDocument()
  })
})

describe('ResultDebugPanel — independent section collapse', () => {
  it('expanding Scoring details does not expand other sections', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-scoring-toggle'))
    expect(screen.getByTestId('debug-section-scoring-body')).toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-document-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-processed-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-raw-body')).not.toBeInTheDocument()
  })

  it('expanding Document in index does not expand other sections', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-document-toggle'))
    expect(screen.getByTestId('debug-section-document-body')).toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-scoring-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-processed-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-raw-body')).not.toBeInTheDocument()
  })

  it('each of the 4 sections can be independently toggled', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))

    fireEvent.click(screen.getByTestId('debug-section-scoring-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-document-toggle'))

    expect(screen.getByTestId('debug-section-scoring-body')).toBeInTheDocument()
    expect(screen.getByTestId('debug-section-document-body')).toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-processed-body')).not.toBeInTheDocument()
    expect(screen.queryByTestId('debug-section-raw-body')).not.toBeInTheDocument()
  })
})

// ── Scoring details section ───────────────────────────────────────────────────

describe('ResultDebugPanel — Scoring details section', () => {
  it('shows _rankingScore when expanded', () => {
    renderPanel(makeDebugResult({ _rankingScore: 0.95 }))
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-scoring-toggle'))
    const content = screen.getByTestId('debug-scoring-content').textContent
    expect(content).toContain('0.95')
  })

  it('shows _rankingScoreDetails when present', () => {
    renderPanel(makeDebugResult({ _rankingScoreDetails: { words: { order: 0 } } }))
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-scoring-toggle'))
    const content = screen.getByTestId('debug-scoring-content').textContent
    expect(content).toContain('_rankingScoreDetails')
  })

  it('shows only _rankingScore when _rankingScoreDetails is absent — section renders without crash', () => {
    const result = { ...makeDebugResult() }
    delete result._rankingScoreDetails
    renderPanel(result)
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-scoring-toggle'))
    const content = screen.getByTestId('debug-scoring-content').textContent
    expect(content).toContain('0.87')
    expect(content).not.toContain('_rankingScoreDetails')
  })
})

// ── Document in index section ─────────────────────────────────────────────────

describe('ResultDebugPanel — Document in index section', () => {
  it('renders the _meili_document content when expanded', () => {
    renderPanel(makeDebugResult({ _meili_document: { id: 'x', custom_field: 'hello' } }))
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-document-toggle'))
    const content = screen.getByTestId('debug-document-content').textContent
    expect(content).toContain('custom_field')
    expect(content).toContain('hello')
  })

  it('does not trigger any fetch (data is from the result prop)', () => {
    global.fetch = vi.fn()
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-document-toggle'))
    expect(global.fetch).not.toHaveBeenCalled()
  })
})

// ── Processed record section — lazy fetch and caching ────────────────────────

describe('ResultDebugPanel — Processed record section', () => {
  it('does not fetch on mount or panel open', async () => {
    global.fetch = vi.fn()
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('triggers a fetch on first expand of Processed record', async () => {
    const payload = { table: 'speeches', row: { subject: 'Test' } }
    mockFetch('debug/processed', payload)
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-processed-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-processed-content')).toBeInTheDocument()
    )
    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(global.fetch.mock.calls[0][0]).toContain('debug/processed')
  })

  it('shows data after successful fetch', async () => {
    const payload = { table: 'speeches', row: { subject: 'Budget debate' } }
    mockFetch('debug/processed', payload)
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-processed-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-processed-content')).toBeInTheDocument()
    )
    expect(screen.getByTestId('debug-processed-content').textContent).toContain('speeches')
  })

  it('collapse then re-expand does not trigger a second fetch', async () => {
    const payload = { table: 'speeches', row: {} }
    mockFetch('debug/processed', payload)
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-processed-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-processed-content')).toBeInTheDocument()
    )
    expect(global.fetch).toHaveBeenCalledTimes(1)

    // Collapse
    fireEvent.click(screen.getByTestId('debug-section-processed-toggle'))
    expect(screen.queryByTestId('debug-processed-content')).not.toBeInTheDocument()

    // Re-expand
    fireEvent.click(screen.getByTestId('debug-section-processed-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-processed-content')).toBeInTheDocument()
    )
    expect(global.fetch).toHaveBeenCalledTimes(1)  // still only 1
  })

  it('shows error message on 404', async () => {
    mockFetch('debug/processed', { error: 'not_found', message: 'Record not found.' }, 404)
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-processed-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-processed-error')).toBeInTheDocument()
    )
    expect(screen.getByTestId('debug-processed-error').textContent).toMatch(/not found/i)
  })

  it('error in Processed record does not affect Document in index', async () => {
    mockFetch('debug/processed', { error: 'not_found' }, 404)
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-processed-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-processed-error')).toBeInTheDocument()
    )
    // Document in index is independent
    fireEvent.click(screen.getByTestId('debug-section-document-toggle'))
    expect(screen.getByTestId('debug-section-document-body')).toBeInTheDocument()
  })
})

// ── Raw document section — lazy fetch and caching ────────────────────────────

describe('ResultDebugPanel — Raw document section', () => {
  it('does not fetch on mount or panel open', async () => {
    global.fetch = vi.fn()
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('triggers a fetch on first expand of Raw document', async () => {
    const payload = { row: { canonical_doc_id: 'abc' } }
    mockFetch('debug/raw', payload)
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-raw-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-raw-content')).toBeInTheDocument()
    )
    expect(global.fetch).toHaveBeenCalledTimes(1)
    expect(global.fetch.mock.calls[0][0]).toContain('debug/raw')
  })

  it('collapse then re-expand does not trigger a second fetch', async () => {
    const payload = { row: {} }
    mockFetch('debug/raw', payload)
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-raw-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-raw-content')).toBeInTheDocument()
    )
    expect(global.fetch).toHaveBeenCalledTimes(1)

    fireEvent.click(screen.getByTestId('debug-section-raw-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-raw-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-raw-content')).toBeInTheDocument()
    )
    expect(global.fetch).toHaveBeenCalledTimes(1)
  })

  it('shows "Raw document not available" message on 404', async () => {
    mockFetch('debug/raw', { error: 'not_found', message: 'Raw document not available.' }, 404)
    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-raw-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-raw-error')).toBeInTheDocument()
    )
    expect(screen.getByTestId('debug-raw-error').textContent).toMatch(/raw document not available/i)
  })

  it('error in Raw document does not affect Processed record', async () => {
    const processedPayload = { table: 'speeches', row: { subject: 'test' } }
    global.fetch = vi.fn((url) => {
      if (url.includes('debug/raw')) {
        return Promise.resolve({
          ok: false, status: 404,
          json: async () => ({ error: 'not_found' }),
        })
      }
      if (url.includes('debug/processed')) {
        return Promise.resolve({
          ok: true, status: 200,
          json: async () => processedPayload,
        })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
    })

    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-raw-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-raw-error')).toBeInTheDocument()
    )

    // Processed record still fetches independently
    fireEvent.click(screen.getByTestId('debug-section-processed-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-processed-content')).toBeInTheDocument()
    )
  })

  it('expanding Processed record does not trigger Raw document fetch', async () => {
    global.fetch = vi.fn((url) => {
      if (url.includes('debug/processed')) {
        return Promise.resolve({
          ok: true, status: 200,
          json: async () => ({ table: 'speeches', row: {} }),
        })
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
    })

    renderPanel()
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    fireEvent.click(screen.getByTestId('debug-section-processed-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('debug-processed-content')).toBeInTheDocument()
    )

    const calls = global.fetch.mock.calls.map((c) => c[0])
    expect(calls.every((url) => !url.includes('debug/raw'))).toBe(true)
  })
})
