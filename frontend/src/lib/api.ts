import type { ComparisonData, DashboardData, Finding, ImportInput, ScanReport, ScanSummary, Severity } from '../types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/$/, '')

export class ApiUnavailableError extends Error {
  status?: number

  constructor(message = 'The RepoReady API is unavailable.', status?: number) {
    super(message)
    this.name = 'ApiUnavailableError'
    this.status = status
  }
}

export class ApiRequestError extends Error {
  status?: number

  constructor(message: string, status?: number) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiUnavailableError()
  }

  if (!response.ok) {
    if (response.status === 404 || response.status === 502 || response.status === 503 || response.status === 504) {
      throw new ApiUnavailableError(`RepoReady API returned ${response.status}.`, response.status)
    }
    let message = `RepoReady API returned ${response.status}.`
    try {
      const body = await response.json() as { message?: string }
      if (body.message) message = body.message
    } catch {
      // Keep the status-based message when the server does not return JSON.
    }
    throw new ApiRequestError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  return await response.json() as T
}

type BackendScan = Partial<ScanSummary> & {
  source_type?: string
  source_name?: string
  source_url?: string
  created_at?: string
  completed_at?: string
  summary?: Record<string, unknown>
  findings?: unknown[]
  error?: string
}

type BackendFinding = {
  id?: string | number
  code?: string
  category?: string
  severity?: string
  title?: string
  description?: string
  remediation?: string
  evidence?: Array<{ path?: string; detail?: string; line?: number | null }>
}

function normalizeSeverity(value?: string): Severity {
  if (value === 'critical' || value === 'high' || value === 'medium' || value === 'low' || value === 'info') return value
  return 'info'
}

function normalizeFinding(payload: BackendFinding, scanId: string, index: number): Finding {
  const evidence = Array.isArray(payload.evidence) ? payload.evidence : []
  const firstEvidence = evidence[0]
  return {
    id: String(payload.id ?? `${scanId}-${payload.code ?? index}`),
    severity: normalizeSeverity(payload.severity),
    title: payload.title ?? payload.code ?? 'Untitled finding',
    description: payload.description ?? 'No description returned by the scan API.',
    file: firstEvidence?.path ?? 'Repository root',
    line: firstEvidence?.line ?? undefined,
    rule: payload.code ?? 'repo-ready/finding',
    category: payload.category ?? 'General',
    recommendation: payload.remediation,
    snippet: firstEvidence?.detail,
    status: 'open',
  }
}

export function normalizeScan(payload: BackendScan, findings?: BackendFinding[]): ScanSummary {
  const summary = payload.summary ?? {}
  const findingRows = findings ?? (Array.isArray(payload.findings) ? payload.findings as BackendFinding[] : undefined)
  const findingCounts = summary.finding_counts as Record<string, unknown> | undefined
  const totalFindings = findingRows ? findingRows.length : typeof summary.finding_count === 'number' ? summary.finding_count : undefined
  const criticalCount = findingRows?.filter(finding => finding.severity === 'critical').length ?? (typeof findingCounts?.high === 'number' ? findingCounts.high : undefined)
  const status = payload.status === 'running' ? 'running' : payload.status === 'failed' ? 'failed' : payload.status === 'complete' ? 'complete' : 'queued'
  return {
    id: String(payload.id ?? 'unknown-scan'),
    repository: payload.repository ?? payload.source_name ?? payload.source_url ?? 'Repository',
    branch: payload.branch,
    status,
    score: typeof payload.score === 'number' ? payload.score : typeof summary.score === 'number' ? summary.score : undefined,
    findings: totalFindings,
    critical: criticalCount,
    duration: payload.duration,
    startedAt: payload.startedAt ?? payload.created_at ?? new Date().toISOString(),
    completedAt: payload.completedAt ?? payload.completed_at,
    commit: payload.commit,
    source: payload.source ?? payload.source_type,
    progress: payload.progress,
  }
}

function normalizeReport(payload: BackendScan): ScanReport {
  const backendFindings = Array.isArray(payload.findings) ? payload.findings as BackendFinding[] : []
  const scan = normalizeScan(payload, backendFindings)
  const summary = payload.summary ?? {}
  const findingCounts = summary.finding_counts as Record<string, unknown> | undefined
  const filesScanned = typeof summary.file_count === 'number' ? summary.file_count : undefined
  const score = typeof summary.score === 'number' ? summary.score : scan.score
  const findingCount = backendFindings.length || (findingCounts ? Object.values(findingCounts).reduce<number>((total, value) => total + (typeof value === 'number' ? value : 0), 0) : undefined)
  return {
    scan: { ...scan, findings: findingCount },
    findings: backendFindings.map((finding, index) => normalizeFinding(finding, scan.id, index)),
    summary: {
      score,
      filesScanned,
      duration: scan.duration,
      coverage: undefined,
    },
  }
}

