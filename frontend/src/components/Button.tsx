import type { ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost'
}

export function Button({ variant = 'primary', className, ...props }: ButtonProps) {
  const base =
    'inline-flex items-center justify-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50'
  const variants = {
    primary: 'bg-accent text-page hover:brightness-90',
    ghost: 'bg-raised text-ink hover:brightness-95',
  }
  return <button className={`${base} ${variants[variant]} ${className ?? ''}`} {...props} />
}
