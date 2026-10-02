# fixtures/ — payloads sanitizados (versionados)

Aquí van los payloads **anonimizados/sintéticos** que sí se commitean y que usan
los tests de parsers en CI. Mantienen la **misma estructura** que los reales pero
sin datos de salud personales.

Las genera `../sanitize_fixtures.py` a partir de los payloads reales de
`../fixtures_local/` (sueño/FC → `band_data`, BioCharge, historial de deportes),
sustituyendo valores por datos plausibles pero ficticios.

> Los payloads **reales** viven en `../fixtures_local/` y están en `.gitignore`:
> nunca se suben al repositorio.
