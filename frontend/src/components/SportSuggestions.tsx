import { sportLabel, suggestedSports } from '../lib/workouts'

/** Autocompletado nativo para los campos donde el tipo de entreno se escribe a
 * mano.
 *
 * `<datalist>` y no un combo propio: el navegador ya trae el filtrado mientras
 * escribes, el teclado, el táctil y el lector de pantalla. El `value` es la
 * etiqueta EXACTA que se guarda en `user_sport` — así "Bicicleta trabajo" se
 * escribe una vez y las demás veces se elige, sin variantes con erratas que
 * luego hay que unificar a mano. */
export function SportSuggestions({ id, sports }: { id: string; sports: readonly { name: string }[] }) {
  return (
    <datalist id={id}>
      {suggestedSports(sports).map((sport) => (
        <option key={sport.name} value={sport.name}>
          {sportLabel(sport.name)}
        </option>
      ))}
    </datalist>
  )
}