function dashboardFromHistory(scans: ScanSummary[]): DashboardData {
  const scored = scans.filter(scan => typeof scan.score === 'number')
  const repositories = Array.from(new Map(scans.map(scan => [scan.repository, {
    id: scan.repository,
    name: scan.repository,
    provider: scan.source,
    branch: scan.branch,
    lastScanAt: scan.completedAt ?? scan.startedAt,
    score: scan.score,
    status: scan.status,
  }])).values())
  const metrics = []
  if (scored.length) {
    const average = Math.round(scored.reduce((total, scan) => total + (scan.score ?? 0), 0) / scored.length)
    metrics.push({ id: 'score', label: 'Average health score', value: `${average}/100`, detail: `${scored.length} scored scan${scored.length === 1 ? '' : 's'}`, trend: 'flat' as const, trendLabel: 'from API' })
  }
  if (scans.length) metrics.push({ id: 'scans', label: 'Total scans', value: scans.length, detail: `${repositories.length} repos in history`, trend: 'flat' as const, trendLabel: 'from API' })
  return { metrics, recentScans: scans.slice(0, 8), repositories: repositories.slice(0, 8), generatedAt: scans[0]?.completedAt ?? scans[0]?.startedAt }
}

function normalizeDashboard(payload: Partial<DashboardData> | null | undefined): DashboardData {
  return {
    metrics: Array.isArray(payload?.metrics) ? payload.metrics : [],
    recentScans: Array.isArray(payload?.recentScans) ? payload.recentScans : [],
    repositories: Array.isArray(payload?.repositories) ? payload.repositories : [],
    generatedAt: payload?.generatedAt,
  }
}

export async function getDashboard(): Promise<DashboardData> {
  try {
    return normalizeDashboard(await request<Partial<DashboardData>>('/dashboard'))
  } catch (error) {
    if (error instanceof ApiUnavailableError && error.status === 404) return dashboardFromHistory(await getHistory())
    throw error
  }
}

export async function getHistory(): Promise<ScanSummary[]> {
  const payload = await request<{ items?: BackendScan[]; scans?: BackendScan[] } | BackendScan[]>('/scans?limit=100')
  const items = Array.isArray(payload) ? payload : (payload.items ?? payload.scans ?? [])
  return items.map(item => normalizeScan(item))
}

export async function importRepository(input: ImportInput): Promise<ScanSummary> {
  if (input.source === 'zip' && input.file) {
    const form = new FormData()
    form.append('file', input.file)
    if (input.branch) form.append('branch', input.branch)
    return normalizeScan(await request<BackendScan>('/scans/upload', { method: 'POST', body: form }))
  }

  return normalizeScan(await request<BackendScan>('/scans/git', {
    method: 'POST',
    body: JSON.stringify({ url: input.url, ref: input.branch }),
  }))
}

export async function getScanStatus(scanId: string): Promise<ScanSummary> {
  const payload = await request<BackendScan>(`/scans/${encodeURIComponent(scanId)}`)
  return normalizeScan(payload, payload.findings as BackendFinding[] | undefined)
}

export async function getScanReport(scanId: string): Promise<ScanReport> {
  return normalizeReport(await request<BackendScan>(`/scans/${encodeURIComponent(scanId)}`))
}

export async function compareScans(baselineId: string, currentId: string): Promise<ComparisonData> {
  const [payload, baselinePayload, currentPayload] = await Promise.all([
    request<Record<string, unknown>>(`/scans/compare?base_id=${encodeURIComponent(baselineId)}&candidate_id=${encodeURIComponent(currentId)}`),
    request<BackendScan>(`/scans/${encodeURIComponent(baselineId)}`),
    request<BackendScan>(`/scans/${encodeURIComponent(currentId)}`),
  ])
  const baseline = normalizeScan(baselinePayload, baselinePayload.findings as BackendFinding[] | undefined)
  const current = normalizeScan(currentPayload, currentPayload.findings as BackendFinding[] | undefined)
  const resolved = Array.isArray(payload.findings_resolved) ? payload.findings_resolved as BackendFinding[] : []
  const introduced = Array.isArray(payload.findings_added) ? payload.findings_added as BackendFinding[] : []
  const unchanged = Array.isArray(payload.findings_unchanged) ? payload.findings_unchanged as BackendFinding[] : []
  const changed = Array.isArray(payload.findings_changed) ? payload.findings_changed as BackendFinding[] : []
  return {
    baseline,
    current,
    scoreDelta: typeof payload.score_delta === 'number' ? payload.score_delta : undefined,
    findingDelta: introduced.length - resolved.length,
    resolved: resolved.map((finding, index) => normalizeFinding(finding, baseline.id, index)),
    introduced: introduced.map((finding, index) => normalizeFinding(finding, current.id, index)),
    unchanged: [...unchanged, ...changed].map((finding, index) => normalizeFinding(finding, current.id, index)),
  }
}

export async function exportScan(scanId: string, format: 'json' | 'markdown' = 'json'): Promise<Blob> {
  const endpoint = format === 'markdown' ? 'markdown' : 'json'
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/scans/${encodeURIComponent(scanId)}/export/${endpoint}`, {
      headers: { Accept: format === 'markdown' ? 'text/markdown' : 'application/json' },
    })
  } catch {
    throw new ApiUnavailableError()
  }
  if (!response.ok) {
    if ([404, 502, 503, 504].includes(response.status)) throw new ApiUnavailableError(undefined, response.status)
    throw new ApiRequestError(`Export failed with status ${response.status}.`, response.status)
  }
  return await response.blob()
}
