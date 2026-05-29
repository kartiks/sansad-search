import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

import Home from '../pages/Home.jsx'
import { makeStatusResponse } from './fixtures.js'

function renderHome(initialEntries = ['/']) {
  const navigateSpy = { current: null }
  function NavCapture() {
    const location = window.location.pathname + window.location.search
    return <div data-testid="here">{location}</div>
  }
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route
          path="/search"
          element={
            <div data-testid="results-page">
              <span data-testid="results-query">{useSearchString()}</span>
            </div>
          }
        />
      </Routes>
    </MemoryRouter>
  )
}

function useSearchString() {
  return window.location.search
}

beforeEach(() => {
  global.fetch = vi.fn()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('Home — layout', () => {
  it('renders wordmark, tagline, and search bar', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    expect(screen.getByText('SansadSearch')).toBeInTheDocument()
    expect(
      screen.getByText('Search the complete record of Indian parliamentary debates.')
    ).toBeInTheDocument()
    expect(screen.getByTestId('home-search-input')).toBeInTheDocument()
  })

  it('renders the Advanced Search link and bookmark icon as placeholders', () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    expect(screen.getByTestId('home-advanced-search-link')).toBeInTheDocument()
    expect(screen.getByTestId('home-bookmark-btn')).toBeInTheDocument()
  })
})

describe('Home — search bar inline validation (F02)', () => {
  it('shows validation when query is empty', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('home-search-submit'))
    expect(await screen.findByTestId('home-validation')).toHaveTextContent(
      'Enter at least 2 characters to search.'
    )
  })

  it('shows validation when query is only one non-whitespace character', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    const input = screen.getByTestId('home-search-input')
    fireEvent.change(input, { target: { value: '  a  ' } })
    fireEvent.click(screen.getByTestId('home-search-submit'))
    expect(await screen.findByTestId('home-validation')).toBeInTheDocument()
  })

  it('dismisses validation when user resumes typing', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('home-search-submit'))
    expect(await screen.findByTestId('home-validation')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('home-search-input'), {
      target: { value: 'r' },
    })
    expect(screen.queryByTestId('home-validation')).toBeNull()
  })

  it('does not navigate when validation fails', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/search" element={<div data-testid="results-page" />} />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('home-search-submit'))
    expect(screen.queryByTestId('results-page')).toBeNull()
  })
})

describe('Home — submit navigation', () => {
  it('navigates to /search?q=...&page=1 on submit', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route
            path="/search"
            element={
              <div data-testid="results-page">
                <span data-testid="search-string">{window.location.search}</span>
              </div>
            }
          />
        </Routes>
      </MemoryRouter>
    )
    fireEvent.change(screen.getByTestId('home-search-input'), {
      target: { value: 'fundamental rights' },
    })
    fireEvent.click(screen.getByTestId('home-search-submit'))
    expect(await screen.findByTestId('results-page')).toBeInTheDocument()
  })
})

describe('Home — status strip (F07)', () => {
  it('renders the strip with counts and formatted date', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse(),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    await waitFor(() => {
      const text = screen.getByTestId('status-strip').textContent
      expect(text).toContain('Indexed')
      expect(text).toContain('Constituent Assembly')
      expect(text).toContain('Lok Sabha')
      expect(text).toContain('Rajya Sabha')
      expect(text).toContain('15 May 2026')
    })
  })

  it('formats counts with thousands separators', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse({
        sources: {
          ca: { count: 8200, date_from: '1946-12-09', date_to: '1950-11-26' },
          ls: { count: 198000, date_from: '2014-06-04', date_to: '2026-05-15' },
          rs: { count: 143800, date_from: '2014-06-11', date_to: '2026-04-20' },
        },
      }),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    await waitFor(() => {
      const text = screen.getByTestId('status-strip').textContent
      expect(text).toContain('8,200')
      expect(text).toContain('198,000')
      expect(text).toContain('143,800')
    })
  })

  it('shows a zero-count source as "0 [Body] records" in the strip (not omitted)', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse({
        sources: {
          ca: { count: 0, date_from: null, date_to: null },
          ls: { count: 198000, date_from: '2014-06-04', date_to: '2026-05-15' },
          rs: { count: 143800, date_from: '2014-06-11', date_to: '2026-04-20' },
        },
      }),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    await waitFor(() => {
      const text = screen.getByTestId('status-strip').textContent
      expect(text).toContain('0 Constituent Assembly records')
      expect(text).toContain('198,000 Lok Sabha records')
    })
  })

  it('renders "Never" for last_updated when null (fresh deploy)', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => makeStatusResponse({
        total_records: 0,
        sources: {
          ca: { count: 0, date_from: null, date_to: null },
          ls: { count: 0, date_from: null, date_to: null },
          rs: { count: 0, date_from: null, date_to: null },
        },
        last_updated: null,
      }),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByTestId('status-strip').textContent).toContain(
        'Last updated: Never'
      )
    })
  })

  it('renders "Status unavailable" when fetch fails', async () => {
    global.fetch.mockRejectedValue(new Error('network down'))
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByTestId('status-strip').textContent).toContain(
        'Status unavailable'
      )
    })
  })

  it('renders "Status unavailable" when API returns status=unavailable', async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'unavailable' }),
    })
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    await waitFor(() => {
      expect(screen.getByTestId('status-strip').textContent).toContain(
        'Status unavailable'
      )
    })
  })
})

describe('Home — Advanced Search modal (F03 UI)', () => {
  beforeEach(() => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'unavailable' }),
    })
  })

  it('clicking Advanced Search opens the modal', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    expect(screen.queryByTestId('advanced-search-modal')).toBeNull()
    fireEvent.click(screen.getByTestId('home-advanced-search-link'))
    expect(screen.getByTestId('advanced-search-modal')).toBeInTheDocument()
  })

  it('modal close button closes the modal', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('home-advanced-search-link'))
    expect(screen.getByTestId('advanced-search-modal')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('modal-close'))
    expect(screen.queryByTestId('advanced-search-modal')).toBeNull()
  })

  it('applying filters in modal stores them (modal closes)', () => {
    render(
      <MemoryRouter>
        <Home />
      </MemoryRouter>
    )
    fireEvent.click(screen.getByTestId('home-advanced-search-link'))
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))
    expect(screen.queryByTestId('advanced-search-modal')).toBeNull()
  })
})
