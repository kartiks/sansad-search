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

  it('renders all 5 filter sections', () => {
    renderModal()
    expect(screen.getByText('Legislative Body')).toBeInTheDocument()
    expect(screen.getByText('Date Range')).toBeInTheDocument()
    expect(screen.getByText('Speaker')).toBeInTheDocument()
    expect(screen.getByText('Session')).toBeInTheDocument()
    expect(screen.getByText('Proceeding Type')).toBeInTheDocument()
  })

  it('renders all 3 source checkboxes checked by default', () => {
    renderModal()
<<<<<<< HEAD
    const ca = screen.getByTestId('source-checkbox-CA')
    const ls = screen.getByTestId('source-checkbox-LS')
    const rs = screen.getByTestId('source-checkbox-RS')
    expect(ca).toBeChecked()
    expect(ls).toBeChecked()
    expect(rs).toBeChecked()
=======
    expect(screen.getByTestId('source-checkbox-CA')).toBeChecked()
    expect(screen.getByTestId('source-checkbox-LS')).toBeChecked()
    expect(screen.getByTestId('source-checkbox-RS')).toBeChecked()
>>>>>>> 286b750 (Checkpointing Phase 7 build.)
  })

  it('renders all proceeding type checkboxes checked by default', () => {
    renderModal()
    ALL_PROCEEDING_TYPES.forEach((pt) => {
      expect(screen.getByTestId(`type-checkbox-${pt}`)).toBeChecked()
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

describe('AdvancedSearchModal — source checkboxes', () => {
  it('unchecking a source removes it', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    expect(screen.getByTestId('source-checkbox-CA')).not.toBeChecked()
    expect(screen.getByTestId('source-checkbox-LS')).toBeChecked()
  })

  it('unchecking all sources shows validation message', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
    fireEvent.click(screen.getByTestId('source-checkbox-RS'))
    expect(screen.getByTestId('source-validation')).toBeInTheDocument()
    expect(screen.getByTestId('source-validation').textContent).toContain(
      'Select at least one source'
    )
  })

  it('Apply button is disabled when all sources unchecked', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
    fireEvent.click(screen.getByTestId('source-checkbox-RS'))
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

describe('AdvancedSearchModal — proceeding types', () => {
  it('unchecking all types shows validation message and disables Apply', () => {
    renderModal()
    ALL_PROCEEDING_TYPES.forEach((pt) => {
      fireEvent.click(screen.getByTestId(`type-checkbox-${pt}`))
    })
    expect(screen.getByTestId('type-validation')).toBeInTheDocument()
    expect(screen.getByTestId('modal-apply')).toBeDisabled()
  })

  it('CA-only selected disables all non-Debate proceeding type checkboxes', () => {
    renderModal()
<<<<<<< HEAD
    // Uncheck LS and RS so only CA is selected
=======
>>>>>>> 286b750 (Checkpointing Phase 7 build.)
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
    fireEvent.click(screen.getByTestId('source-checkbox-RS'))

    ALL_PROCEEDING_TYPES.forEach((pt) => {
      const checkbox = screen.getByTestId(`type-checkbox-${pt}`)
      if (pt === 'debate') {
        expect(checkbox).not.toBeDisabled()
      } else {
        expect(checkbox).toBeDisabled()
      }
    })
  })

  it('adding LS back re-enables all proceeding type checkboxes', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
    fireEvent.click(screen.getByTestId('source-checkbox-RS'))
<<<<<<< HEAD
    // Now only CA selected
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
    // Now CA+LS selected — all types should be enabled
=======
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
>>>>>>> 286b750 (Checkpointing Phase 7 build.)
    ALL_PROCEEDING_TYPES.forEach((pt) => {
      expect(screen.getByTestId(`type-checkbox-${pt}`)).not.toBeDisabled()
    })
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
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
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
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('modal-clear-all'))

    expect(screen.getByTestId('speaker-input')).toHaveValue('')
    expect(screen.getByTestId('source-checkbox-CA')).toBeChecked()
    expect(screen.getByTestId('source-checkbox-LS')).toBeChecked()
    expect(screen.getByTestId('source-checkbox-RS')).toBeChecked()
  })

  it('Apply button is enabled after Clear all', () => {
    renderModal()
    fireEvent.click(screen.getByTestId('source-checkbox-CA'))
    fireEvent.click(screen.getByTestId('source-checkbox-LS'))
    fireEvent.click(screen.getByTestId('source-checkbox-RS'))
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
    expect(screen.getByTestId('source-checkbox-CA')).not.toBeChecked()
    expect(screen.getByTestId('source-checkbox-LS')).not.toBeChecked()
    expect(screen.getByTestId('source-checkbox-RS')).toBeChecked()
    expect(screen.getByTestId('speaker-input')).toHaveValue('Manmohan Singh')
    expect(screen.getByTestId('date-from-input')).toHaveValue('2020-01-01')
    expect(screen.getByTestId('date-to-input')).toHaveValue('2023-12-31')
  })
})
