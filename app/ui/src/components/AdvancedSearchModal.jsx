import { useEffect, useReducer, useRef } from 'react'
import {
  ALL_SOURCES,
  ALL_PROCEEDING_TYPES,
  SOURCE_LABELS,
  PROCEEDING_TYPE_LABELS,
} from '../lib/constants.js'
import { validateFilterState, defaultFilterState } from '../lib/filterState.js'

function initLocalState(filters) {
  const f = filters || defaultFilterState()
  return {
    sources: Array.isArray(f.sources) ? [...f.sources] : [...ALL_SOURCES],
    proceeding_types: Array.isArray(f.proceeding_types)
      ? [...f.proceeding_types]
      : [...ALL_PROCEEDING_TYPES],
    date_from: f.date_from || '',
    date_to: f.date_to || '',
    speaker: f.speaker || '',
    session: f.session || '',
  }
}

function localReducer(state, action) {
  switch (action.type) {
    case 'TOGGLE_SOURCE': {
      const { source } = action
      const has = state.sources.includes(source)
      const next = has
        ? state.sources.filter((s) => s !== source)
        : [...state.sources, source]
      return { ...state, sources: next }
    }
    case 'TOGGLE_TYPE': {
      const { pt } = action
      const has = state.proceeding_types.includes(pt)
      const next = has
        ? state.proceeding_types.filter((t) => t !== pt)
        : [...state.proceeding_types, pt]
      return { ...state, proceeding_types: next }
    }
    case 'SET_DATE_FROM':
      return { ...state, date_from: action.value }
    case 'SET_DATE_TO':
      return { ...state, date_to: action.value }
    case 'SET_SPEAKER':
      return { ...state, speaker: action.value }
    case 'SET_SESSION':
      return { ...state, session: action.value }
    case 'RESET':
      return initLocalState(defaultFilterState())
    case 'INIT':
      return initLocalState(action.filters)
    default:
      return state
  }
}

