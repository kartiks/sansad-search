import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import ResultCard from '../components/ResultCard.jsx'
import { makeSpeechResult, makeQAResult } from './fixtures.js'

function LocationDisplay() {
  const location = useLocation()
  return <div data-testid="location">{location.pathname}</div>
}

function renderCard(result) {
  return render(
    <MemoryRouter>
      <ResultCard result={result} />
    </MemoryRouter>
  )
}

function renderCardWithRouter(result) {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<ResultCard result={result} />} />
        <Route path="/record/:id" element={<LocationDisplay />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('ResultCard — dispatcher', () => {
  it('renders SpeechCard for record_type=speech', () => {
    renderCard(makeSpeechResult())
    expect(screen.getByTestId('speech-card')).toBeInTheDocument()
    expect(screen.queryByTestId('qa-card')).toBeNull()
  })

  it('renders QACard for record_type=qa', () => {
    renderCard(makeQAResult())
    expect(screen.getByTestId('qa-card')).toBeInTheDocument()
    expect(screen.queryByTestId('speech-card')).toBeNull()
  })

  it('renders nothing for null', () => {
    const { container } = renderCard(null)
    expect(container.firstChild).toBeNull()
  })
})

describe('ResultCard — card wrapper is not itself a link', () => {
  it('speech card is not wrapped in an anchor element', () => {
    renderCard(makeSpeechResult({ id: 'speech-1' }))
    const card = screen.getByTestId('speech-card')
    expect(card.closest('a')).toBeNull()
  })

  it('qa card is not wrapped in an anchor element', () => {
    renderCard(makeQAResult({ id: 'qa-1' }))
    const card = screen.getByTestId('qa-card')
    expect(card.closest('a')).toBeNull()
  })
})

describe('ResultCard — Details link navigates to /record/:id', () => {
  it('Details link on speech card navigates to /record/:id', () => {
    renderCardWithRouter(makeSpeechResult({ id: 'speech-1' }))
    fireEvent.click(screen.getByTestId('details-link'))
    expect(screen.getByTestId('location')).toHaveTextContent('/record/speech-1')
  })

  it('Details link on qa card navigates to /record/:id', () => {
    renderCardWithRouter(makeQAResult({ id: 'qa-1' }))
    fireEvent.click(screen.getByTestId('details-link'))
    expect(screen.getByTestId('location')).toHaveTextContent('/record/qa-1')
  })

  it('Details link uses the result id field', () => {
    renderCardWithRouter(makeSpeechResult({ id: 'custom-id-xyz' }))
    fireEvent.click(screen.getByTestId('details-link'))
    expect(screen.getByTestId('location')).toHaveTextContent('/record/custom-id-xyz')
  })
})

// ── Debug mode (F10) ──────────────────────────────────────────────────────────

import { vi, beforeEach, afterEach } from 'vitest'
import { act, waitFor } from '@testing-library/react'

function mockFetchOk() {
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
  )
}

beforeEach(() => { vi.clearAllMocks() })
afterEach(() => { if (global.fetch) delete global.fetch })

function makeDebugResult(overrides = {}) {
  return {
    ...makeSpeechResult({ id: 'debug-1' }),
    _rankingScore: 0.9,
    _meili_document: { id: 'debug-1', source: 'LS' },
    ...overrides,
  }
}

describe('ResultCard — normal mode has no debug DOM elements', () => {
  it('renders no debug panel toggle when debug=false (default)', () => {
    renderCard(makeSpeechResult())
    expect(screen.queryByTestId('debug-panel-toggle')).toBeNull()
  })

  it('renders no debug panel container when debug=false', () => {
    renderCard(makeSpeechResult())
    expect(screen.queryByTestId('result-debug-panel-wrap')).toBeNull()
  })

  it('renders no debug section headers when debug=false', () => {
    renderCard(makeSpeechResult())
    expect(screen.queryByTestId('debug-section-scoring')).toBeNull()
    expect(screen.queryByTestId('debug-section-processed')).toBeNull()
    expect(screen.queryByTestId('debug-section-raw')).toBeNull()
  })
})

describe('ResultCard — debug mode renders debug panel', () => {
  function renderDebugCard(result, overrides = {}) {
    return render(
      <MemoryRouter>
        <ResultCard result={result} debug={true} {...overrides} />
      </MemoryRouter>
    )
  }

  it('renders the debug toggle when debug=true', () => {
    mockFetchOk()
    renderDebugCard(makeDebugResult())
    expect(screen.getByTestId('debug-panel-toggle')).toBeInTheDocument()
  })

  it('debug panel wrap is in the DOM when debug=true', () => {
    mockFetchOk()
    renderDebugCard(makeDebugResult())
    expect(screen.getByTestId('result-debug-panel-wrap')).toBeInTheDocument()
  })

  it('panel opens when Debug toggle is clicked', () => {
    mockFetchOk()
    renderDebugCard(makeDebugResult())
    fireEvent.click(screen.getByTestId('debug-panel-toggle'))
    expect(screen.getByTestId('result-debug-panel')).toBeInTheDocument()
  })

  it('card content (speech card) still renders in debug mode', () => {
    mockFetchOk()
    renderDebugCard(makeDebugResult())
    expect(screen.getByTestId('speech-card')).toBeInTheDocument()
  })
})
