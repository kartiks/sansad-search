import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import AdvancedSearchModal from '../components/AdvancedSearchModal.jsx'
import { defaultFilterState } from '../lib/filterState.js'
import { ALL_SOURCES, ALL_PROCEEDING_TYPES } from '../lib/constants.js'

function renderModal(props = {}) {
  const defaults = {
    isOpen: true,
    initialFilters: defaultFilterState(),
    onApply: vi.fn(),
    onClose: vi.fn(),
    ...props,
  }
  return { ...render(<AdvancedSearchModal {...defaults} />), ...defaults }
}

describe('AdvancedSearchModal — rendering', () => {
  it('renders when isOpen=true', () => {
    renderModal()
    expect(screen.getByTestId('advanced-search-modal')).toBeInTheDocument()
    expect(screen.getByText('Advanced Search')).toBeInTheDocument()
  })

  it('does not render when isOpen=false', () => {
    renderModal({ isOpen: false })
    expect(screen.queryByTestId('advanced-search-modal')).toBeNull()
  })

  it('renders all 6 filter sections', () => {
    renderModal()
    expect(screen.getByText('Legislative Body')).toBeInTheDocument()
    expect(screen.getByText('Date Range')).toBeInTheDocument()
    expect(screen.getByText('Speaker')).toBeInTheDocument()
    expect(screen.getByText('Session')).toBeInTheDocument()
    expect(screen.getByText('Subject')).toBeInTheDocument()
    expect(screen.getByText('Proceeding Type')).toBeInTheDocument()
  })

  it('renders all 3 source chips selected by default', () => {
    renderModal()
    expect(screen.getByTestId('source-chip-CA')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('source-chip-LS')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('source-chip-RS')).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders all proceeding type chips selected by default', () => {
    renderModal()
    ALL_PROCEEDING_TYPES.forEach((pt) => {
      expect(screen.getByTestId(`type-chip-${pt}`)).toHaveAttribute('aria-pressed', 'true')
    })
  })
})

