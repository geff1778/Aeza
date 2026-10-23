/** Reusable presentational components shared across pages. */

import { useEffect, useRef, type ReactNode } from 'react'
import type { PaymentStatus } from '../lib/types'
import { STATUS_LABELS } from '../lib/format'

export function Card({
  title,
  subtitle,
  actions,
  children,
  flush,
}: {
  title?: string
  subtitle?: string
  actions?: ReactNode
  children: ReactNode
  flush?: boolean
}) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card__header">
          <div>
            {title && <h2 className="card__title">{title}</h2>}
            {subtitle && <div className="card__subtitle">{subtitle}</div>}
          </div>
          {actions && <div className="btn-row">{actions}</div>}
        </header>
      )}
      <div className={flush ? 'card__body card__body--flush' : 'card__body'}>{children}</div>
    </section>
  )
}

export function StatusBadge({ status }: { status: PaymentStatus }) {
  return (
    <span className={`badge badge--${status}`}>
      <span className="badge__dot" aria-hidden="true" />
      {STATUS_LABELS[status]}
    </span>
  )
}

export function Spinner() {
  return <span className="spinner" aria-hidden="true" />
}

export function LoadingBlock({ label = 'Загрузка…' }: { label?: string }) {
  return (
    <div className="loading-block" role="status">
      <Spinner />
      <span>{label}</span>
    </div>
  )
}

export function ErrorAlert({
  message,
  onRetry,
}: {
  message: string
  onRetry?: () => void
}) {
  return (
    <div className="alert alert--error" role="alert">
      <div style={{ flex: 1 }}>
        <div className="alert__title">Не удалось загрузить данные</div>
        <div>{message}</div>
      </div>
      {onRetry && (
        <button type="button" className="btn btn--secondary btn--sm" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  title,
  text,
  action,
  icon = '📭',
}: {
  title: string
  text: string
  action?: ReactNode
  icon?: string
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon" aria-hidden="true">
        {icon}
      </div>
      <div className="empty-state__title">{title}</div>
      <p className="empty-state__text">{text}</p>
      {action && <div style={{ marginTop: '16px' }}>{action}</div>}
    </div>
  )
}

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  wide,
}: {
  open: boolean
  title: string
  description?: string
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  wide?: boolean
}) {
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialogRef.current?.focus()
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = previous
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className={wide ? 'modal modal--wide' : 'modal'}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={dialogRef}
        tabIndex={-1}
      >
        <header className="modal__header">
          <div>
            <h2 className="modal__title">{title}</h2>
            {description && <div className="modal__description">{description}</div>}
          </div>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Закрыть">
            ✕
          </button>
        </header>
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__footer">{footer}</footer>}
      </div>
    </div>
  )
}

export function Field({
  label,
  hint,
  error,
  htmlFor,
  full,
  children,
}: {
  label: string
  hint?: string
  error?: string
  htmlFor?: string
  full?: boolean
  children: ReactNode
}) {
  return (
    <div className={full ? 'field field--full' : 'field'}>
      <label className="field__label" htmlFor={htmlFor}>
        {label}
      </label>
      {children}
      {hint && !error && <span className="field__hint">{hint}</span>}
      {error && (
        <span className="field__error" role="alert">
          {error}
        </span>
      )}
    </div>
  )
}

export function ProgressBar({ percent, variant }: { percent: number; variant?: 'warning' | 'error' }) {
  const clamped = Math.max(0, Math.min(100, percent))
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(percent)} aria-valuemin={0} aria-valuemax={100}>
      <div
        className={variant ? `progress__bar progress__bar--${variant}` : 'progress__bar'}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}
