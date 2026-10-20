import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../App'

const dashboard = {
  metrics: [{ id: 'score', label: 'Health score', value: '91/100', detail: 'Across 2 repositories', trend: 'up', trendLabel: '+3.2%' }],
  recentScans: [],
  repositories: [],
  generatedAt: '2026-10-20T08:26:00.000Z',
}

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
}

describe('RepoReady workspace', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => undefined)))
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows a loading state while the dashboard request is pending', () => {
    render(<App />)
    expect(screen.getByRole('status', { name: /loading repository overview/i })).toBeInTheDocument()
  })

  it('preserves an empty API response without inventing metrics', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ metrics: [], recentScans: [], repositories: [] })))
    render(<App />)

    expect(await screen.findByText('No workspace metrics yet')).toBeInTheDocument()
    expect(screen.getByText('No scans in history')).toBeInTheDocument()
    expect(screen.getByText('No repositories connected')).toBeInTheDocument()
    expect(screen.queryByText('86/100')).not.toBeInTheDocument()
  })

  it('shows a recoverable error for a failed dashboard response', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ message: 'Database unavailable' }, 500)))
    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable')
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('renders API-provided metrics and connected status on success', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse(dashboard)))
    render(<App />)

    expect(await screen.findByText('91/100')).toBeInTheDocument()
    expect(screen.getByText('API connected')).toBeInTheDocument()
    expect(screen.getByText('No scans in history')).toBeInTheDocument()
  })

  it('opens the repository import flow from the primary CTA', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse(dashboard)))
    render(<App />)

    await screen.findByText('91/100')
    await user.click(screen.getByRole('button', { name: /run a new scan/i }))
    expect(screen.getByRole('heading', { name: /bring a repository into focus/i })).toBeInTheDocument()
    expect(screen.getByLabelText('Repository URL')).toBeInTheDocument()
  })

  it('opens the informational start page without changing live workspace data', async () => {
    const user = userEvent.setup()
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse(dashboard)))
    render(<App />)

    await screen.findByText('91/100')
    await user.click(screen.getByRole('button', { name: /open repoready start page/i }))
    expect(screen.getByRole('heading', { name: /ship the repository you meant to share/i })).toBeInTheDocument()
    expect(screen.getByText('Sample data')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /analyze a repository/i })).toBeInTheDocument()
  })

  it('shows an honest connection error when the API is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))))
    render(<App />)

    expect(await screen.findByRole('alert')).toHaveTextContent('RepoReady API is unavailable')
    expect(screen.queryByText('86/100')).not.toBeInTheDocument()
  })
})
