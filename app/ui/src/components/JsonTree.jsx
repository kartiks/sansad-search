import { useState } from 'react'

function JsonNode({ keyName, value, depth }) {
  const type =
    value === null ? 'null'
    : Array.isArray(value) ? 'array'
    : typeof value

  const isComplex = type === 'object' || type === 'array'
  // Root-level complex nodes start expanded; nested ones start collapsed.
  const [expanded, setExpanded] = useState(depth === 0 && isComplex)

  if (isComplex) {
    const entries =
      type === 'array'
        ? value.map((v, i) => [i, v])
        : Object.entries(value)
    const isEmpty = entries.length === 0
    const openBrace = type === 'array' ? '[' : '{'
    const closeBrace = type === 'array' ? ']' : '}'

    return (
      <span className="json-node">
        {keyName !== undefined && (
          <span className="json-key">"{String(keyName)}": </span>
        )}
        <button
          type="button"
          className="json-toggle"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
        >
          {expanded ? '▼' : '▶'}
        </button>
        {expanded ? (
          <>
            {' '}{openBrace}
            {!isEmpty && (
              <div className="json-children">
                {entries.map(([k, v]) => (
                  <div key={String(k)} className="json-line">
                    <JsonNode keyName={k} value={v} depth={depth + 1} />
                  </div>
                ))}
              </div>
            )}
            {closeBrace}
          </>
        ) : (
          <> {' '}<span className="json-collapsed">{openBrace}{isEmpty ? '' : '…'}{closeBrace}</span></>
        )}
      </span>
    )
  }

  let colorClass = 'json-null'
  let display = 'null'
  if (type === 'string') {
    colorClass = 'json-string'
    display = `"${value}"`
  } else if (type === 'number') {
    colorClass = 'json-number'
    display = String(value)
  } else if (type === 'boolean') {
    colorClass = 'json-boolean'
    display = String(value)
  }

  return (
    <span className="json-node">
      {keyName !== undefined && (
        <span className="json-key">"{String(keyName)}": </span>
      )}
      <span className={colorClass}>{display}</span>
    </span>
  )
}

export default function JsonTree({ data }) {
  return (
    <div className="json-tree">
      <JsonNode value={data} depth={0} />
    </div>
  )
}
