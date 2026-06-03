import { Link, useLocation } from 'react-router-dom'
import SpeechCard from './SpeechCard.jsx'
import QACard from './QACard.jsx'

export default function ResultCard({ result }) {
  const location = useLocation()
  if (!result) return null
  const card =
    result.record_type === 'qa' || result.record_type === 'qa_exchange'
      ? <QACard result={result} />
      : <SpeechCard result={result} />

  return (
    <Link
      to={`/record/${result.id}`}
      state={{ from: 'search', resultsPath: location.pathname + location.search }}
      className="result-card-link"
    >
      {card}
    </Link>
  )
}
