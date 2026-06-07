import { useCallback, useState } from 'react'

export const DEBUG_PROCESSED_ENDPOINT = (id) =>
  `/api/debug/processed/${encodeURIComponent(id)}`

export const DEBUG_RAW_ENDPOINT = (id) =>
  `/api/debug/raw/${encodeURIComponent(id)}`

async function _fetchDebugSection(url) {
  let response
  try {
    response = await fetch(url)
  } catch {
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

/**
 * F10 lazy-fetch hook for per-result debug sections.
 *
 * Each section (processed record / raw document) fetches independently.
 * After the first successful or failed fetch, subsequent calls are no-ops
 * (the result is cached in component state). Sections are independent:
 * fetching one does not trigger the other.
 */
export function useDebugDetail(id) {
  const [processedData, setProcessedData] = useState(null)
  const [processedError, setProcessedError] = useState(null)
  const [processedLoading, setProcessedLoading] = useState(false)
  const [processedFetched, setProcessedFetched] = useState(false)

  const [rawData, setRawData] = useState(null)
  const [rawError, setRawError] = useState(null)
  const [rawLoading, setRawLoading] = useState(false)
  const [rawFetched, setRawFetched] = useState(false)

  const fetchProcessed = useCallback(async () => {
    if (processedFetched || processedLoading) return
    setProcessedLoading(true)
    setProcessedError(null)
    try {
      const data = await _fetchDebugSection(DEBUG_PROCESSED_ENDPOINT(id))
      setProcessedData(data)
    } catch (err) {
      setProcessedError(err)
    } finally {
      setProcessedLoading(false)
      setProcessedFetched(true)
    }
  }, [id, processedFetched, processedLoading])

  const fetchRaw = useCallback(async () => {
    if (rawFetched || rawLoading) return
    setRawLoading(true)
    setRawError(null)
    try {
      const data = await _fetchDebugSection(DEBUG_RAW_ENDPOINT(id))
      setRawData(data)
    } catch (err) {
      setRawError(err)
    } finally {
      setRawLoading(false)
      setRawFetched(true)
    }
  }, [id, rawFetched, rawLoading])

  return {
    processedData,
    processedError,
    processedLoading,
    processedFetched,
    fetchProcessed,
    rawData,
    rawError,
    rawLoading,
    rawFetched,
    fetchRaw,
  }
}
