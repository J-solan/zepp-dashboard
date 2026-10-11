import { setAppTz } from './lib/date'

// En la app la zona la fija el backend al arrancar (main.tsx); sin eso vale la
// del navegador, que aquí es UTC (vitest.config.ts). Los tests se escribieron
// contra Europe/Madrid, distinta a propósito de la de la máquina: así un
// formateo que olvide la zona de la app falla también en local.
setAppTz('Europe/Madrid')
