/** Tu propia banda de referencia. Un valor suelto no dice nada ("readiness 92"
 * ¿es alto?); contra la distribución de tus últimos días, sí. */

export interface Band {
  min: number
  p25: number
  median: number
  p75: number
  max: number
}

/** Cuantiles por rango más cercano sobre los valores que EXISTEN.
 *
 * Sin interpolar entre vecinos a propósito: con ventanas de 30 puntos la
 * diferencia es de decimales, y el método interpolado se explica peor cuando
 * uno compara la banda con la lista de días que la produjo. */
export function quantiles(values: readonly (number | null | undefined)[]): Band | null {
  // `filter` ya copia, así que ordenar aquí no toca la serie del llamante.
  const sorted = values.filter((v): v is number => v != null).sort((a, b) => a - b)
  if (sorted.length === 0) return null
  const at = (p: number) => sorted[Math.floor((sorted.length - 1) * p)]
  return {
    min: sorted[0],
    p25: at(0.25),
    median: at(0.5),
    p75: at(0.75),
    max: sorted[sorted.length - 1],
  }
}

/** Distancia a la mediana en múltiplos del rango intercuartílico.
 *
 * En IQR y no en desviaciones típicas porque estas series traen picos sueltos
 * (una sesión de vóley entre semanas de bici) que inflan la sigma y esconden
 * justo lo que se quiere destacar. Una banda plana devuelve 0: sin dispersión
 * no hay anomalía que medir. */
export function deviation(value: number, band: Band): number {
  const iqr = band.p75 - band.p25
  return iqr === 0 ? 0 : (value - band.median) / iqr
}