describe('AdvancedSearchModal — close behavior', () => {
  it('clicking close button calls onClose', () => {
    const { onClose } = renderModal()
    fireEvent.click(screen.getByTestId('modal-close'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('clicking overlay background calls onClose', () => {
    const { onClose } = renderModal()
    const overlay = screen.getByTestId('advanced-search-modal')
    fireEvent.click(overlay)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('clicking inside modal panel does not call onClose', () => {
    const { onClose } = renderModal()
    fireEvent.click(screen.getByText('Advanced Search'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('pressing Escape calls onClose', () => {
    const { onClose } = renderModal()
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })
})

describe('AdvancedSearchModal — source chips', () => {
  it('clicking a selected source chip deselects it', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    expect(screen.getByTestId('source-chip-CA')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('source-chip-LS')).toHaveAttribute('aria-pressed', 'true')
  })

  it('deselecting all sources shows validation message', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    fireEvent.click(screen.getByTestId('source-chip-RS'))
    expect(screen.getByTestId('source-validation')).toBeInTheDocument()
    expect(screen.getByTestId('source-validation').textContent).toContain(
      'Select at least one source'
    )
  })

  it('Apply button is disabled when all sources deselected', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    fireEvent.click(screen.getByTestId('source-chip-RS'))
    expect(screen.getByTestId('modal-apply')).toBeDisabled()
  })
})

describe('AdvancedSearchModal — date range', () => {
  it('From > To shows validation message and disables Apply', () => {
    renderModal()
    fireEvent.change(screen.getByTestId('date-from-input'), {
      target: { value: '2022-06-01' },
    })
    fireEvent.change(screen.getByTestId('date-to-input'), {
      target: { value: '2021-01-01' },
    })
    expect(screen.getByTestId('date-validation')).toBeInTheDocument()
    expect(screen.getByTestId('date-validation').textContent).toContain(
      'From date must be before To date'
    )
    expect(screen.getByTestId('modal-apply')).toBeDisabled()
  })

  it('valid date range shows no error', () => {
    renderModal()
    fireEvent.change(screen.getByTestId('date-from-input'), {
      target: { value: '2020-01-01' },
    })
    fireEvent.change(screen.getByTestId('date-to-input'), {
      target: { value: '2022-12-31' },
    })
    expect(screen.queryByTestId('date-validation')).toBeNull()
    expect(screen.getByTestId('modal-apply')).not.toBeDisabled()
  })
})

describe('AdvancedSearchModal — proceeding type chips', () => {
  it('deselecting all types shows validation message and disables Apply', () => {
    renderModal()
    ALL_PROCEEDING_TYPES.forEach((pt) => {
      fireEvent.click(screen.getByTestId(`type-chip-${pt}`))
    })
    expect(screen.getByTestId('type-validation')).toBeInTheDocument()
    expect(screen.getByTestId('modal-apply')).toBeDisabled()
  })

  it('CA-only selected disables all non-Debate proceeding type chips', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    fireEvent.click(screen.getByTestId('source-chip-RS'))

    ALL_PROCEEDING_TYPES.forEach((pt) => {
      const chip = screen.getByTestId(`type-chip-${pt}`)
      if (pt === 'debate') {
        expect(chip).not.toBeDisabled()
      } else {
        expect(chip).toBeDisabled()
      }
    })
  })

  it('adding LS back re-enables all proceeding type chips', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    fireEvent.click(screen.getByTestId('source-chip-RS'))
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    ALL_PROCEEDING_TYPES.forEach((pt) => {
      expect(screen.getByTestId(`type-chip-${pt}`)).not.toBeDisabled()
    })
  })

  it('"Select all" selects all non-disabled proceeding type chips', () => {
    renderModal()
    // First deselect all
    ALL_PROCEEDING_TYPES.forEach((pt) => {
      fireEvent.click(screen.getByTestId(`type-chip-${pt}`))
    })
    expect(screen.getByTestId('modal-apply')).toBeDisabled()
    fireEvent.click(screen.getByTestId('type-select-all'))
    ALL_PROCEEDING_TYPES.forEach((pt) => {
      expect(screen.getByTestId(`type-chip-${pt}`)).toHaveAttribute('aria-pressed', 'true')
    })
    expect(screen.getByTestId('modal-apply')).not.toBeDisabled()
  })

  it('"Clear" in CA-only mode sets all type chips to aria-pressed=false and Apply remains enabled', () => {
    renderModal()
    // Switch to CA-only: deselect LS and RS
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    fireEvent.click(screen.getByTestId('source-chip-RS'))
    // In CA-only mode, only the debate chip is enabled and selected
    expect(screen.getByTestId('type-chip-debate')).toHaveAttribute('aria-pressed', 'true')
    // Click Clear — removes debate from proceeding_types; non-debate types remain in state
    fireEvent.click(screen.getByTestId('type-clear'))
    // All chips show aria-pressed=false: debate is now deselected; non-debate chips are
    // disabled (aria-pressed = selected && !disabled = false regardless of state value)
    ALL_PROCEEDING_TYPES.forEach((pt) => {
      expect(screen.getByTestId(`type-chip-${pt}`)).toHaveAttribute('aria-pressed', 'false')
    })
    // Apply must remain enabled: non-debate types are still in proceeding_types,
    // so proceeding_types.length > 0 and validation passes
    expect(screen.getByTestId('modal-apply')).not.toBeDisabled()
  })
})

describe('AdvancedSearchModal — Apply', () => {
  it('Apply calls onApply with correct filter object', () => {
    const { onApply } = renderModal()
    fireEvent.change(screen.getByTestId('speaker-input'), {
      target: { value: 'Ambedkar' },
    })
    fireEvent.change(screen.getByTestId('session-input'), {
      target: { value: 'Budget Session 2023' },
    })
    fireEvent.click(screen.getByTestId('modal-apply'))
    expect(onApply).toHaveBeenCalledOnce()
    const arg = onApply.mock.calls[0][0]
    expect(arg.speaker).toBe('Ambedkar')
    expect(arg.session).toBe('Budget Session 2023')
    expect(arg.sources).toEqual(expect.arrayContaining(['CA', 'LS', 'RS']))
  })

  it('subject input appears and is included in onApply', () => {
    const { onApply } = renderModal()
    fireEvent.change(screen.getByTestId('subject-input'), {
      target: { value: 'MGNREGA' },
    })
    fireEvent.click(screen.getByTestId('modal-apply'))
    const arg = onApply.mock.calls[0][0]
    expect(arg.subject).toBe('MGNREGA')
  })

  it('subject with only whitespace is treated as no subject filter', () => {
    const { onApply } = renderModal()
    fireEvent.change(screen.getByTestId('subject-input'), {
      target: { value: '   ' },
    })
    fireEvent.click(screen.getByTestId('modal-apply'))
    const arg = onApply.mock.calls[0][0]
    expect(arg.subject).toBeNull()
  })

  it('speaker with only whitespace is treated as no speaker filter', () => {
    const { onApply } = renderModal()
    fireEvent.change(screen.getByTestId('speaker-input'), {
      target: { value: '   ' },
    })
    fireEvent.click(screen.getByTestId('modal-apply'))
    const arg = onApply.mock.calls[0][0]
    expect(arg.speaker).toBeNull()
  })

  it('Apply with source subset sends only those sources', () => {
    const { onApply } = renderModal()
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('modal-apply'))
    const arg = onApply.mock.calls[0][0]
    expect(arg.sources).not.toContain('CA')
    expect(arg.sources).toContain('LS')
    expect(arg.sources).toContain('RS')
  })
})

describe('AdvancedSearchModal — Clear all', () => {
  it('Clear all resets all fields to defaults', () => {
    renderModal()
    fireEvent.change(screen.getByTestId('speaker-input'), {
      target: { value: 'Singh' },
    })
    fireEvent.change(screen.getByTestId('subject-input'), {
      target: { value: 'Railways' },
    })
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('modal-clear-all'))

    expect(screen.getByTestId('speaker-input')).toHaveValue('')
    expect(screen.getByTestId('subject-input')).toHaveValue('')
    expect(screen.getByTestId('source-chip-CA')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('source-chip-LS')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('source-chip-RS')).toHaveAttribute('aria-pressed', 'true')
  })

  it('Apply button is enabled after Clear all', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-chip-CA'))
    fireEvent.click(screen.getByTestId('source-chip-LS'))
    fireEvent.click(screen.getByTestId('source-chip-RS'))
    expect(screen.getByTestId('modal-apply')).toBeDisabled()
    fireEvent.click(screen.getByTestId('modal-clear-all'))
    expect(screen.getByTestId('modal-apply')).not.toBeDisabled()
  })
})

describe('AdvancedSearchModal — pre-population', () => {
  it('pre-populates from initialFilters', () => {
    renderModal({
      initialFilters: {
        ...defaultFilterState(),
        sources: ['RS'],
        speaker: 'Manmohan Singh',
        date_from: '2020-01-01',
        date_to: '2023-12-31',
      },
    })
    expect(screen.getByTestId('source-chip-CA')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('source-chip-LS')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('source-chip-RS')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('speaker-input')).toHaveValue('Manmohan Singh')
    expect(screen.getByTestId('date-from-input')).toHaveValue('2020-01-01')
    expect(screen.getByTestId('date-to-input')).toHaveValue('2023-12-31')
  })
})
