import { useEffect, useState } from 'react'

export const RECORD_ENDPOINT = (id) => `/api/record/${encodeURIComponent(id)}`

export async function fetchRecord(id, signal) {
  let response
  try {
    response = await fetch(RECORD_ENDPOINT(id), { signal })
  } catch (err) {
    if (err && err.name === 'AbortError') throw err
    throw new Error('network_error')
  }

  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (response.status === 404) {
    const e = new Error('not_found')
    e.status = 404
    e.payload = payload
    throw e
  }

  if (!response.ok) {
    const e = new Error(
      (payload && (payload.message || payload.error)) || `http_${response.status}`
    )
    e.status = response.status
    e.payload = payload
    throw e
  }

  return payload
}

export function useRecord(id) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [notFound, setNotFound] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    if (!id) return

    const controller = new AbortController()
    setLoading(true)
    setError(null)
    setNotFound(false)
    setData(null)

    fetchRecord(id, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return
        setData(result)
        setLoading(false)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        if (err && err.name === 'AbortError') return
        if (err.status === 404) {
          setNotFound(true)
        } else {
          setError(err)
        }
        setLoading(false)
      })

    return () => controller.abort()
  }, [id, reloadToken])

  const retry = () => setReloadToken((t) => t + 1)

  return { data, error, loading, notFound, retry }
}
