import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
}

export function Card({ children, className }: CardProps) {
  return (
    // Con filete y casi a escuadra: sobre papel, `surface` y `page` se
    // distinguen por un pelo, así que lo que separa la tarjeta del fondo es la
    // línea, no el escalón de tono.
    <div className={`rounded-card border border-hairline bg-surface ${className ?? ''}`}>
      {children}
    </div>
  )
}
