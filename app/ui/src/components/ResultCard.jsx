import { useLocation } from 'react-router-dom'
import SpeechCard from './SpeechCard.jsx'
import QACard from './QACard.jsx'
import ResultDebugPanel from './ResultDebugPanel.jsx'

export default function ResultCard({ result, debug = false }) {
  const location = useLocation()
  if (!result) return null

  const detailTo = `/record/${result.id}`
  // The results URL carries query, filters, sort and page, so it is all the
  // detail page needs for its "Back to results" link.
  const detailState = {
    from: 'search',
    resultsPath: location.pathname + location.search,
  }

  const card =
    result.record_type === 'qa' || result.record_type === 'qa_exchange'
      ? <QACard result={result} detailTo={detailTo} detailState={detailState} />
      : <SpeechCard result={result} detailTo={detailTo} detailState={detailState} />

  return (
    <div className="result-card-link">
      {card}
      {debug && <ResultDebugPanel result={result} />}
    </div>
  )
}
