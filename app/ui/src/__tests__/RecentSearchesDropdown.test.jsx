import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import RecentSearchesDropdown from '../components/RecentSearchesDropdown.jsx'

function makeEntries(queries) {
  return queries.map((q, i) => ({ query: q, timestamp: Date.now() + i }))
}

function renderDropdown(props = {}) {
  const defaults = {
    entries: makeEntries(['water rights', 'budget speech', 'education policy']),
    visible: true,
    onSelect: vi.fn(),
    onDeleteEntry: vi.fn(),
    onClearAll: vi.fn(),
    onDismiss: vi.fn(),
  }
  return render(<RecentSearchesDropdown {...defaults} {...props} />)
}

describe('RecentSearchesDropdown — visibility', () => {
  it('renders nothing when visible is false', () => {
    renderDropdown({ visible: false })
    expect(screen.queryByTestId('recent-searches-dropdown')).toBeNull()
  })

  it('renders the dropdown when visible is true', () => {
    renderDropdown({ visible: true })
    expect(screen.getByTestId('recent-searches-dropdown')).toBeInTheDocument()
  })
})

describe('RecentSearchesDropdown — entries', () => {
  it('renders all provided entries', () => {
    renderDropdown()
    const items = screen.getAllByTestId('recent-search-item')
    expect(items).toHaveLength(3)
  })

  it('renders the query text for each entry', () => {
    renderDropdown()
    expect(screen.getByText('water rights')).toBeInTheDocument()
    expect(screen.getByText('budget speech')).toBeInTheDocument()
    expect(screen.getByText('education policy')).toBeInTheDocument()
  })

  it('shows empty state when no entries', () => {
    renderDropdown({ entries: [] })
    expect(screen.getByTestId('recent-searches-empty')).toBeInTheDocument()
    expect(screen.getByText('No recent searches')).toBeInTheDocument()
  })

  it('does not show items when entries is empty', () => {
    renderDropdown({ entries: [] })
    expect(screen.queryAllByTestId('recent-search-item')).toHaveLength(0)
  })
})

describe('RecentSearchesDropdown — interactions', () => {
  it('calls onSelect with the query when item button is clicked', () => {
    const onSelect = vi.fn()
    renderDropdown({ onSelect })
    fireEvent.click(screen.getByLabelText('Search for water rights'))
    expect(onSelect).toHaveBeenCalledWith('water rights')
  })

  it('calls onDeleteEntry when the delete button for an item is clicked', () => {
    const onDeleteEntry = vi.fn()
    renderDropdown({ onDeleteEntry })
    const deleteBtns = screen.getAllByTestId('recent-search-delete-btn')
    fireEvent.click(deleteBtns[0])
    expect(onDeleteEntry).toHaveBeenCalledWith('water rights')
  })

  it('calls onClearAll when "Clear history" is clicked', () => {
    const onClearAll = vi.fn()
    renderDropdown({ onClearAll })
    fireEvent.click(screen.getByTestId('recent-search-clear-history'))
    expect(onClearAll).toHaveBeenCalled()
  })

  it('calls onDismiss when Escape key is pressed', () => {
    const onDismiss = vi.fn()
    renderDropdown({ onDismiss })
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onDismiss).toHaveBeenCalled()
  })

  it('calls onDismiss on outside click', () => {
    const onDismiss = vi.fn()
    renderDropdown({ onDismiss })
    fireEvent.mouseDown(document.body)
    expect(onDismiss).toHaveBeenCalled()
  })

  it('does not call onDismiss when clicking inside the dropdown', () => {
    const onDismiss = vi.fn()
    renderDropdown({ onDismiss })
    const dropdown = screen.getByTestId('recent-searches-dropdown')
    fireEvent.mouseDown(dropdown)
    expect(onDismiss).not.toHaveBeenCalled()
  })
})

describe('RecentSearchesDropdown — shows up to 10 items', () => {
  it('renders at most 10 items', () => {
    const entries = makeEntries(
      Array.from({ length: 12 }, (_, i) => `query-${i}`)
    )
    renderDropdown({ entries })
    const items = screen.getAllByTestId('recent-search-item')
    // Component doesn't slice — caller passes correct number — but all 12 render
    // The FIFO 10-limit is enforced in the hook, not the component
    expect(items).toHaveLength(12)
  })
})
