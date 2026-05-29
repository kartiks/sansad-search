import SpeechCard from './SpeechCard.jsx'
import QACard from './QACard.jsx'

export default function ResultCard({ result }) {
  if (!result) return null
  if (result.record_type === 'qa' || result.record_type === 'qa_exchange') {
    return <QACard result={result} />
  }
  return <SpeechCard result={result} />
}
