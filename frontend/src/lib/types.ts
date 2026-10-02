export interface Overview {
  date: string
  biocharge: {
    ts: number
    total: number | null
    mental: number | null
    physical: number | null
    status: number
  } | null
  readiness: number | null
  steps: number | null
  sleep: {
    score: number | null
    duration_min: number
  } | null
  last_sync: {
    ts: number | null
    status: 'ok' | 'error' | 'unknown'
  }
}

/** Fila de `daily_metrics` (histórico diario, `GET /api/daily`). Casi todo es
 * nullable: cada job rellena SUS columnas, así que un día puede tener pasos y
 * no readiness. Los días sin fila no vienen en la respuesta. */
export interface DailyMetrics {
  day: string
  steps: number | null
  calories: number | null
  resting_hr: number | null
  readiness: number | null
  hrv_ms: number | null
  respiratory_rate: number | null
  stress_avg: number | null
  vo2max: number | null
  train_load: number | null
  tz: string | null
}

export interface SyncStatus {
  status: 'idle' | 'running' | 'ok' | 'error'
  started_at: number | null
  finished_at: number | null
  stats: unknown
  error: string | null
}

// `bpm`/`value` pueden ser null: marcador de hueco insertado por el servidor
// para cortar la línea en un tramo sin muestras.
export interface HrSample {
  ts: number
  bpm: number | null
}

export interface StressSample {
  ts: number
  value: number | null
}

export interface BiochargeSample {
  ts: number
  total: number | null
  mental: number | null
  physical: number | null
  status: number | null
}

// Estadísticos EXACTOS del rango, calculados en servidor sobre el crudo
// min/avg/max reales, no la media de los buckets. null si el rango
// está vacío.
export interface Stats {
  min: number | null
  avg: number | null
  max: number | null
}

export interface HrSeries {
  series: HrSample[]
  stats: Stats
}

export interface StressSeries {
  series: StressSample[]
  stats: Stats
}

/** Nota manual sobre un tramo de la línea de tiempo. No pertenece a ninguna
 * métrica: se pinta igual sobre FC y sobre estrés. */
export interface Annotation {
  id: number
  start_ts: number
  end_ts: number
  text: string
  created_at: number
}

/** Segundos pasados en una zona de FC. `threshold` es el bpm MÁXIMO de la zona
 * (el último umbral de un workout coincide siempre con su `max_hr`), así que la
 * zona i abarca (threshold[i-1], threshold[i]]. */
export interface HrZone {
  seconds: number
  threshold: number
}

export interface WorkoutSet {
  set_index: number | null
  reps: number | null
  weight_kg: number | null
  rpe: number | null
  /** 'normal' | 'warmup' | 'dropset' | 'failure', verbatim de Hevy. */
  set_type: string | null
}

export interface WorkoutExercise {
  exercise: string
  muscle_group: string | null
  sets: WorkoutSet[]
}

export interface WorkoutMuscle {
  muscle: string
  /** 0-1: cuánto entra ese músculo en la sesión. 1 = principal. */
  intensity: number
}

/** Lado fisiológico del entreno: el workout del strap vinculado al de Hevy. */
export interface StrapData {
  id: number
  sport_type: number | null
  start_ts: number
  end_ts: number
  train_load: number | null
  te: number | null
  avg_hr: number | null
  max_hr: number | null
  hr_zones: HrZone[]
}

export interface Workout {
  id: number
  /** `manual` = lo creaste tú; la ingesta no toca esas filas y sí se pueden
   * borrar de verdad (las de Zepp volverían en el siguiente sync). */
  source: 'zepp' | 'hevy' | 'manual'
  external_id: string | null
  /** Nombre que trae la FUENTE: `sport_title` de Zepp o el título del entreno
   * de Hevy. La ingesta lo reescribe en cada sync. */
  title: string | null
  /** Nombre que escribió el usuario. La ingesta NUNCA lo toca (migración 006). */
  user_title: string | null
  /** `user_title` y, si no hay, `title`. Es lo que se pinta. */
  effective_title: string | null
  notes: string | null
  sport: string | null
  sport_type: number | null
  /** `user_sport` si el usuario lo clasificó, si no el mapa `sport_types`.
   * `null` = code desconocido sin revisar. */
  effective_sport: string | null
  start_ts: number
  end_ts: number
  duration_s: number | null
  train_load: number | null
  te: number | null
  avg_hr: number | null
  max_hr: number | null
  hr_zones: HrZone[]
  strength_scores: number[] | null
  auto_recognized: boolean
  review_status: 'auto' | 'pending' | 'classified' | 'ignored'
  user_sport: string | null
  linked_workout_id: number | null
  hr_overlay?: { ts: number; bpm: number }[]
  /** Solo en workouts de Hevy (fuente de verdad de fuerza). */
  exercises?: WorkoutExercise[]
  muscles?: WorkoutMuscle[]
  strap?: StrapData | null
}

/** Volumen ponderado de un músculo en el rango: Σ(peso × reps × intensity)
 * sobre las series efectivas (sin calentamiento). No es "peso movido": es
 * comparable entre músculos, que es lo que necesita el mapa. */
export interface MuscleVolume {
  muscle: string
  volume: number
  sets: number
  top_exercises: { exercise: string; volume: number; sets: number }[]
}

export interface MuscleVolumes {
  from: string
  to: string
  total_volume: number
  muscles: MuscleVolume[]
}

/** Entreno de Hevy del mismo día sin vincular: la pista que hace contestable
 * el "¿qué hiciste aquí?" de la cola de revisión. */
export interface HevyEvidence {
  id: number
  title: string | null
  n_sets: number
  duration_s: number | null
}

export interface PendingWorkout extends Workout {
  hevy_evidence: HevyEvidence | null
}

export interface SleepStage {
  start_ts: number
  end_ts: number
  stage: number
}

export interface SleepSession {
  id: number
  day: string
  start_ts: number
  end_ts: number
  score: number | null
  deep_min: number | null
  light_min: number | null
  rem_min: number | null
  awake_min: number | null
  wake_count: number | null
  resting_hr: number | null
  tz: string
  is_nap: boolean
  stages: SleepStage[]
}
