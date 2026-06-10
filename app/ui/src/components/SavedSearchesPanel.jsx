import { useEffect, useRef, useState } from 'react'
import {
  ALL_SOURCES,
  ALL_PROCEEDING_TYPES,
  SOURCE_LABELS,
  PROCEEDING_TYPE_LABELS,
} from '../lib/constants.js'
import { isDefaultFilterState } from '../lib/filterState.js'

const NAME_MAX_LEN = 60
const SAVE_LIMIT_MSG = 'Saved searches full — delete one to save'

function arraysMatch(a, b) {
  if (!Array.isArray(a) || !Array.isArray(b)) return false
  if (a.length !== b.length) return false
  const sa = [...a].sort()
  const sb = [...b].sort()
  return sa.every((v, i) => v === sb[i])
}

function buildFilterSummary(filters) {
  if (!filters || isDefaultFilterState(filters)) return 'No filters'
  const parts = []

  if (Array.isArray(filters.sources) && !arraysMatch(filters.sources, ALL_SOURCES)) {
    parts.push(filters.sources.map((s) => SOURCE_LABELS[s] || s).join(', '))
  }

  if (filters.date_from || filters.date_to) {
    if (filters.date_from && filters.date_to) {
      const fy = String(filters.date_from).slice(0, 4)
      const ty = String(filters.date_to).slice(0, 4)
      parts.push(`${fy}–${ty}`)
    } else if (filters.date_from) {
      parts.push(`From ${String(filters.date_from).slice(0, 4)}`)
    } else {
      parts.push(`To ${String(filters.date_to).slice(0, 4)}`)
    }
  }

  if (filters.speaker && filters.speaker.trim()) {
    parts.push(`Speaker: ${filters.speaker.trim()}`)
  }
  if (filters.session && filters.session.trim()) {
    parts.push(filters.session.trim())
  }
  if (filters.subject && filters.subject.trim()) {
    parts.push(`Subject: ${filters.subject.trim()}`)
  }

  if (
    Array.isArray(filters.proceeding_types) &&
    !arraysMatch(filters.proceeding_types, ALL_PROCEEDING_TYPES)
  ) {
    parts.push(
      filters.proceeding_types.map((pt) => PROCEEDING_TYPE_LABELS[pt] || pt).join(', ')
    )
  }

  return parts.length > 0 ? parts.join(' · ') : 'No filters'
}

export default function SavedSearchesPanel({
  entries,
  atLimit,
  visible,
  showSaveButton,
  onRunSearch,
  onSave,
  onDelete,
  onRename,
  onToast,
  onDismiss,
}) {
  const containerRef = useRef(null)
  const [renamingId, setRenamingId] = useState(null)
  const [renameValue, setRenameValue] = useState('')
  const [savedFlash, setSavedFlash] = useState(false)

  useEffect(() => {
    if (!visible) {
      setRenamingId(null)
      return undefined
    }

    function handleMouseDown(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        onDismiss()
      }
    }
    function handleKeyDown(e) {
      if (e.key === 'Escape') onDismiss()
    }

    document.addEventListener('mousedown', handleMouseDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleMouseDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [visible, onDismiss])

  if (!visible) return null

  const handleDelete = (id) => {
    onDelete(id)
    if (typeof onToast === 'function') onToast('Search removed')
  }

  const handleSave = () => {
    if (atLimit) return
    onSave()
    setSavedFlash(true)
    setTimeout(() => setSavedFlash(false), 1500)
    if (typeof onToast === 'function') onToast('Search saved')
  }

  const handleRenameStart = (entry) => {
    setRenamingId(entry.id)
    setRenameValue(entry.name)
  }

  const handleRenameConfirm = () => {
    if (renamingId) onRename(renamingId, renameValue)
    setRenamingId(null)
  }

  const handleRenameCancel = () => {
    setRenamingId(null)
  }

  const handleRenameKeyDown = (e) => {
    if (e.key === 'Enter') handleRenameConfirm()
    if (e.key === 'Escape') handleRenameCancel()
  }

  return (
    <div
      className="saved-searches-panel"
      ref={containerRef}
      data-testid="saved-searches-panel"
    >
      <div className="saved-searches-header">Saved searches</div>

      <div className="saved-searches-list-wrap">
        {entries.length === 0 ? (
          <div
            className="saved-searches-empty"
            data-testid="saved-searches-empty"
          >
            No saved searches yet.
          </div>
        ) : (
          <ul className="saved-searches-list">
            {entries.map((entry) => (
              <li
                key={entry.id}
                className="saved-searches-item"
                data-testid="saved-search-item"
              >
                <div className="saved-searches-item-content">
                  {renamingId === entry.id ? (
                    <div className="saved-searches-rename-row">
                      <input
                        type="text"
                        className="saved-searches-rename-input"
                        value={renameValue}
                        maxLength={NAME_MAX_LEN}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={handleRenameKeyDown}
                        autoFocus
                        data-testid="saved-search-rename-input"
                      />
                      <button
                        type="button"
                        className="saved-searches-rename-confirm"
                        aria-label="Confirm rename"
                        onClick={handleRenameConfirm}
                        data-testid="saved-search-rename-confirm"
                      >
                        ✓
                      </button>
                      <button
                        type="button"
                        className="saved-searches-rename-cancel"
                        aria-label="Cancel rename"
                        onClick={handleRenameCancel}
                        data-testid="saved-search-rename-cancel"
                      >
                        ×
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="saved-searches-item-btn"
                      onClick={() => onRunSearch(entry)}
                      data-testid="saved-search-run-btn"
                    >
                      <span className="saved-searches-name">{entry.name}</span>
                      <span className="saved-searches-summary">
                        {buildFilterSummary(entry.filters)}
                      </span>
                    </button>
                  )}
                </div>
                <div className="saved-searches-item-actions">
                  <button
                    type="button"
                    className="saved-searches-action-btn"
                    aria-label={`Rename ${entry.name}`}
                    onClick={() => handleRenameStart(entry)}
                    data-testid="saved-search-rename-btn"
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <path
                        d="M11.5 2.5l2 2L5 13H3v-2L11.5 2.5z"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                  <button
                    type="button"
                    className="saved-searches-action-btn saved-searches-delete-btn"
                    aria-label={`Delete ${entry.name}`}
                    onClick={() => handleDelete(entry.id)}
                    data-testid="saved-search-delete-btn"
                  >
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <path
                        d="M3 4h10M6 4V3h4v1M5 4v9h6V4H5z"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {showSaveButton && (
        <div className="saved-searches-footer">
          <button
            type="button"
            className="saved-searches-save-btn"
            onClick={handleSave}
            disabled={atLimit}
            style={{ opacity: atLimit ? 0.4 : 1, cursor: atLimit ? 'default' : 'pointer' }}
            data-testid="saved-search-save-btn"
          >
            {savedFlash ? 'Saved ✓' : 'Save current search'}
          </button>
          {atLimit && (
            <p
              className="saved-searches-limit-msg"
              data-testid="saved-search-limit-msg"
            >
              {SAVE_LIMIT_MSG}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
