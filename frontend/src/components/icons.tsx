interface IconProps {
  className?: string
}

const base = {
  xmlns: 'http://www.w3.org/2000/svg',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

export function HeartPulseIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M3 13h4l2-5 3 9 2-7 1.5 3H21" />
    </svg>
  )
}

export function WavesIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M3 9c1.5-1.5 3-1.5 4.5 0s3 1.5 4.5 0 3-1.5 4.5 0 3 1.5 4.5 0" />
      <path d="M3 15c1.5-1.5 3-1.5 4.5 0s3 1.5 4.5 0 3-1.5 4.5 0 3 1.5 4.5 0" />
    </svg>
  )
}

export function MoonIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z" />
    </svg>
  )
}

export function BatteryIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="2.5" y="8" width="16" height="8" rx="2" />
      <path d="M21 10.5v3" />
      <path d="M6 11v2" />
      <path d="M10 11v2" />
      <path d="M14 11v2" />
    </svg>
  )
}

export function DumbbellIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M6.5 8v8" />
      <path d="M17.5 8v8" />
      <path d="M2.5 10v4" />
      <path d="M21.5 10v4" />
      <path d="M6.5 12h11" />
    </svg>
  )
}

export function GridIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="3" y="3" width="8" height="8" rx="1.5" />
      <rect x="13" y="3" width="8" height="8" rx="1.5" />
      <rect x="3" y="13" width="8" height="8" rx="1.5" />
      <rect x="13" y="13" width="8" height="8" rx="1.5" />
    </svg>
  )
}

export function CalendarIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <rect x="3" y="5" width="18" height="16" rx="1" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </svg>
  )
}

export function ChevronDownIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m5 8.5 7 7 7-7" />
    </svg>
  )
}

export function ChevronLeftIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m15 5 -7 7 7 7" />
    </svg>
  )
}

export function ChevronRightIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m9 5 7 7 -7 7" />
    </svg>
  )
}

export function NoteIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4h13A1.5 1.5 0 0 1 20 5.5v9L14.5 20h-9A1.5 1.5 0 0 1 4 18.5z" />
      <path d="M20 14.5h-4a1.5 1.5 0 0 0-1.5 1.5v4" />
      <path d="M8 9h8M8 12.5h5" />
    </svg>
  )
}

export function BellIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M6 9a6 6 0 0 1 12 0c0 4 1.5 5.5 2 6.5H4c.5-1 2-2.5 2-6.5Z" />
      <path d="M10 19a2 2 0 0 0 4 0" />
    </svg>
  )
}

export function PlusIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

export function TagIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 4h7l9 9-7 7-9-9z" />
      <circle cx="8" cy="8" r="1.4" />
    </svg>
  )
}

export function TrashIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 6.5h16" />
      <path d="M9.5 6.5V4.5h5v2" />
      <path d="M6.5 6.5 7.5 20h9l1-13.5" />
    </svg>
  )
}

export function CloseIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  )
}

export function ZoomOutIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <circle cx="11" cy="11" r="6.5" />
      <path d="M8.5 11h5" />
      <path d="m16 16 4 4" />
    </svg>
  )
}

export function RefreshIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 12a8 8 0 0 1 14.3-4.9" />
      <path d="M18.5 3v4.5H14" />
      <path d="M20 12a8 8 0 0 1-14.3 4.9" />
      <path d="M5.5 21v-4.5H10" />
    </svg>
  )
}

export function AlertIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 3.5 21.5 20h-19Z" />
      <path d="M12 10v4" />
      <path d="M12 17.2v.1" />
    </svg>
  )
}

export function CheckIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M4 12.5 9.5 18 20 6" />
    </svg>
  )
}

export function ArrowUpIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 19V5" />
      <path d="m6 11 6-6 6 6" />
    </svg>
  )
}

export function ArrowDownIcon({ className }: IconProps) {
  return (
    <svg {...base} className={className}>
      <path d="M12 5v14" />
      <path d="m6 13 6 6 6-6" />
    </svg>
  )
}

export function SpinnerIcon({ className }: IconProps) {
  return (
    <svg {...base} className={`animate-spin ${className ?? ''}`} strokeWidth={2.4}>
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  )
}
