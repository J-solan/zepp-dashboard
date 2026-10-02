/** Correlación de Pearson entre dos columnas de días.
 *
 * Devuelve `null` en vez de un número cuando la respuesta no significaría
 * nada: menos de tres días cruzados, o una de las dos series sin variación
 * (correlacionar con una constante no está definido). Es lo que permite que la
 * interfaz calle en vez de enseñar un "0,00" con pinta de hallazgo.
 *
 * Es correlación, no causa: dos series pueden moverse juntas por un tercero
 * que no está en la tabla. */
export function pearson(
  xs: readonly (number | null | undefined)[],
  ys: readonly (number | null | undefined)[],
): number | null {
  const pairs: [number, number][] = []
  for (let i = 0; i < Math.min(xs.length, ys.length); i++) {
    const a = xs[i]
    const b = ys[i]
    if (a != null && b != null) pairs.push([a, b])
  }
  if (pairs.length < 3) return null

  const n = pairs.length
  const meanA = pairs.reduce((sum, [a]) => sum + a, 0) / n
  const meanB = pairs.reduce((sum, [, b]) => sum + b, 0) / n

  let cov = 0
  let varA = 0
  let varB = 0
  for (const [a, b] of pairs) {
    cov += (a - meanA) * (b - meanB)
    varA += (a - meanA) ** 2
    varB += (b - meanB) ** 2
  }
  if (varA === 0 || varB === 0) return null
  return cov / Math.sqrt(varA * varB)
}
