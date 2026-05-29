import { useEffect, useRef, useState } from 'react'
import { toApiFilters } from '../lib/filterState.js'

export const SEARCH_ENDPOINT = '/api/search'

export function buildSearchRequestBody({ query, filters, sort, page }) {
  const body = {
    query: String(query ?? ''),
    sort: sort || 'relevance',
    page: Math.max(1, Number(page) || 1),
  }
  const apiFilters = toApiFilters(filters)
  if (apiFilters) body.filters = apiFilters
  return body
}

export async function postSearch({ query, filters, sort, page, signal }) {
  const body = buildSearchRequestBody({ query, filters, sort, page })

  let response
  try {
    response = await fetch(SEARCH_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
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

  if (!response.ok) {
    const error = new Error(
      (payload && (payload.message || payload.error)) || `http_${response.status}`
    )
    error.status = response.status
    error.payload = payload
    throw error
  }

  return payload
}

export function useSearch({ query, filters, sort, page, enabled = true }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const lastKey = useRef(null)

  useEffect(() => {
    if (!enabled) {
      setData(null)
      setError(null)
      setLoading(false)
      return undefined
    }

    const controller = new AbortController()
    const key = JSON.stringify(
      buildSearchRequestBody({ query, filters, sort, page })
    )
    lastKey.current = key
    setLoading(true)
    setError(null)

    postSearch({ query, filters, sort, page, signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return
        if (lastKey.current !== key) return
        setData(result)
        setLoading(false)
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        if (err && err.name === 'AbortError') return
        if (lastKey.current !== key) return
        setError(err)
        setData(null)
        setLoading(false)
      })

    return () => controller.abort()
  }, [
    enabled,
    query,
    sort,
    page,
    JSON.stringify(toApiFilters(filters)),
    reloadToken,
  ])

  const retry = () => setReloadToken((t) => t + 1)

  return { data, error, loading, retry }
}
