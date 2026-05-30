import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import SavedSearchesPanel from '../components/SavedSearchesPanel.jsx'
import { defaultFilterState } from '../lib/filterState.js'

function makeEntry(overrides = {}) {
  return {
    id: `id-${Math.random()}`,
    name: 'My search',
    query: 'water rights',
    filters: defaultFilterState(),
    timestamp: Date.now(),
    ...overrides,
  }
}

function renderPanel(props = {}) {
  const defaults = {
    entries: [makeEntry()],
    atLimit: false,
    visible: true,
    showSaveButton: true,
    onRunSearch: vi.fn(),
    onSave: vi.fn(),
    onDelete: vi.fn(),
    onRename: vi.fn(),
    onToast: vi.fn(),
    onDismiss: vi.fn(),
  }
  return render(<SavedSearchesPanel {...defaults} {...props} />)
}

describe('SavedSearchesPanel — visibility', () => {
  it('renders nothing when visible is false', () => {
    renderPanel({ visible: false })
    expect(screen.queryByTestId('saved-searches-panel')).toBeNull()
  })

  it('renders the panel when visible is true', () => {
    renderPanel({ visible: true })
    expect(screen.getByTestId('saved-searches-panel')).toBeInTheDocument()
  })
})

describe('SavedSearchesPanel — empty state', () => {
  it('shows empty state when no entries', () => {
    renderPanel({ entries: [] })
    expect(screen.getByTestId('saved-searches-empty')).toBeInTheDocument()
    expect(screen.getByText('No saved searches yet.')).toBeInTheDocument()
  })

  it('does not show items when entries is empty', () => {
    renderPanel({ entries: [] })
    expect(screen.queryAllByTestId('saved-search-item')).toHaveLength(0)
  })
})

describe('SavedSearchesPanel — entries', () => {
  it('renders each entry', () => {
    const entries = [
      makeEntry({ name: 'First search', query: 'alpha' }),
      makeEntry({ name: 'Second search', query: 'beta' }),
    ]
    renderPanel({ entries })
    expect(screen.getByText('First search')).toBeInTheDocument()
    expect(screen.getByText('Second search')).toBeInTheDocument()
    expect(screen.getAllByTestId('saved-search-item')).toHaveLength(2)
  })

  it('shows filter summary "No filters" for default filter state', () => {
    renderPanel({ entries: [makeEntry({ filters: defaultFilterState() })] })
    expect(screen.getByText('No filters')).toBeInTheDocument()
  })

  it('shows filter summary with source name for non-default sources', () => {
    const filters = { ...defaultFilterState(), sources: ['RS'] }
    renderPanel({ entries: [makeEntry({ filters })] })
    expect(screen.getByText(/Rajya Sabha/)).toBeInTheDocument()
  })

  it('shows date range in filter summary', () => {
    const filters = { ...defaultFilterState(), date_from: '2020-01-01', date_to: '2024-12-31' }
    renderPanel({ entries: [makeEntry({ filters })] })
    expect(screen.getByText(/2020–2024/)).toBeInTheDocument()
  })
})

describe('SavedSearchesPanel — run search', () => {
  it('calls onRunSearch with the entry when item text is clicked', () => {
    const onRunSearch = vi.fn()
    const entry = makeEntry({ name: 'Test search' })
    renderPanel({ entries: [entry], onRunSearch })
    fireEvent.click(screen.getByTestId('saved-search-run-btn'))
    expect(onRunSearch).toHaveBeenCalledWith(entry)
  })
})

describe('SavedSearchesPanel — delete', () => {
  it('calls onDelete with the entry id when trash icon is clicked', () => {
    const onDelete = vi.fn()
    const entry = makeEntry({ id: 'test-id-123' })
    renderPanel({ entries: [entry], onDelete })
    fireEvent.click(screen.getByTestId('saved-search-delete-btn'))
    expect(onDelete).toHaveBeenCalledWith('test-id-123')
  })

  it('calls onToast with "Search removed" on delete', () => {
    const onToast = vi.fn()
    renderPanel({ onToast })
    fireEvent.click(screen.getByTestId('saved-search-delete-btn'))
    expect(onToast).toHaveBeenCalledWith('Search removed')
  })
})

