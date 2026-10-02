import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
    // La app ancla los días a Europe/Madrid (lib/date.ts), no a la zona de la
    // máquina. Con UTC, un formateo que olvide esa zona falla también en local,
    // no solo en el CI (que corre en UTC).
    env: { TZ: 'UTC' },
  },
})
