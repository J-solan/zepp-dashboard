/** Geometría de las series alineadas del Panel.
 *
 * Devuelven strings de `path` en vez de componentes: los siete carriles
 * comparten un solo SVG y un solo eje de tiempo, que es lo que permite leer
 * una columna vertical como "un día entero". Con un contenedor de gráfica por
 * métrica esa alineación no se puede garantizar.
 *
 * Todas tratan `null` como "no se midió", nunca como cero. */

type Values = readonly (number | null | undefined)[]
type X = (index: number) => number
type Y = (value: number) => number

/** Un decimal basta para un SVG y recorta el path a la mitad. */
const r = (n: number) => Math.round(n * 10) / 10

/** Línea que se PARTE en los huecos: unir los dos extremos dibujaría una
 * tendencia que nadie midió. Los huecos los cubre `gapPath`, punteados. */
export function linePath(values: Values, x: X, y: Y): string {
  let d = ''
  let open = false
  values.forEach((v, i) => {
    if (v == null) {
      open = false
      return
    }
    d += (open ? 'L' : 'M') + r(x(i)) + ' ' + r(y(v))
    open = true
  })
  return d
}

/** Los puentes sobre cada hueco, para pintarlos con otro trazo y que se lean
 * como lo que son: una interpolación, no una medida. */
export function gapPath(values: Values, x: X, y: Y): string {
  let d = ''
  let prev = -1
  values.forEach((v, i) => {
    if (v == null) return
    if (prev >= 0 && i - prev > 1) {
      d += 'M' + r(x(prev)) + ' ' + r(y(values[prev] as number)) + 'L' + r(x(i)) + ' ' + r(y(v))
    }
    prev = i
  })
  return d
}

/** Relleno bajo la línea, cerrado contra `baseY`. Un tramo cerrado por cada
 * racha de días con dato, por el mismo motivo que `linePath`. */
export function areaPath(values: Values, x: X, y: Y, baseY: number): string {
  let d = ''
  let run: string[] = []
  let first = 0

  const close = (last: number) => {
    if (run.length === 0) return
    d += 'M' + r(x(first)) + ' ' + r(baseY) + run.join('') + 'L' + r(x(last)) + ' ' + r(baseY) + 'Z'
    run = []
  }

  values.forEach((v, i) => {
    if (v == null) {
      close(i - 1)
      return
    }
    if (run.length === 0) first = i
    run.push('L' + r(x(i)) + ' ' + r(y(v)))
  })
  close(values.length - 1)
  return d
}

export interface BarOptions {
  /** Y del suelo del carril. */
  baseY: number
  /** Alto máximo de barra, en px. */
  height: number
  /** Valor que llena el carril entero; por encima se recorta. */
  max: number
  width: number
}

/** Barras como un único path.
 *
 * Con techo porque estas series tienen picos que son la excepción (una sesión
 * de vóley con carga 251 entre días de 0 a 12): escalar al máximo dejaría el
 * resto del mes en una línea plana ilegible. El pico se recorta y se rotula
 * con su valor real al lado. */
export function barsPath(values: Values, x: X, { baseY, height, max, width }: BarOptions): string {
  let d = ''
  values.forEach((v, i) => {
    if (v == null || v <= 0) return
    const h = Math.min(height, (v / max) * height)
    const left = x(i) - width / 2
    d += 'M' + r(left) + ' ' + r(baseY - h) + 'h' + r(width) + 'v' + r(h) + 'h' + r(-width) + 'Z'
  })
  return d
}
