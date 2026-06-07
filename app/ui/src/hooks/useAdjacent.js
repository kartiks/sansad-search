import { useCallback, useEffect, useRef, useState } from 'react'

export const ADJACENT_ENDPOINT = (id, direction, fromSeq, limit = 5) =>
  `/api/record/${encodeURIComponent(id)}/adjacent` +
  `?direction=${direction}&from_seq=${fromSeq}&limit=${limit}`

export async function fetchAdjacent(id, direction, fromSeq, signal, limit = 5) {
  let response
  try {
    response = await fetch(ADJACENT_ENDPOINT(id, direction, fromSeq, limit), { signal })
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
    const e = new Error(
      (payload && (payload.message || payload.error)) || `http_${response.status}`
    )
    e.status = response.status
    throw e
  }

  return payload
}

/**
 * F09 inline adjacent loading.
 *
 * Manages "Load 5 previous" / "Load 5 next" batches around a focal record,
 * accumulating prepended (prev) and appended (next) records inline without
 * navigation. Tracks per-direction enabled state (initial has_prev/has_next,
 * then has_more after each batch), in-flight state, and error state.
 *
 * @param focalId  the focal record's id
 * @param focal    the loaded focal record (or null before load); reads
 *                 sequence_within_sitting, has_prev, has_next
 */
export function useAdjacent(focalId, focal) {
  const [prevRecords, setPrevRecords] = useState([])
  const [nextRecords, setNextRecords] = useState([])
  const [canLoadPrev, setCanLoadPrev] = useState(false)
  const [canLoadNext, setCanLoadNext] = useState(false)
  const [loadingPrev, setLoadingPrev] = useState(false)
  const [loadingNext, setLoadingNext] = useState(false)
  const [errorPrev, setErrorPrev] = useState(false)
  const [errorNext, setErrorNext] = useState(false)

  // Exclusive sequence boundary for the next batch in each direction.
  const prevSeqRef = useRef(null)
  const nextSeqRef = useRef(null)

  const focalSeq = focal?.sequence_within_sitting
  const hasPrev = focal?.has_prev
  const hasNext = focal?.has_next

  // Reset all adjacent state when the focal record (or its sitting position)
  // changes. Initial enabled state comes from has_prev / has_next.
  useEffect(() => {
    setPrevRecords([])
    setNextRecords([])
    setErrorPrev(false)
    setErrorNext(false)
    setLoadingPrev(false)
    setLoadingNext(false)
    setCanLoadPrev(!!hasPrev)
    setCanLoadNext(!!hasNext)
    prevSeqRef.current = focalSeq == null ? null : focalSeq
    nextSeqRef.current = focalSeq == null ? null : focalSeq
  }, [focalId, focalSeq, hasPrev, hasNext])

  const loadPrev = useCallback(async () => {
    if (loadingPrev || prevSeqRef.current == null) return
    setLoadingPrev(true)
    setErrorPrev(false)
    try {
      const data = await fetchAdjacent(focalId, 'prev', prevSeqRef.current)
      const records = data.records || []
      if (records.length > 0) {
        // Ascending order → first element is the lowest-loaded sequence.
        prevSeqRef.current = records[0].sequence_within_sitting
        setPrevRecords((cur) => [...records, ...cur])
      }
      setCanLoadPrev(!!data.has_more)
    } catch (err) {
      if (err && err.name === 'AbortError') return
      // Error shown; control stays enabled (pre-click state) for retry.
      setErrorPrev(true)
    } finally {
      setLoadingPrev(false)
    }
  }, [focalId, loadingPrev])

  const loadNext = useCallback(async () => {
    if (loadingNext || nextSeqRef.current == null) return
    setLoadingNext(true)
    setErrorNext(false)
    try {
      const data = await fetchAdjacent(focalId, 'next', nextSeqRef.current)
      const records = data.records || []
      if (records.length > 0) {
        // Ascending order → last element is the highest-loaded sequence.
        nextSeqRef.current = records[records.length - 1].sequence_within_sitting
        setNextRecords((cur) => [...cur, ...records])
      }
      setCanLoadNext(!!data.has_more)
    } catch (err) {
      if (err && err.name === 'AbortError') return
      setErrorNext(true)
    } finally {
      setLoadingNext(false)
    }
  }, [focalId, loadingNext])

  return {
    prevRecords,
    nextRecords,
    canLoadPrev,
    canLoadNext,
    loadingPrev,
    loadingNext,
    errorPrev,
    errorNext,
    loadPrev,
    loadNext,
  }
}
