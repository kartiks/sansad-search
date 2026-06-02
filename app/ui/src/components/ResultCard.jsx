import { Link } from 'react-router-dom'
import SpeechCard from './SpeechCard.jsx'
import QACard from './QACard.jsx'

export default function ResultCard({ result }) {
  if (!result) return null
  const card =
    result.record_type === 'qa' || result.record_type === 'qa_exchange'
      ? <QACard result={result} />
      : <SpeechCard result={result} />

  return (
    <Link
      to={`/record/${result.id}`}
      state={{ from: 'search' }}
      className="result-card-link"
    >
      {card}
    </Link>
  )
}
