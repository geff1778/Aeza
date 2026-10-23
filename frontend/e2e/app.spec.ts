import { expect, test } from '@playwright/test'
import { ADMIN, USER, goTo, login, logout, paymentRow, searchFor, uniqueTitle } from './helpers'

/**
 * Full product scenario, mirroring the hackathon demo script:
 * auth guard -> admin creates -> period generated -> user pays ->
 * date corrected -> unmarked -> independence -> completion keeps history.
 */

test.describe('authentication and access control', () => {
  test('protected pages redirect to login when unauthenticated', async ({ page }) => {
    await page.goto('/payments')
    await expect(page).toHaveURL(/\/login/)
    await expect(page.getByTestId('login-submit')).toBeVisible()
  })

  test('a regular user does not see admin navigation', async ({ page }) => {
    await login(page, USER)
    await expect(page.getByRole('link', { name: 'Пользователи', exact: true })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Журнал действий', exact: true })).toHaveCount(0)
  })

  test('a regular user cannot reach the users page directly', async ({ page }) => {
    await login(page, USER)
    await page.goto('/users')
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
  })

  test('wrong password shows an error and stays on login', async ({ page }) => {
    await page.goto('/login')
    await page.getByTestId('login-username').fill(ADMIN.username)
    await page.getByTestId('login-password').fill('definitely-wrong-password')
    await page.getByTestId('login-submit').click()
    await expect(page.getByRole('alert')).toBeVisible()
    await expect(page).toHaveURL(/\/login/)
  })

  test('logout returns to login and the session is really gone', async ({ page }) => {
    await login(page, ADMIN)
    await logout(page)
    await page.goto('/payments')
    await expect(page).toHaveURL(/\/login/)
  })
})

test.describe('dashboard and calendar render real data', () => {
  test('dashboard shows currency-separated totals and integrations', async ({ page }) => {
    await login(page, ADMIN)
    await expect(page.getByTestId('stat-upcoming')).toContainText('RUB')
    await expect(page.getByTestId('stat-overdue')).toBeVisible()
    await expect(page.getByTestId('stat-due-soon')).toBeVisible()
    await expect(page.getByTestId('stat-paid')).toBeVisible()
    await expect(page.getByText('Каналы уведомлений')).toBeVisible()
  })

  test('calendar renders the month grid and real events', async ({ page }) => {
    await login(page, ADMIN)
    await goTo(page, 'Календарь')
    await expect(page.getByRole('heading', { name: 'Календарь платежей' })).toBeVisible()
    await expect(page.locator('.calendar__weekday')).toHaveCount(7)
    await expect(page.locator('.calendar__event').first()).toBeVisible()
  })
})

test.describe('payment lifecycle across two users', () => {
  const title = uniqueTitle('E2E Платёж')

  test('admin creates a payment and its period is generated', async ({ page }) => {
    await login(page, ADMIN)
    await goTo(page, 'Платежи')
    await page.getByTestId('create-payment-button').click()

    await page.getByTestId('form-title').fill(title)
    await page.getByTestId('form-amount').fill('4321.50')
    await page.getByTestId('form-currency').selectOption('RUB')
    // A past due date guarantees an overdue period for the status checks below.
    const past = new Date(Date.now() - 7 * 86_400_000).toISOString().slice(0, 10)
    await page.getByTestId('form-first-due').fill(past)
    await page.getByTestId('submit-payment-form').click()

    await expect(page.getByText('Регулярный платёж создан, периоды сформированы')).toBeVisible()
    await searchFor(page, title)

    const row = paymentRow(page, title)
    await expect(row).toContainText(title)
    await expect(row).toContainText('Просрочено')
  })

  test('regular user sees the same shared period and marks it paid', async ({ page }) => {
    await login(page, USER)
    await goTo(page, 'Платежи')
    await searchFor(page, title)

    const row = paymentRow(page, title)
    await expect(row).toContainText('Просрочено')

    await row.getByTestId('mark-paid').click()
    await expect(page.getByText(/отмечен как оплаченный/)).toBeVisible()
    // Paid after the due date => late, and the UI must say so in words.
    await expect(paymentRow(page, title)).toContainText('Оплачено с просрочкой')
  })

  test('shared status survives a page reload', async ({ page }) => {
    await login(page, ADMIN)
    await page.goto('/payments')
    await searchFor(page, title)
    await page.reload()
    await searchFor(page, title)
    await expect(paymentRow(page, title)).toContainText('Оплачено с просрочкой')
  })

  test('correcting the actual date flips late payment to on-time', async ({ page }) => {
    await login(page, USER)
    await page.goto('/payments')
    await searchFor(page, title)

    const row = paymentRow(page, title)
    const dueText = await row.textContent()
    const dueMatch = dueText?.match(/(\d{2})\.(\d{2})\.(\d{4})/)
    expect(dueMatch).toBeTruthy()
    const [, dd, mm, yyyy] = dueMatch!
    const due = new Date(`${yyyy}-${mm}-${dd}T00:00:00Z`)
    const earlier = new Date(due.getTime() - 2 * 86_400_000).toISOString().slice(0, 10)

    await row.getByTestId('edit-paid-date').click()
    await page.getByTestId('paid-at-input').fill(earlier)
    await page.getByTestId('save-paid-date').click()

    await expect(paymentRow(page, title)).toContainText('Оплачено вовремя')
    // The due date itself must not have moved.
    await expect(paymentRow(page, title)).toContainText(`${dd}.${mm}.${yyyy}`)
  })

  test('removing the paid mark restores the overdue state', async ({ page }) => {
    await login(page, USER)
    await page.goto('/payments')
    await searchFor(page, title)

    await paymentRow(page, title).getByTestId('unmark-paid').click()
    await expect(page.getByText('Отметка об оплате снята')).toBeVisible()
    await expect(paymentRow(page, title)).toContainText('Просрочено')
  })

  test('periods are independent and history is kept after completion', async ({ page }) => {
    await login(page, ADMIN)
    await page.goto('/payments')
    await searchFor(page, title)
    await paymentRow(page, title).getByRole('link', { name: title }).click()

    await expect(page.getByRole('heading', { name: title })).toBeVisible()
    const rows = page.locator('tbody tr')
    await expect(rows.first()).toBeVisible()
    const beforeCount = await rows.count()
    expect(beforeCount).toBeGreaterThan(1)

    await page.getByTestId('deactivate-payment').click()
    await page.getByTestId('confirm-deactivate').click()
    await expect(page.getByText(/История периодов сохранена|завершён/).first()).toBeVisible()

    await page.reload()
    await expect(page.locator('tbody tr')).toHaveCount(beforeCount)
    await expect(page.getByText(/Регулярный платёж завершён/)).toBeVisible()
  })
})

test.describe('admin surfaces', () => {
  test('users page lists accounts and protects the bootstrap admin', async ({ page }) => {
    await login(page, ADMIN)
    await goTo(page, 'Пользователи')
    await expect(page.getByRole('heading', { name: 'Пользователи' })).toBeVisible()
    await expect(page.getByTestId('user-row').first()).toBeVisible()
    await expect(page.getByText('Защищён').first()).toBeVisible()
  })

  test('audit log shows real recorded actions', async ({ page }) => {
    await login(page, ADMIN)
    await goTo(page, 'Журнал действий')
    await expect(page.getByRole('heading', { name: 'Журнал действий' })).toBeVisible()
    await expect(page.getByTestId('audit-row').first()).toBeVisible()
  })

  test('budgets page renders per-currency limits', async ({ page }) => {
    await login(page, ADMIN)
    await goTo(page, 'Бюджеты')
    await expect(page.getByRole('heading', { name: 'Бюджеты' })).toBeVisible()
    await expect(page.getByText('Бюджет RUB')).toBeVisible()
    await expect(page.getByText('Бюджет USD')).toBeVisible()
    await expect(page.getByText('Бюджет EUR')).toBeVisible()
  })
})

test.describe('interface states', () => {
  test('empty search results show a helpful state', async ({ page }) => {
    await login(page, ADMIN)
    await page.goto('/payments')
    await page.getByTestId('search-input').fill('zzz-no-such-payment-zzz')
    await expect(page.getByText('Ничего не найдено')).toBeVisible()
    await page.getByRole('button', { name: 'Сбросить фильтры' }).click()
    await expect(page.getByTestId('payment-row').first()).toBeVisible()
    await expect(page.getByText('Ничего не найдено')).toHaveCount(0)
  })

  test('status filter narrows the table', async ({ page }) => {
    await login(page, ADMIN)
    await page.goto('/payments')
    await page.getByTestId('filter-status').selectOption('overdue')
    await expect(page.getByTestId('payment-row').first()).toBeVisible()
    const badges = await page.locator('.badge--overdue').count()
    expect(badges).toBeGreaterThan(0)
  })

  test('mobile viewport has no horizontal overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await login(page, ADMIN)
    await page.goto('/payments')
    await expect(page.getByTestId('payment-row').first()).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(2)
  })

  test('mobile navigation works through the hamburger menu', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await login(page, ADMIN)

    // The sidebar must start closed on a narrow screen.
    const toggle = page.getByRole('button', { name: 'Открыть меню' })
    await expect(toggle).toBeVisible()
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')

    await goTo(page, 'Календарь')
    await expect(page.getByRole('heading', { name: 'Календарь платежей' })).toBeVisible()
    // Navigating closes the drawer again.
    await expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  test('no console errors on the main pages', async ({ page }) => {
    await login(page, ADMIN)

    // Listeners attach after login: the pre-login /auth/me probe legitimately
    // returns 401, and we only want to catch unexpected errors here.
    const errors: string[] = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text())
    })
    page.on('pageerror', (err) => errors.push(`pageerror: ${err.message}`))

    for (const path of ['/', '/payments', '/calendar', '/budgets', '/users', '/audit']) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      await expect(page.locator('.content')).toBeVisible()
    }
    expect(errors).toEqual([])
  })
})
