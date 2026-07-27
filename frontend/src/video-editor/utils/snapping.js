export function snapValue(value, candidates = [], threshold = 0.25) {
  let result = Number(value || 0)
  let bestDistance = Infinity

  candidates.forEach((candidate) => {
    const distance = Math.abs(Number(candidate || 0) - result)
    if (distance <= threshold && distance < bestDistance) {
      result = Number(candidate || 0)
      bestDistance = distance
    }
  })

  return result
}
