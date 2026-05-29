import { useEffect } from 'react'

export const TOAST_DEFAULT_MS = 3000

export default function Toast({ message, onDismiss, durationMs = TOAST_DEFAULT_MS }) {
  useEffect(() => {
    if (!message) return undefined
    const id = setTimeout(() => {
      if (typeof onDismiss === 'function') onDismiss()
    }, durationMs)
    return () => clearTimeout(id)
  }, [message, durationMs, onDismiss])

  if (!message) return null

  return (
    <div className="toast" role="status" aria-live="polite">
      {message}
    </div>
  )
}
