export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'

export type ScanStatus = 'queued' | 'running' | 'complete' | 'failed'

export interface DashboardMetric {
  id: string
  label: string
  value: string | number
  detail?: string
  trend?: 'up' | 'down' | 'flat'
  trendLabel?: string
}

export interface ScanSummary {
  id: string
  repository: string
  branch?: string
  status: ScanStatus
  score?: number
  findings?: number
  critical?: number
  duration?: string
  startedAt: string
  completedAt?: string
  commit?: string
  source?: string
  progress?: number
}

export interface RepositorySummary {
  id: string
  name: string
  provider?: string
  branch?: string
  lastScanAt?: string
  score?: number
  status?: ScanStatus
}

export interface DashboardData {
  metrics: DashboardMetric[]
  recentScans: ScanSummary[]
  repositories: RepositorySummary[]
  generatedAt?: string
}

export interface Finding {
  id: string
  severity: Severity
  title: string
  description: string
  file: string
  line?: number
  rule: string
  category: string
  recommendation?: string
  snippet?: string
  status?: 'open' | 'resolved' | 'ignored'
}

export interface ScanReport {
  scan: ScanSummary
  findings: Finding[]
  summary?: {
    score?: number
    filesScanned?: number
    duration?: string
    coverage?: string
  }
}

export interface ComparisonData {
  baseline: ScanSummary
  current: ScanSummary
  scoreDelta?: number
  findingDelta?: number
  resolved: Finding[]
  introduced: Finding[]
  unchanged: Finding[]
}

export interface ImportInput {
  source: 'git' | 'zip'
  url?: string
  file?: File
  branch?: string
}

export interface ApiErrorPayload {
  message: string
  status?: number
}
