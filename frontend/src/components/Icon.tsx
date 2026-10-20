import type { SVGProps } from 'react'

export type IconName =
  | 'activity'
  | 'arrow-up-right'
  | 'bell'
  | 'book'
  | 'box'
  | 'check'
  | 'chevron-down'
  | 'chevron-right'
  | 'clock'
  | 'code'
  | 'compare'
  | 'download'
  | 'external'
  | 'file'
  | 'filter'
  | 'git-branch'
  | 'github'
  | 'globe'
  | 'history'
  | 'layers'
  | 'link'
  | 'loader'
  | 'lock'
  | 'menu'
  | 'minus'
  | 'plus'
  | 'refresh'
  | 'repo'
  | 'search'
  | 'settings'
  | 'shield'
  | 'spark'
  | 'terminal'
  | 'upload'
  | 'x'

const paths: Record<IconName, string[]> = {
  activity: ['M3 12h4l2.2-7 4.2 14L16 9l2 3h3'],
  'arrow-up-right': ['M7 17 17 7', 'M7 7h10v10'],
  bell: ['M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9', 'M10 21h4'],
  book: ['M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z', 'M4 5.5v16', 'M8 7h8'],
  box: ['m7.5 4.5 4.5-2 4.5 2', 'M3 7l9 4 9-4', 'M12 11v10', 'm3 7 1 11 8 3 8-3 1-11'],
  check: ['m5 12 4 4L19 6'],
  'chevron-down': ['m6 9 6 6 6-6'],
  'chevron-right': ['m9 18 6-6-6-6'],
  clock: ['M12 7v5l3 2', 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z'],
  code: ['m8 9-4 3 4 3', 'm16 9 4 3-4 3', 'm14 5-4 14'],
  compare: ['M7 4v16', 'M17 4v16', 'M4 7h6', 'M14 17h6', 'M4 17h6', 'M14 7h6'],
  download: ['M12 3v12', 'm7 10 5 5 5-5', 'M4 21h16'],
  external: ['M14 4h6v6', 'M20 4 12 12', 'M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6'],
  file: ['M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', 'M14 2v6h6', 'M8 13h8', 'M8 17h6'],
  filter: ['M4 6h16', 'M7 12h10', 'M10 18h4'],
  'git-branch': ['M6 3v12', 'M18 9V3', 'M6 9c0 3 3 3 6 3s6 0 6-3', 'M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z', 'M18 6a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z'],
  github: ['M15 22v-4a4.8 4.8 0 0 0-1-3.5c3.3-.4 6.7-1.6 6.7-7A5.4 5.4 0 0 0 19.2 4 5 5 0 0 0 19 0S17.8-.4 15 1.5a13.4 13.4 0 0 0-6 0C6.2-.4 5 0 5 0a5 5 0 0 0-.2 4A5.4 5.4 0 0 0 3.5 7.5c0 5.4 3.4 6.6 6.7 7A4.8 4.8 0 0 0 9 18v4'],
  globe: ['M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z', 'M3 12h18', 'M12 3a14 14 0 0 1 0 18', 'M12 3a14 14 0 0 0 0 18'],
  history: ['M3 12a9 9 0 1 0 3-6.7', 'M3 4v5h5', 'M12 7v5l3 2'],
  layers: ['m12 2 9 5-9 5-9-5 9-5Z', 'm3 12 9 5 9-5', 'm3 17 9 5 9-5'],
  link: ['M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.1 1.1', 'M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.1-1.1'],
  loader: ['M12 2v4', 'M12 18v4', 'M4.93 4.93l2.83 2.83', 'M16.24 16.24l2.83 2.83', 'M2 12h4', 'M18 12h4', 'M4.93 19.07l2.83-2.83', 'M16.24 7.76l2.83-2.83'],
  lock: ['M6 10V7a6 6 0 0 1 12 0v3', 'M5 10h14v11H5z', 'M12 14v3'],
  menu: ['M4 6h16', 'M4 12h16', 'M4 18h16'],
  minus: ['M5 12h14'],
  plus: ['M12 5v14', 'M5 12h14'],
  refresh: ['M20 11a8 8 0 0 0-14.7-4L3 10', 'M3 4v6h6', 'M4 13a8 8 0 0 0 14.7 4L21 14', 'M21 20v-6h-6'],
  repo: ['M4 4h16v16H4z', 'M8 8h8', 'M8 12h5', 'M8 16h7'],
  search: ['m21 21-4.3-4.3', 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Z'],
  settings: ['M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z', 'M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.8 1.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5v.1h-2.5v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1-1.8-1.8.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H6.5v-2.5h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1 1.8-1.8.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.5V4h2.5v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.8 1.8-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.1v2.5h-.1a1.7 1.7 0 0 0-1.5 1.5Z'],
  shield: ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z', 'm9 12 2 2 4-4'],
  spark: ['m12 3-1.4 5.6L5 10l5.6 1.4L12 17l1.4-5.6L19 10l-5.6-1.4Z', 'm19 16-.6 2.4L16 19l2.4.6L19 22l.6-2.4L22 19l-2.4-.6Z'],
  terminal: ['M4 5h16v14H4z', 'm7 9 3 3-3 3', 'M13 15h4'],
  upload: ['M12 16V4', 'm7 9 5-5 5 5', 'M4 20h16'],
  x: ['M6 6l12 12', 'M18 6 6 18'],
}

export function Icon({ name, size = 18, strokeWidth = 1.8, className, ...props }: SVGProps<SVGSVGElement> & { name: IconName; size?: number; strokeWidth?: number }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth={strokeWidth}
      viewBox="0 0 24 24"
      width={size}
      {...props}
    >
      {paths[name].map((path, index) => <path d={path} key={`${name}-${index}`} />)}
    </svg>
  )
}
