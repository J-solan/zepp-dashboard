import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
    // La app ancla los días a la zona del backend (lib/date.ts), no a la de la
    // máquina. Con UTC, un formateo que olvide esa zona falla también en local,
    // no solo en el CI (que corre en UTC). test-setup.ts fija la de la app.
    env: { TZ: 'UTC' },
    setupFiles: ['src/test-setup.ts'],
  },
})
