/**
 * Convert an integer to its English ordinal string.
 *
 *   1 → "1st", 2 → "2nd", 3 → "3rd", 4 → "4th",
 *   11 → "11th", 12 → "12th", 13 → "13th" (teens are always "th"),
 *   21 → "21st", 22 → "22nd", 23 → "23rd".
 *
 * Returns null for non-finite / non-integer input so callers can omit display.
 */
export function toOrdinal(n) {
  if (n == null || typeof n !== 'number' || !Number.isInteger(n)) return null

  const abs = Math.abs(n)
  const lastTwo = abs % 100
  const lastOne = abs % 10

  let suffix = 'th'
  if (lastTwo < 11 || lastTwo > 13) {
    if (lastOne === 1) suffix = 'st'
    else if (lastOne === 2) suffix = 'nd'
    else if (lastOne === 3) suffix = 'rd'
  }

  return `${n}${suffix}`
}
