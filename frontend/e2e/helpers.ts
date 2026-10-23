import { expect, type Page } from '@playwright/test'

export const ADMIN = {
  username: process.env.E2E_ADMIN_USERNAME ?? process.env.ADMIN_USERNAME ?? 'admin',
  password: process.env.E2E_ADMIN_PASSWORD ?? process.env.ADMIN_PASSWORD ?? 'DemoAdmin123!',
}

export const USER = {
  username: process.env.E2E_USER_USERNAME ?? process.env.DEMO_USERNAME ?? 'demo_user',
  password: process.env.E2E_USER_PASSWORD ?? process.env.DEMO_PASSWORD ?? 'DemoUser123!',
}

/** Unique suffix so repeated runs never collide on titles. */
export function uniqueTitle(prefix: string): string {
  return `${prefix} ${Date.now().toString().slice(-7)}`
}

/**
 * Returns the table row for a specific payment.
 *
 * The search box is debounced, so we must never rely on `.first()` right after
 * typing — that would still be the unfiltered first page. Filtering by the
 * unique title makes the row selection deterministic.
 */
export function paymentRow(page: Page, title: string) {
  return page.getByTestId('payment-row').filter({ hasText: title }).first()
}

/** Fills the search box and waits until the matching row is really rendered. */
export async function searchFor(page: Page, title: string) {
  await page.getByTestId('search-input').fill(title)
  await expect(paymentRow(page, title)).toBeVisible()
}

export async function login(page: Page, creds: { username: string; password: string }) {
  await page.goto('/login')
  await page.getByTestId('login-username').fill(creds.username)
  await page.getByTestId('login-password').fill(creds.password)
  await page.getByTestId('login-submit').click()
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible()
}

/**
 * Opens the sidebar on narrow viewports.
 *
 * On mobile the navigation lives behind a hamburger button, so a direct click
 * on a nav link would fail with "element is not visible". This is real product
 * behaviour, so tests must drive it the way a user does.
 */
export async function openSidebarIfNeeded(page: Page) {
  const toggle = page.getByRole('button', { name: 'Открыть меню' })
  if (await toggle.isVisible()) {
    const expanded = await toggle.getAttribute('aria-expanded')
    if (expanded !== 'true') {
      await toggle.click()
      await expect(toggle).toHaveAttribute('aria-expanded', 'true')
    }
  }
}

/** Navigates via the sidebar, handling the mobile hamburger automatically. */
export async function goTo(page: Page, label: string) {
  await openSidebarIfNeeded(page)
  await page.getByRole('link', { name: label, exact: true }).click()
}

export async function logout(page: Page) {
  await openSidebarIfNeeded(page)
  await page.getByTestId('logout-button').click()
  await expect(page).toHaveURL(/\/login/)
}
