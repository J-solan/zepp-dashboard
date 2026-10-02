PRAGMA journal_mode=WAL;

-- Landing: JSON crudo → reproceso sin re-tirar de la API no oficial
CREATE TABLE IF NOT EXISTS raw_ingest (
  id INTEGER PRIMARY KEY, source TEXT NOT NULL, day TEXT,
  fetched_at INTEGER NOT NULL, payload TEXT NOT NULL);

-- Series por minuto
CREATE TABLE IF NOT EXISTS biocharge (ts INTEGER PRIMARY KEY,     -- unix s UTC
  total REAL, mental REAL, physical REAL, status INTEGER);
CREATE TABLE IF NOT EXISTS hr_minute (ts INTEGER PRIMARY KEY, bpm INTEGER);  -- centinela descartado al ingerir

-- Métricas diarias (wide, upsert desde varios jobs)
CREATE TABLE IF NOT EXISTS daily_metrics (day TEXT PRIMARY KEY,  -- 'YYYY-MM-DD' local
  steps INTEGER, calories INTEGER, resting_hr INTEGER,
  readiness INTEGER, hrv_ms REAL, respiratory_rate REAL, stress_avg INTEGER,
  vo2max REAL, train_load INTEGER, tz TEXT);

-- Sueño (id propio + UNIQUE(day,start_ts) para admitir siestas)
CREATE TABLE IF NOT EXISTS sleep_session (id INTEGER PRIMARY KEY,
  day TEXT, start_ts INTEGER, end_ts INTEGER, score INTEGER,
  deep_min INTEGER, light_min INTEGER, rem_min INTEGER,
  awake_min INTEGER, wake_count INTEGER, resting_hr INTEGER,
  tz TEXT,
  UNIQUE(day, start_ts));
CREATE TABLE IF NOT EXISTS sleep_stage (id INTEGER PRIMARY KEY,
  session_id INTEGER REFERENCES sleep_session(id),
  start_ts INTEGER, end_ts INTEGER, stage INTEGER);        -- 4=ligero 5=profundo 7=despierto 8=REM

-- Estrés intradía (serie para GET /api/stress)
CREATE TABLE IF NOT EXISTS stress_sample (ts INTEGER PRIMARY KEY, value INTEGER);

-- Workouts (Hevy fuerza + strap vóley/overlay futuro)
CREATE TABLE IF NOT EXISTS workout (id INTEGER PRIMARY KEY, source TEXT NOT NULL,
  external_id TEXT, sport TEXT, sport_type INTEGER,        -- 52=fuerza 122=vóley 223=auto-IA
  start_ts INTEGER, end_ts INTEGER,
  train_load INTEGER, te REAL,                             -- te = training effect 1.0-5.0
  avg_hr INTEGER, max_hr INTEGER,                          -- si null en summary, derivar de hr_minute
  hr_zones TEXT,                                           -- 'heart_range' crudo, se parsea al leer
  strength_scores TEXT,                                    -- 'strengthScores' de Zepp (opcional, fuerza)
  auto_recognized INTEGER,                                 -- 1 = type 223
  review_status TEXT DEFAULT 'auto',                       -- 'auto'|'pending'|'classified'|'ignored'
  user_sport TEXT,                                         -- tipo asignado por el usuario si reclasifica
  UNIQUE(source, external_id));
CREATE TABLE IF NOT EXISTS workout_set (id INTEGER PRIMARY KEY,
  workout_id INTEGER REFERENCES workout(id),
  exercise TEXT, muscle_group TEXT, set_index INTEGER,
  reps INTEGER, weight_kg REAL, rpe REAL);

-- Bookkeeping de sync: último fetch OK por fuente/día
CREATE TABLE IF NOT EXISTS sync_state (source TEXT, day TEXT, last_ok_at INTEGER,
  status TEXT, PRIMARY KEY(source, day));

CREATE INDEX IF NOT EXISTS idx_workout_start ON workout(start_ts);
CREATE INDEX IF NOT EXISTS idx_sleep_stage_session ON sleep_stage(session_id);
