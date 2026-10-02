import { useMemo } from 'react'
import { pearson } from '../lib/stats'
import { formatDuration } from '../lib/format'
import { METRIC } from '../lib/palette'
import { STAGE_COLORS, mainSessionPerDay } from '../lib/sleep'
import type { DailyMetrics, SleepSession } from '../lib/types'

const W = 300
const H = 104

/** Cómo de fuerte es una correlación, dicho en castellano y sin adornarla. */
function strength(r: number): string {
  const abs = Math.abs(r)
  if (abs < 0.2) return 'prácticamente ninguna relación'
  if (abs < 0.4) return 'una relación floja'
  if (abs < 0.6) return 'una relación moderada'
  return 'una relación fuerte'
}

const fmtR = (r: number) => r.toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

interface ScatterProps {
  title: string
  xs: (number | null)[]
  ys: (number | null)[]
  color: string
  xLabel: (v: number) => string
}

function Scatter({ title, xs, ys, color, xLabel }: ScatterProps) {
  const pairs = xs.flatMap((x, i) => (x != null && ys[i] != null ? [[x, ys[i]!] as const] : []))
  const r = pearson(xs, ys)

  if (pairs.length < 3) {
    return (
      <div className="border border-hairline bg-surface p-3">
        <p className="text-label uppercase text-ink-muted">{title}</p>
        <p className="mt-2 text-xs text-ink-secondary">Hacen falta más días cruzados para decir nada.</p>
      </div>
    )
  }

  const xsOnly = pairs.map(([x]) => x)
  const ysOnly = pairs.map(([, y]) => y)
  const [x0, x1] = [Math.min(...xsOnly), Math.max(...xsOnly)]
  const [y0, y1] = [Math.min(...ysOnly), Math.max(...ysOnly)]
  const px = (v: number) => ((v - x0) / (x1 - x0 || 1)) * (W - 12) + 6
  const py = (v: number) => H - 8 - ((v - y0) / (y1 - y0 || 1)) * (H - 16)

  return (
    <div className="border border-hairline bg-surface p-3">
      <p className="text-label uppercase text-ink-muted">{title}</p>
      <p className="mb-2 mt-0.5 text-xs">
        {r != null ? (
          <>
            <span className="font-mono">r = {fmtR(r)}</span>
            <span className="text-ink-secondary"> · {strength(r)} en {pairs.length} noches</span>
          </>
        ) : (
          <span className="text-ink-secondary">Sin variación suficiente para correlacionar.</span>
        )}
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="presentation">
        <rect x="0" y="0" width={W} height={H} fill="var(--color-page)" />
        {pairs.map(([x, y], i) => (
          <circle key={i} cx={px(x)} cy={py(y)} r="2.6" fill={color} opacity="0.7" />
        ))}
      </svg>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-ink-muted">
        <span>{xLabel(x0)}</span>
        <span>{xLabel(x1)} · eje Y readiness</span>
      </div>
    </div>
  )
}

interface CrossesProps {
  daily: DailyMetrics[]
  sessions: SleepSession[]
}

/** Los cruces que ninguna app oficial enseña: dos series propias, una contra
 * otra, con su correlación calculada sobre los días en los que existen las dos.
 *
 * Correlación, no causa: se dice el número y se deja que el usuario mire la
 * nube, que es justo lo que un titular ("¡duerme más!") escondería. */
export function Crosses({ daily, sessions }: CrossesProps) {
  const { minutes, scores, readiness, nights } = useMemo(() => {
    const byDay = new Map(daily.map((d) => [d.day, d]))
    const list = mainSessionPerDay(sessions)
    return {
      nights: list,
      minutes: list.map((s) => (s.end_ts - s.start_ts) / 60),
      scores: list.map((s) => s.score),
      readiness: list.map((s) => byDay.get(s.day)?.readiness ?? null),
    }
  }, [daily, sessions])

  // Reparto de fases noche a noche: la otra cara del score, que es un número
  // sin desglose.
  const stack = useMemo(() => {
    const shown = nights.slice(-30)
    const width = W / Math.max(shown.length, 1)
    return shown.map((s, i) => {
      let base = H
      const seg = (min: number | null) => {
        if (min == null || min <= 0) return null
        const h = (min / 600) * H
        base -= h
        return { y: base, h }
      }
      return {
        key: s.id,
        x: i * width + 0.6,
        w: Math.max(width - 1.2, 1),
        deep: seg(s.deep_min),
        rem: seg(s.rem_min),
        light: seg(s.light_min),
      }
    })
  }, [nights])

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Scatter
        title="Cruce · dormir más"
        xs={minutes}
        ys={readiness}
        color={METRIC.readiness}
        xLabel={(v) => formatDuration(v)}
      />
      <Scatter
        title="Cruce · dormir mejor"
        xs={scores}
        ys={readiness}
        color={METRIC.sleep}
        xLabel={(v) => `score ${Math.round(v)}`}
      />

      <div className="border border-hairline bg-surface p-3">
        <p className="text-label uppercase text-ink-muted">Reparto de las noches</p>
        <p className="mb-2 mt-0.5 text-xs text-ink-secondary">Profundo, REM y ligero, noche a noche.</p>
        <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="presentation">
          {stack.map((n) => (
            <g key={n.key}>
              {n.light && <rect x={n.x} y={n.light.y} width={n.w} height={n.light.h} fill={STAGE_COLORS[4]} />}
              {n.rem && <rect x={n.x} y={n.rem.y} width={n.w} height={n.rem.h} fill={STAGE_COLORS[8]} />}
              {n.deep && <rect x={n.x} y={n.deep.y} width={n.w} height={n.deep.h} fill={STAGE_COLORS[5]} />}
            </g>
          ))}
        </svg>
        <div className="mt-1 flex justify-between font-mono text-[10px] text-ink-muted">
          <span>{stack.length} noches</span>
          <span>escala a 10 h</span>
        </div>
      </div>
    </div>
  )
}
