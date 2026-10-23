import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  Card,
  EmptyState,
  ErrorAlert,
  Field,
  LoadingBlock,
  Modal,
  StatusBadge,
} from '../components/ui'
import { ApiError, api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useToast } from '../lib/toast'
import {
  RECURRENCE_LABELS,
  dueHint,
  formatAmount,
  formatBytes,
  formatDate,
} from '../lib/format'
import type { Attachment, Occurrence, RecurringPayment } from '../lib/types'
import { PayModal } from '../features/PayModal'
import { PaymentFormModal } from '../features/PaymentFormModal'

export function PaymentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { isAdmin } = useAuth()
  const toast = useToast()

  const [payment, setPayment] = useState<RecurringPayment | null>(null)
  const [history, setHistory] = useState<Occurrence[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [payTarget, setPayTarget] = useState<Occurrence | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [confirmDeactivate, setConfirmDeactivate] = useState(false)
  const [attachmentsFor, setAttachmentsFor] = useState<Occurrence | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [paymentData, historyData] = await Promise.all([
        api.get<RecurringPayment>(`/recurring-payments/${id}`),
        api.get<Occurrence[]>(`/recurring-payments/${id}/history`),
      ])
      setPayment(paymentData)
      setHistory(historyData)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Неизвестная ошибка')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    void load()
  }, [load])

  const handleDeactivate = async () => {
    if (!id) return
    try {
      await api.delete(`/recurring-payments/${id}`)
      toast.push('Регулярный платёж завершён. История периодов сохранена.')
      setConfirmDeactivate(false)
      await load()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось завершить', 'error')
    }
  }

  if (loading) return <LoadingBlock label="Загрузка платежа…" />
  if (error) return <ErrorAlert message={error} onRetry={load} />
  if (!payment) return null

  return (
    <>
      <div className="page-header">
        <div>
          <Link to="/payments" className="text-small">
            ← К списку платежей
          </Link>
          <h1 className="page-header__title" style={{ marginTop: '4px' }}>
            {payment.title}
          </h1>
          <p className="page-header__description">
            {formatAmount(payment.amount, payment.currency)} ·{' '}
            {RECURRENCE_LABELS[payment.recurrence]} · день {payment.anchor_day}
          </p>
        </div>
        {isAdmin && (
          <div className="btn-row">
            <button type="button" className="btn btn--secondary" onClick={() => setEditOpen(true)}>
              Изменить параметры
            </button>
            {payment.is_active && (
              <button
                type="button"
                className="btn btn--danger"
                onClick={() => setConfirmDeactivate(true)}
                data-testid="deactivate-payment"
              >
                Завершить платёж
              </button>
            )}
          </div>
        )}
      </div>

      {!payment.is_active && (
        <div className="alert alert--info" role="status">
          Регулярный платёж завершён: новые периоды не создаются и напоминания не отправляются.
          История ниже сохранена полностью.
        </div>
      )}

      {payment.description && (
        <Card title="Описание">
          <p style={{ margin: 0 }}>{payment.description}</p>
        </Card>
      )}

      <div className="stat-grid">
        <div className="stat">
          <div className="stat__label">Всего периодов</div>
          <div className="stat__value">{payment.occurrences_count}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Не оплачено</div>
          <div className="stat__value">{payment.unpaid_count}</div>
        </div>
        <div className="stat">
          <div className="stat__label">
            <span className="badge badge--overdue">
              <span className="badge__dot" aria-hidden="true" />
              Просрочено
            </span>
          </div>
          <div className="stat__value">{payment.overdue_count}</div>
        </div>
        <div className="stat">
          <div className="stat__label">Первый срок</div>
          <div className="stat__value" style={{ fontSize: '18px' }}>
            {formatDate(payment.first_due_date)}
          </div>
        </div>
      </div>

      <Card
        title="История периодов"
        subtitle="Каждый период независим; прошлые периоды сохраняются при завершении платежа"
        flush
      >
        {history.length === 0 ? (
          <EmptyState icon="📅" title="Периодов пока нет" text="Периоды будут сформированы автоматически." />
        ) : (
          <div className="table-wrap">
            <table className="table table--responsive">
              <thead>
                <tr>
                  <th scope="col">Срок</th>
                  <th scope="col">Сумма</th>
                  <th scope="col">Статус</th>
                  <th scope="col">Фактическая дата</th>
                  <th scope="col">Чек</th>
                  <th scope="col" style={{ textAlign: 'right' }}>
                    Действия
                  </th>
                </tr>
              </thead>
              <tbody>
                {history.map((item) => (
                  <tr key={item.id}>
                    <td data-label="Срок">
                      {formatDate(item.due_date)}
                      <div className="table__meta">{dueHint(item)}</div>
                    </td>
                    <td data-label="Сумма" className="table__amount">
                      {formatAmount(item.amount, item.currency)}
                    </td>
                    <td data-label="Статус">
                      <StatusBadge status={item.status} />
                    </td>
                    <td data-label="Фактическая дата">{formatDate(item.paid_at)}</td>
                    <td data-label="Чек">
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => setAttachmentsFor(item)}
                      >
                        {item.attachment_count > 0 ? `${item.attachment_count} файл(а)` : 'Добавить'}
                      </button>
                    </td>
                    <td data-label="Действия">
                      <div className="table__actions">
                        {item.is_paid ? (
                          <>
                            <button
                              type="button"
                              className="btn btn--ghost btn--sm"
                              onClick={() => setPayTarget(item)}
                            >
                              Изменить дату
                            </button>
                            <button
                              type="button"
                              className="btn btn--ghost btn--sm"
                              onClick={async () => {
                                try {
                                  await api.patch(`/payment-occurrences/${item.id}`, { is_paid: false })
                                  toast.push('Отметка об оплате снята')
                                  await load()
                                } catch (err) {
                                  toast.push(
                                    err instanceof ApiError ? err.detail : 'Ошибка',
                                    'error',
                                  )
                                }
                              }}
                            >
                              Снять отметку
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className="btn btn--success btn--sm"
                            onClick={async () => {
                              try {
                                await api.patch(`/payment-occurrences/${item.id}`, { is_paid: true })
                                toast.push('Период отмечен как оплаченный')
                                await load()
                              } catch (err) {
                                toast.push(
                                  err instanceof ApiError ? err.detail : 'Ошибка',
                                  'error',
                                )
                              }
                            }}
                          >
                            Оплачено
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <PayModal
        occurrence={payTarget}
        onClose={() => setPayTarget(null)}
        onSaved={() => {
          setPayTarget(null)
          void load()
        }}
      />

      <PaymentFormModal
        open={editOpen}
        payment={payment}
        onClose={() => setEditOpen(false)}
        onSaved={() => {
          setEditOpen(false)
          void load()
        }}
      />

      <Modal
        open={confirmDeactivate}
        title="Завершить регулярный платёж?"
        description="Новые периоды не будут создаваться, напоминания прекратятся."
        onClose={() => setConfirmDeactivate(false)}
        footer={
          <>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setConfirmDeactivate(false)}
            >
              Отмена
            </button>
            <button
              type="button"
              className="btn btn--danger"
              onClick={handleDeactivate}
              data-testid="confirm-deactivate"
            >
              Завершить платёж
            </button>
          </>
        }
      >
        <p style={{ margin: 0 }}>
          Вся история периодов, включая отметки об оплате и просрочки, будет сохранена. Сама запись
          регулярного платежа остаётся в системе.
        </p>
      </Modal>

      <AttachmentsModal
        occurrence={attachmentsFor}
        onClose={() => setAttachmentsFor(null)}
        onChanged={() => void load()}
      />
    </>
  )
}

function AttachmentsModal({
  occurrence,
  onClose,
  onChanged,
}: {
  occurrence: Occurrence | null
  onClose: () => void
  onChanged: () => void
}) {
  const toast = useToast()
  const [items, setItems] = useState<Attachment[]>([])
  const [loading, setLoading] = useState(false)
  const [receiptUrl, setReceiptUrl] = useState('')
  const [savingLink, setSavingLink] = useState(false)

  const load = useCallback(async () => {
    if (!occurrence) return
    setLoading(true)
    try {
      setItems(await api.get<Attachment[]>(`/attachments/occurrence/${occurrence.id}`))
      setReceiptUrl(occurrence.receipt_url ?? '')
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось загрузить чеки', 'error')
    } finally {
      setLoading(false)
    }
  }, [occurrence, toast])

  useEffect(() => {
    void load()
  }, [load])

  if (!occurrence) return null

  const handleUpload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    try {
      await api.upload(`/attachments/occurrence/${occurrence.id}`, formData)
      toast.push('Файл загружен')
      await load()
      onChanged()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось загрузить файл', 'error')
    }
  }

  const handleDelete = async (attachmentId: number) => {
    try {
      await api.delete(`/attachments/${attachmentId}`)
      toast.push('Файл удалён')
      await load()
      onChanged()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось удалить файл', 'error')
    }
  }

  const handleSaveLink = async () => {
    setSavingLink(true)
    try {
      await api.patch(`/payment-occurrences/${occurrence.id}`, {
        receipt_url: receiptUrl.trim() || null,
      })
      toast.push('Ссылка на чек сохранена')
      onChanged()
    } catch (err) {
      toast.push(err instanceof ApiError ? err.detail : 'Не удалось сохранить ссылку', 'error')
    } finally {
      setSavingLink(false)
    }
  }

  return (
    <Modal
      open
      wide
      title="Чеки и подтверждения"
      description={`${occurrence.payment_title} · срок ${formatDate(occurrence.due_date)}`}
      onClose={onClose}
      footer={
        <button type="button" className="btn btn--secondary" onClick={onClose}>
          Закрыть
        </button>
      }
    >
      <div className="stack">
        <Field
          label="Ссылка на подтверждение оплаты"
          htmlFor="receipt-url"
          hint="Публичная ссылка на чек или платёжный документ."
        >
          <div className="row">
            <input
              id="receipt-url"
              className="input"
              placeholder="https://…"
              value={receiptUrl}
              onChange={(event) => setReceiptUrl(event.target.value)}
            />
            <button
              type="button"
              className="btn btn--secondary"
              onClick={handleSaveLink}
              disabled={savingLink}
            >
              Сохранить
            </button>
          </div>
        </Field>

        <Field
          label="Загрузить файл"
          htmlFor="receipt-file"
          hint="PDF, PNG, JPEG или WebP. Размер ограничен настройкой сервера."
        >
          <input
            id="receipt-file"
            type="file"
            className="input"
            accept=".pdf,.png,.jpg,.jpeg,.webp"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void handleUpload(file)
              event.target.value = ''
            }}
            data-testid="receipt-file-input"
          />
        </Field>

        {loading ? (
          <LoadingBlock label="Загрузка файлов…" />
        ) : items.length === 0 ? (
          <EmptyState icon="🧾" title="Файлов нет" text="Прикрепите чек или платёжное подтверждение." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Файл</th>
                  <th scope="col">Размер</th>
                  <th scope="col" style={{ textAlign: 'right' }}>
                    Действия
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.original_name}</td>
                    <td>{formatBytes(item.size_bytes)}</td>
                    <td>
                      <div className="table__actions">
                        <a
                          className="btn btn--ghost btn--sm"
                          href={`/api/v1/attachments/${item.id}/download`}
                          target="_blank"
                          rel="noreferrer noopener"
                        >
                          Скачать
                        </a>
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => handleDelete(item.id)}
                        >
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-tiny text-muted" style={{ margin: 0 }}>
          Файлы доступны только авторизованным пользователям. Внутреннее имя файла генерируется
          сервером и не совпадает с исходным.
        </p>
      </div>
    </Modal>
  )
}