describe('SavedSearchesPanel — rename', () => {
  it('shows rename input when pencil icon is clicked', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('saved-search-rename-btn'))
    expect(screen.getByTestId('saved-search-rename-input')).toBeInTheDocument()
  })

  it('pre-populates rename input with current entry name', () => {
    const entry = makeEntry({ name: 'Original name' })
    renderPanel({ entries: [entry] })
    fireEvent.click(screen.getByTestId('saved-search-rename-btn'))
    expect(screen.getByTestId('saved-search-rename-input')).toHaveValue('Original name')
  })

  it('calls onRename with id and new name on confirm', () => {
    const onRename = vi.fn()
    const entry = makeEntry({ id: 'rename-id', name: 'Old name' })
    renderPanel({ entries: [entry], onRename })
    fireEvent.click(screen.getByTestId('saved-search-rename-btn'))
    fireEvent.change(screen.getByTestId('saved-search-rename-input'), {
      target: { value: 'New name' },
    })
    fireEvent.click(screen.getByTestId('saved-search-rename-confirm'))
    expect(onRename).toHaveBeenCalledWith('rename-id', 'New name')
  })

  it('hides rename input on cancel without calling onRename', () => {
    const onRename = vi.fn()
    renderPanel({ onRename })
    fireEvent.click(screen.getByTestId('saved-search-rename-btn'))
    fireEvent.click(screen.getByTestId('saved-search-rename-cancel'))
    expect(screen.queryByTestId('saved-search-rename-input')).toBeNull()
    expect(onRename).not.toHaveBeenCalled()
  })

  it('confirms rename on Enter key in the input', () => {
    const onRename = vi.fn()
    const entry = makeEntry({ id: 'kb-id' })
    renderPanel({ entries: [entry], onRename })
    fireEvent.click(screen.getByTestId('saved-search-rename-btn'))
    fireEvent.change(screen.getByTestId('saved-search-rename-input'), {
      target: { value: 'Keyboard name' },
    })
    fireEvent.keyDown(screen.getByTestId('saved-search-rename-input'), { key: 'Enter' })
    expect(onRename).toHaveBeenCalledWith('kb-id', 'Keyboard name')
  })

  it('cancels rename on Escape key in the input', () => {
    const onRename = vi.fn()
    renderPanel({ onRename })
    fireEvent.click(screen.getByTestId('saved-search-rename-btn'))
    fireEvent.keyDown(screen.getByTestId('saved-search-rename-input'), { key: 'Escape' })
    expect(screen.queryByTestId('saved-search-rename-input')).toBeNull()
    expect(onRename).not.toHaveBeenCalled()
  })

  it('enforces maxLength of 60 on the rename input', () => {
    renderPanel()
    fireEvent.click(screen.getByTestId('saved-search-rename-btn'))
    const input = screen.getByTestId('saved-search-rename-input')
    expect(input).toHaveAttribute('maxlength', '60')
  })
})

describe('SavedSearchesPanel — save button', () => {
  it('renders save button when showSaveButton is true', () => {
    renderPanel({ showSaveButton: true })
    expect(screen.getByTestId('saved-search-save-btn')).toBeInTheDocument()
  })

  it('does not render save button when showSaveButton is false', () => {
    renderPanel({ showSaveButton: false })
    expect(screen.queryByTestId('saved-search-save-btn')).toBeNull()
  })

  it('calls onSave and onToast("Search saved") when save button is clicked', () => {
    const onSave = vi.fn()
    const onToast = vi.fn()
    renderPanel({ onSave, onToast, atLimit: false })
    fireEvent.click(screen.getByTestId('saved-search-save-btn'))
    expect(onSave).toHaveBeenCalled()
    expect(onToast).toHaveBeenCalledWith('Search saved')
  })

  it('save button is disabled when atLimit is true', () => {
    renderPanel({ atLimit: true })
    const btn = screen.getByTestId('saved-search-save-btn')
    expect(btn).toBeDisabled()
  })

  it('shows limit message when atLimit is true', () => {
    renderPanel({ atLimit: true })
    expect(screen.getByTestId('saved-search-limit-msg')).toBeInTheDocument()
    expect(screen.getByText('Saved searches full — delete one to save')).toBeInTheDocument()
  })

  it('does not call onSave when atLimit is true and button is clicked', () => {
    const onSave = vi.fn()
    renderPanel({ atLimit: true, onSave })
    const btn = screen.getByTestId('saved-search-save-btn')
    // button is disabled so click should not fire
    fireEvent.click(btn)
    expect(onSave).not.toHaveBeenCalled()
  })

  it('does not show limit message when atLimit is false', () => {
    renderPanel({ atLimit: false })
    expect(screen.queryByTestId('saved-search-limit-msg')).toBeNull()
  })
})

describe('SavedSearchesPanel — dismiss', () => {
  it('calls onDismiss on outside click', () => {
    const onDismiss = vi.fn()
    renderPanel({ onDismiss })
    fireEvent.mouseDown(document.body)
    expect(onDismiss).toHaveBeenCalled()
  })

  it('calls onDismiss on Escape key', () => {
    const onDismiss = vi.fn()
    renderPanel({ onDismiss })
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(onDismiss).toHaveBeenCalled()
  })

  it('does not call onDismiss when clicking inside the panel', () => {
    const onDismiss = vi.fn()
    renderPanel({ onDismiss })
    fireEvent.mouseDown(screen.getByTestId('saved-searches-panel'))
    expect(onDismiss).not.toHaveBeenCalled()
  })
})
