import type { ReactNode } from 'react'
import { Icon, type IconName } from './Icon'

export function LoadingState({ label = 'Loading workspace' }: { label?: string }) {
  return (
    <div className="state-card state-card--loading" role="status" aria-label={label} aria-live="polite">
      <span className="spinner"><Icon name="loader" size={20} /></span>
      <span>{label}</span>
    </div>
  )
}

export function EmptyState({ icon = 'layers', title, body, action }: { icon?: IconName; title: string; body: string; action?: ReactNode }) {
  return (
    <div className="state-card state-card--empty">
      <div className="state-icon"><Icon name={icon} size={22} /></div>
      <h3>{title}</h3>
      <p>{body}</p>
      {action ? <div className="state-action">{action}</div> : null}
    </div>
  )
}

export function ErrorState({ title = 'Something went wrong', body, onRetry }: { title?: string; body: string; onRetry?: () => void }) {
  return (
    <div className="state-card state-card--error" role="alert">
      <div className="state-icon state-icon--error"><Icon name="x" size={22} /></div>
      <h3>{title}</h3>
      <p>{body}</p>
      {onRetry ? <button className="button button--secondary" onClick={onRetry}><Icon name="refresh" size={16} /> Try again</button> : null}
    </div>
  )
}