export default function AdvancedSearchModal({ isOpen, initialFilters, onApply, onClose }) {
  const [state, dispatch] = useReducer(
    localReducer,
    null,
    () => initLocalState(initialFilters)
  )
  const overlayRef = useRef(null)

  useEffect(() => {
    if (isOpen) {
      dispatch({ type: 'INIT', filters: initialFilters })
    }
    // Re-init only when modal opens; intentionally omit initialFilters
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen])

  useEffect(() => {
    if (!isOpen) return undefined
    const handler = (e) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const caOnly = state.sources.length === 1 && state.sources[0] === 'CA'

  const filterStateForValidation = {
    sources: state.sources,
    proceeding_types: state.proceeding_types,
    date_from: state.date_from || null,
    date_to: state.date_to || null,
    speaker: state.speaker || null,
    session: state.session || null,
  }
  const errors = validateFilterState(filterStateForValidation)
  const hasErrors = Object.keys(errors).length > 0

  const handleOverlayClick = (e) => {
    if (e.target === overlayRef.current) onClose()
  }

  const handleApply = () => {
    if (hasErrors) return
    onApply({
      sources: [...state.sources],
      proceeding_types: [...state.proceeding_types],
      date_from: state.date_from || null,
      date_to: state.date_to || null,
      speaker: state.speaker.trim() || null,
      session: state.session.trim() || null,
    })
  }

  return (
    <div
      className="modal-overlay"
      ref={overlayRef}
      onClick={handleOverlayClick}
      role="dialog"
      aria-modal="true"
      aria-label="Advanced Search"
      data-testid="advanced-search-modal"
    >
      <div className="modal-panel">
        <div className="modal-header">
          <h2 className="modal-title">Advanced Search</h2>
          <button
            type="button"
            className="modal-close"
            aria-label="Close Advanced Search"
            onClick={onClose}
            data-testid="modal-close"
          >
            ×
          </button>
        </div>

        <div className="modal-body">
          {/* 1. Legislative Body */}
          <div className="filter-field">
            <div className="filter-label">Legislative Body</div>
            <div className="filter-checkboxes" role="group" aria-label="Legislative Body">
              {ALL_SOURCES.map((src) => (
                <label key={src} className="filter-checkbox-row">
                  <input
                    type="checkbox"
                    checked={state.sources.includes(src)}
                    onChange={() => dispatch({ type: 'TOGGLE_SOURCE', source: src })}
                    data-testid={`source-checkbox-${src}`}
                  />
                  {SOURCE_LABELS[src]}
                </label>
              ))}
            </div>
            {errors.sources && (
              <p
                className="filter-validation"
                role="alert"
                data-testid="source-validation"
              >
                {errors.sources}
              </p>
            )}
          </div>

          {/* 2. Date Range */}
          <div className="filter-field">
            <div className="filter-label">Date Range</div>
            <div className="filter-date-row">
              <div className="filter-date-col">
                <div className="filter-date-sublabel">From</div>
                <input
                  type="date"
                  className="filter-date-input"
                  value={state.date_from}
                  onChange={(e) =>
                    dispatch({ type: 'SET_DATE_FROM', value: e.target.value })
                  }
                  data-testid="date-from-input"
                />
              </div>
              <div className="filter-date-col">
                <div className="filter-date-sublabel">To</div>
                <input
                  type="date"
                  className="filter-date-input"
                  value={state.date_to}
                  onChange={(e) =>
                    dispatch({ type: 'SET_DATE_TO', value: e.target.value })
                  }
                  data-testid="date-to-input"
                />
              </div>
            </div>
            {errors.date_range && (
              <p
                className="filter-validation"
                role="alert"
                data-testid="date-validation"
              >
                {errors.date_range}
              </p>
            )}
          </div>

          {/* 3. Speaker */}
          <div className="filter-field">
            <div className="filter-label">Speaker</div>
            <input
              type="text"
              className="filter-text-input"
              placeholder="e.g. Ambedkar"
              value={state.speaker}
              onChange={(e) =>
                dispatch({ type: 'SET_SPEAKER', value: e.target.value })
              }
              data-testid="speaker-input"
            />
            <p className="filter-helper">
              Use last name only for reliable results (names are canonicalized in
              the index).
            </p>
          </div>

          {/* 4. Session */}
          <div className="filter-field">
            <div className="filter-label">Session</div>
            <input
              type="text"
              className="filter-text-input"
              placeholder="e.g. Budget Session 2023"
              value={state.session}
              onChange={(e) =>
                dispatch({ type: 'SET_SESSION', value: e.target.value })
              }
              data-testid="session-input"
            />
            <p className="filter-helper">
              Constituent Assembly records have no session name and will not match
              a session filter.
            </p>
          </div>

          {/* 5. Proceeding Type */}
          <div className="filter-field">
            <div className="filter-label">Proceeding Type</div>
            <div
              className="filter-checkboxes filter-checkboxes-grid"
              role="group"
              aria-label="Proceeding Type"
            >
              {ALL_PROCEEDING_TYPES.map((pt) => {
                const disabled = caOnly && pt !== 'debate'
                return (
                  <label
                    key={pt}
                    className={`filter-checkbox-row${disabled ? ' filter-checkbox-disabled' : ''}`}
                  >
                    <input
                      type="checkbox"
                      checked={state.proceeding_types.includes(pt)}
                      disabled={disabled}
                      onChange={() =>
                        !disabled && dispatch({ type: 'TOGGLE_TYPE', pt })
                      }
                      data-testid={`type-checkbox-${pt}`}
                    />
                    {PROCEEDING_TYPE_LABELS[pt]}
                  </label>
                )
              })}
            </div>
            {errors.proceeding_types && (
              <p
                className="filter-validation"
                role="alert"
                data-testid="type-validation"
              >
                {errors.proceeding_types}
              </p>
            )}
          </div>
        </div>

        <div className="modal-footer">
          <button
            type="button"
            className="modal-clear-all"
            onClick={() => dispatch({ type: 'RESET' })}
            data-testid="modal-clear-all"
          >
            Clear all
          </button>
          <button
            type="button"
            className="modal-apply-btn"
            onClick={handleApply}
            disabled={hasErrors}
            aria-disabled={hasErrors}
            data-testid="modal-apply"
          >
            Apply
          </button>
        </div>
      </div>
    </div>
  )
}
