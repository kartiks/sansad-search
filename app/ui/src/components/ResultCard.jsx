import { useLocation } from 'react-router-dom'
import SpeechCard from './SpeechCard.jsx'
import QACard from './QACard.jsx'
import ResultDebugPanel from './ResultDebugPanel.jsx'

export default function ResultCard({ result, filters, debug = false }) {
  const location = useLocation()
  if (!result) return null

  const detailTo = `/record/${result.id}`
  const detailState = {
    from: 'search',
    resultsPath: location.pathname + location.search,
    filters,
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
