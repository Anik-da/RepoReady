import { useEffect, useState } from 'react'
import type { CSSProperties, FormEvent, ReactNode } from 'react'
import { ErrorState, EmptyState, LoadingState } from './components/StateViews'
import { Icon, type IconName } from './components/Icon'
import {
  compareScans,
  deleteScan,
  exportScan,
  getDashboard,
  getHistory,
  getScanReport,
  getScanStatus,
  importRepository,
  rerunScan,
} from './lib/api'
import type {
  ComparisonData,
  DashboardData,
  DashboardMetric,
  Finding,
  ImportInput,
  RepositorySummary,
  ScanReport,
  ScanStatus,
  ScanSummary,
  Severity,
} from './types'
import './styles.css'

type View = 'landing' | 'overview' | 'repositories' | 'reports' | 'history' | 'compare'
type QueryState<T> =
  | { status: 'idle'; data?: undefined; error?: undefined }
  | { status: 'loading'; data?: undefined; error?: undefined }
  | { status: 'success'; data: T; error?: undefined }
  | { status: 'error'; data?: undefined; error: string }

interface ActiveScan {
  summary: ScanSummary
  progress: number
  status: ScanStatus
  error?: string
}

const navItems: Array<{ id: View; label: string; icon: IconName; shortcut: string }> = [
  { id: 'overview', label: 'Overview', icon: 'activity', shortcut: '01' },
  { id: 'repositories', label: 'Repositories', icon: 'repo', shortcut: '02' },
  { id: 'reports', label: 'Scan reports', icon: 'shield', shortcut: '03' },
  { id: 'history', label: 'History', icon: 'history', shortcut: '04' },
  { id: 'compare', label: 'Compare', icon: 'compare', shortcut: '05' },
]

const viewMeta: Record<View, { eyebrow: string; title: string; description: string }> = {
  landing: { eyebrow: 'RepoReady / start here', title: 'Know what ships next.', description: 'A deterministic read on whether a repository can be installed, tested, and rebuilt on a clean machine.' },
  overview: { eyebrow: 'Workspace / overview', title: 'Repository health, in one signal.', description: 'See what changed, what needs attention, and where to look next.' },
  repositories: { eyebrow: 'Workspace / repositories', title: 'Bring a repository into focus.', description: 'Connect a Git URL or upload a ZIP. RepoReady keeps the import boundary explicit.' },
  reports: { eyebrow: 'Workspace / scan reports', title: 'Findings with enough context to act.', description: 'Filter by severity, open the exact file, and export a review-ready report.' },
  history: { eyebrow: 'Workspace / history', title: 'Every scan, one timeline.', description: 'Trace score movement across branches, commits, and repositories.' },
  compare: { eyebrow: 'Workspace / compare', title: 'Make change visible.', description: 'Put two scans side by side to see what was resolved and what arrived.' },
}

function formatDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(date)
}

function formatRelative(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const diff = Date.now() - date.getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return formatDate(value)
}

function scoreTone(score?: number) {
  if (score === undefined) return 'neutral'
  if (score >= 90) return 'good'
  if (score >= 70) return 'watch'
  return 'risk'
}

function severityLabel(severity: Severity) {
  return severity.charAt(0).toUpperCase() + severity.slice(1)
}

function statusLabel(status: ScanStatus) {
  return status === 'complete' ? 'Complete' : status.charAt(0).toUpperCase() + status.slice(1)
}

function StatusPill({ status }: { status: ScanStatus }) {
  return <span className={`status-pill status-pill--${status}`}><span className="status-dot" />{statusLabel(status)}</span>
}

function ScoreRing({ score, size = 'md' }: { score?: number; size?: 'sm' | 'md' | 'lg' }) {
  if (score === undefined) return <span className="score-empty">—</span>
  return (
    <span className={`score-ring score-ring--${size} score-ring--${scoreTone(score)}`} style={{ '--score': `${Math.max(0, Math.min(100, score)) * 3.6}deg` } as CSSProperties}>
      <span>{score}</span>
    </span>
  )
}

function AppMark() {
  return <span className="app-mark" aria-hidden="true"><span /><span /><span /></span>
}

function MetricCard({ metric }: { metric: DashboardMetric }) {
  return (
    <article className="metric-card">
      <div className="metric-card__top"><span>{metric.label}</span><Icon name="arrow-up-right" size={15} /></div>
      <strong>{metric.value}</strong>
      <div className="metric-card__foot">
        <span>{metric.detail ?? 'No detail available'}</span>
        {metric.trendLabel ? <span className={`trend trend--${metric.trend ?? 'flat'}`}><Icon name={metric.trend === 'down' ? 'arrow-up-right' : metric.trend === 'up' ? 'arrow-up-right' : 'minus'} size={13} />{metric.trendLabel}</span> : null}
      </div>
    </article>
  )
}

function ScanRow({ scan, onOpen, onExport }: { scan: ScanSummary; onOpen: () => void; onExport: () => void }) {
  return (
    <div className="scan-row">
      <div className="scan-row__identity">
        <div className="repo-avatar"><Icon name={scan.source === 'GitHub' ? 'github' : 'repo'} size={16} /></div>
        <div>
          <button className="text-button text-button--strong" onClick={onOpen}>{scan.repository}</button>
          <span className="subline"><Icon name="git-branch" size={12} />{scan.branch ?? 'default'} <span className="separator">·</span> {scan.commit ?? 'no commit'}</span>
        </div>
      </div>
      <div className="scan-row__score"><ScoreRing score={scan.score} size="sm" /></div>
      <div className="scan-row__findings"><strong>{scan.findings ?? '—'}</strong><span>{scan.critical ? `${scan.critical} critical` : 'findings'}</span></div>
      <div className="scan-row__status"><StatusPill status={scan.status} /><span>{formatRelative(scan.completedAt ?? scan.startedAt)}</span></div>
      <button className="icon-button scan-row__export" onClick={onExport} aria-label={`Export ${scan.repository} scan`}><Icon name="download" size={16} /></button>
      <button className="icon-button scan-row__open" onClick={onOpen} aria-label={`Open ${scan.repository} report`}><Icon name="chevron-right" size={17} /></button>
    </div>
  )
}

function RepositoryRow({ repository, onOpen }: { repository: RepositorySummary; onOpen: () => void }) {
  return (
    <button className="repository-row" onClick={onOpen}>
      <div className="repo-avatar repo-avatar--muted"><Icon name="repo" size={16} /></div>
      <div className="repository-row__name"><strong>{repository.name}</strong><span>{repository.provider ?? 'Connected repository'} <span className="separator">·</span> {repository.branch ?? 'default'}</span></div>
      <div className="repository-row__score"><ScoreRing score={repository.score} size="sm" /></div>
      <div className="repository-row__date">{formatRelative(repository.lastScanAt)}</div>
      <Icon name="chevron-right" size={16} />
    </button>
  )
}

function OverviewPage({ state, onRetry, onRunScan, onOpenReport, onExport }: { state: QueryState<DashboardData>; onRetry: () => void; onRunScan: () => void; onOpenReport: (scan: ScanSummary) => void; onExport: (scan: ScanSummary) => void }) {
  if (state.status !== 'success') return state.status === 'loading' ? <LoadingState label="Loading repository overview" /> : <ErrorState title="Overview unavailable" body={state.status === 'error' ? state.error : 'Overview is waiting for data.'} onRetry={onRetry} />
  const data = state.data
  const hasMetrics = data.metrics.length > 0
  const hasScans = data.recentScans.length > 0
  const hasRepositories = data.repositories.length > 0

  return (
    <>
      <section className="hero-card" aria-labelledby="hero-title">
        <div className="hero-card__copy">
          <span className="eyebrow"><span className="live-dot" />Repository intelligence</span>
          <h2 id="hero-title">A sharper read on<br /><em>what ships next.</em></h2>
          <p>Scan a repository, follow the signal, and move from finding to fix without leaving the thread.</p>
          <div className="hero-card__actions"><button className="button button--primary" onClick={onRunScan}>Run a new scan <Icon name="arrow-up-right" size={16} /></button><span className="hero-note"><Icon name="lock" size={13} />Private by default</span></div>
        </div>
        <div className="hero-card__visual" aria-hidden="true">
          <div className="signal-orbit signal-orbit--one" /><div className="signal-orbit signal-orbit--two" /><div className="signal-orbit signal-orbit--three" />
          <div className="signal-core"><AppMark /><span>signal<br />detected</span></div>
          <span className="visual-label visual-label--top">SCANS / 30D <strong>{hasScans ? data.recentScans.length.toString().padStart(2, '0') : '—'}</strong></span>
          <span className="visual-label visual-label--bottom">LAST PULSE <strong>{data.generatedAt ? formatRelative(data.generatedAt) : '—'}</strong></span>
        </div>
      </section>

      <div className="notice-row">
        <span className="connection-badge"><span className="connection-badge__dot" />API connected</span>
        <span className="notice-copy">{`Updated ${formatRelative(data.generatedAt)}`}</span>
      </div>

      <section className="section-block" aria-labelledby="metrics-heading">
        <SectionHeading label="Workspace pulse" title="At a glance" action={hasMetrics ? <button className="text-button" onClick={onRetry}><Icon name="refresh" size={14} />Refresh</button> : undefined} />
        {hasMetrics ? <div className="metric-grid">{data.metrics.map(metric => <MetricCard key={metric.id} metric={metric} />)}</div> : <EmptyState icon="activity" title="No workspace metrics yet" body="Run your first scan to start building a repository health signal." action={<button className="button button--secondary" onClick={onRunScan}>Import a repository <Icon name="plus" size={15} /></button>} />}
      </section>

      <div className="split-grid">
        <section className="panel section-block" aria-labelledby="recent-heading">
          <SectionHeading label="Latest activity" title="Recent scans" action={hasScans ? <button className="text-button" onClick={() => onOpenReport(data.recentScans[0])}>View reports <Icon name="arrow-up-right" size={14} /></button> : undefined} />
          {hasScans ? <div className="scan-list">{data.recentScans.map(scan => <ScanRow key={scan.id} scan={scan} onOpen={() => onOpenReport(scan)} onExport={() => onExport(scan)} />)}</div> : <EmptyState icon="history" title="No scans in history" body="Your recent scan activity will appear here." action={<button className="button button--secondary" onClick={onRunScan}>Run a scan <Icon name="plus" size={15} /></button>} />}
        </section>
        <section className="panel section-block" aria-labelledby="repos-heading">
          <SectionHeading label="Connected surface" title="Repositories" action={<button className="text-button" onClick={onRunScan}>Add repository <Icon name="plus" size={14} /></button>} />
          {hasRepositories ? <div className="repository-list">{data.repositories.map(repository => <RepositoryRow key={repository.id} repository={repository} onOpen={() => onOpenReport(data.recentScans.find(scan => scan.repository.includes(repository.name)) ?? data.recentScans[0])} />)}</div> : <EmptyState icon="repo" title="No repositories connected" body="Import a Git URL or ZIP to create your first scan surface." action={<button className="button button--secondary" onClick={onRunScan}>Connect repository <Icon name="plus" size={15} /></button>} />}
        </section>
      </div>
    </>
  )
}

function SectionHeading({ label, title, action }: { label: string; title: string; action?: ReactNode }) {
  return <div className="section-heading"><div><span className="section-label">{label}</span><h3>{title}</h3></div>{action ? <div className="section-heading__action">{action}</div> : null}</div>
}

function LandingPage({ onStart, onWorkspace }: { onStart: () => void; onWorkspace: () => void }) {
  return <div className="landing-page"><section className="landing-hero"><div className="landing-hero__copy"><span className="eyebrow"><span className="live-dot" />Repository reproducibility</span><h2>Ship the repository you meant to share.</h2><p>RepoReady checks dependency contracts, configuration, tests, Docker, and documentation before a clean machine finds the gaps.</p><div className="landing-actions"><button className="button button--primary" onClick={onStart}>Analyze a repository <Icon name="arrow-up-right" size={16} /></button><button className="button button--secondary" onClick={onWorkspace}>Open workspace <Icon name="activity" size={16} /></button></div><span className="landing-note"><Icon name="lock" size={13} />Local-first analysis · no external AI service required</span></div><div className="landing-signal" aria-hidden="true"><div className="landing-signal__grid" /><div className="landing-signal__core"><AppMark /><strong>READY?</strong><span>evidence over guesswork</span></div><span className="landing-signal__tag landing-signal__tag--one">LOCKFILES</span><span className="landing-signal__tag landing-signal__tag--two">ENV TEMPLATES</span><span className="landing-signal__tag landing-signal__tag--three">TEST READINESS</span></div></section><section className="landing-section"><div><span className="section-label">How it works</span><h3>One scan. Five signals.</h3></div><div className="landing-steps"><article><span>01</span><strong>Import</strong><p>Upload a ZIP or provide a public HTTPS Git URL. Untrusted contents stay inside bounded temporary workspaces.</p></article><article><span>02</span><strong>Inspect</strong><p>Deterministic rules inspect manifests, environment references, test conventions, Docker instructions, and docs.</p></article><article><span>03</span><strong>Act</strong><p>Open evidence, follow remediation guidance, export the report, and compare the next scan to verify change.</p></article></div></section><section className="landing-sample"><div><span className="section-label">Sample data</span><h3>Reports are built for a fix, not a shrug.</h3><p>This preview is illustrative only. Live scores and findings appear after a real repository scan.</p></div><div className="sample-report"><div><span>HEALTH SCORE</span><strong>86<small>/100</small></strong></div><div><span>OPEN FINDINGS</span><strong>12</strong></div><div className="sample-report__finding"><span className="severity-tag severity-tag--high">High</span><strong>JavaScript lockfile is missing</strong><small>package.json · evidence attached</small></div></div></section></div>
}

function ImportPage({ activeScan, onStart, onOpenReport }: { activeScan?: ActiveScan; onStart: (input: ImportInput) => Promise<void>; onOpenReport: () => void }) {
  const [source, setSource] = useState<'git' | 'zip'>('git')
  const [url, setUrl] = useState('')
  const [branch, setBranch] = useState('main')
  const [file, setFile] = useState<File>()
  const [dragging, setDragging] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const canSubmit = source === 'git' ? url.trim().length > 0 : Boolean(file)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    try {
      await onStart({ source, url: source === 'git' ? url.trim() : undefined, file, branch: branch.trim() || undefined })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="import-layout">
      <section className="import-card panel">
        <div className="import-card__intro"><span className="eyebrow">New scan / import</span><h2>Start with the source.</h2><p>RepoReady reads the repository boundary first, then turns the result into a durable report.</p></div>
        <div className="source-tabs" role="tablist" aria-label="Repository source">
          <button className={source === 'git' ? 'source-tab source-tab--active' : 'source-tab'} onClick={() => setSource('git')} role="tab" aria-selected={source === 'git'}><Icon name="git-branch" size={16} /> Git URL</button>
          <button className={source === 'zip' ? 'source-tab source-tab--active' : 'source-tab'} onClick={() => setSource('zip')} role="tab" aria-selected={source === 'zip'}><Icon name="upload" size={16} /> ZIP upload</button>
        </div>
        <form onSubmit={submit}>
          {source === 'git' ? <div className="form-stack"><label className="field-label" htmlFor="git-url">Repository URL</label><div className="input-shell"><Icon name="link" size={16} /><input id="git-url" value={url} onChange={event => setUrl(event.target.value)} placeholder="https://github.com/org/repository" type="url" autoComplete="url" /><span className="input-hint">HTTPS</span></div><p className="field-help">Public or authenticated URLs supported by the connected API.</p></div> : <div className={`drop-zone ${dragging ? 'drop-zone--dragging' : ''}`} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); setFile(event.dataTransfer.files[0]) }}><input id="zip-file" className="visually-hidden" type="file" accept=".zip,application/zip" onChange={event => setFile(event.target.files?.[0])} /><label htmlFor="zip-file"><span className="drop-zone__icon"><Icon name={file ? 'check' : 'upload'} size={20} /></span><strong>{file ? file.name : 'Drop a ZIP here'}</strong><span>{file ? `${Math.round(file.size / 1024)} KB ready to scan` : 'or choose a file from your computer'}</span></label></div>}
          <div className="form-stack"><label className="field-label" htmlFor="branch">Branch <span>optional</span></label><div className="input-shell"><Icon name="git-branch" size={16} /><input id="branch" value={branch} onChange={event => setBranch(event.target.value)} placeholder="main" /></div></div>
          <button className="button button--primary button--wide" disabled={!canSubmit || submitting} type="submit">{submitting ? <><Icon name="loader" size={16} className="spin" /> Preparing scan…</> : <>Scan repository <Icon name="arrow-up-right" size={16} /></>}</button>
        </form>
        <div className="import-footer"><Icon name="lock" size={14} /><span>Source contents stay within the configured scan boundary.</span></div>
      </section>
      <section className="scan-progress panel" aria-live="polite">
        <div className="progress-head"><div><span className="section-label">Live run</span><h3>{activeScan ? activeScan.summary.repository : 'Waiting for a source'}</h3></div>{activeScan ? <StatusPill status={activeScan.status} /> : <span className="status-pill status-pill--idle"><span className="status-dot" />Idle</span>}</div>
        {activeScan ? <><div className="progress-number"><strong>{activeScan.progress}%</strong><span>{activeScan.status === 'complete' ? 'Report ready' : activeScan.status === 'failed' ? 'Scan needs attention' : 'Analyzing repository surface'}</span></div><div className="progress-track"><span style={{ width: `${activeScan.progress}%` }} /></div><div className="progress-meta"><span>{activeScan.summary.branch ?? 'default branch'}</span><span>{activeScan.summary.commit ? `commit ${activeScan.summary.commit}` : 'commit pending'}</span></div>{activeScan.error ? <p className="inline-error">{activeScan.error}</p> : null}{activeScan.status === 'complete' ? <button className="button button--secondary button--wide" onClick={onOpenReport}>Open scan report <Icon name="arrow-up-right" size={16} /></button> : null}</> : <EmptyState icon="activity" title="Your scan will appear here" body="Import a repository to watch the scan move from queued to report-ready." />}
      </section>
    </div>
  )
}

function ReportsPage({ scan, onExport, onRunScan }: { scan?: ScanSummary; onExport: (format: 'json' | 'markdown') => void; onRunScan: () => void }) {
  const [reportState, setReportState] = useState<QueryState<ScanReport>>({ status: 'loading' })
  const [severity, setSeverity] = useState<'all' | Severity>('all')
  const [query, setQuery] = useState('')
  const [selectedFinding, setSelectedFinding] = useState<string>()
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    if (!scan) {
      setReportState({ status: 'idle' })
      return
    }
    setReportState({ status: 'loading' })
    getScanReport(scan.id).then(report => {
      if (!cancelled) setReportState({ status: 'success', data: report })
    }).catch(error => {
      if (cancelled) return
      setReportState({ status: 'error', error: error instanceof Error ? error.message : 'Unable to load this report.' })
    })
    return () => { cancelled = true }
  }, [scan, reloadKey])

  if (!scan) return <EmptyState icon="file" title="No scan selected" body="Run a repository scan before opening a report." action={<button className="button button--secondary" onClick={onRunScan}>Start a scan <Icon name="plus" size={15} /></button>} />
  if (reportState.status !== 'success') return reportState.status === 'loading' ? <LoadingState label="Loading scan report" /> : <ErrorState title="Report unavailable" body={reportState.status === 'error' ? reportState.error : 'Report is waiting for data.'} onRetry={() => setReloadKey(key => key + 1)} />
  const report = reportState.data
  const availableSeverities = Array.from(new Set(report.findings.map(finding => finding.severity)))
  const filteredFindings = report.findings.filter(finding => {
    const matchesSeverity = severity === 'all' || finding.severity === severity
    const searchable = `${finding.title} ${finding.file} ${finding.rule} ${finding.category}`.toLowerCase()
    return matchesSeverity && searchable.includes(query.toLowerCase())
  })
  const activeFinding = report.findings.find(finding => finding.id === selectedFinding) ?? filteredFindings[0]
  const counts = report.findings.reduce<Record<string, number>>((acc, finding) => { acc[finding.severity] = (acc[finding.severity] ?? 0) + 1; return acc }, {})

  return (
    <>
      <div className="report-toolbar panel"><div className="report-toolbar__scan"><div className="repo-avatar"><Icon name="repo" size={16} /></div><div><span className="section-label">Report for</span><strong>{report.scan.repository}</strong><span className="subline"><Icon name="git-branch" size={12} />{report.scan.branch ?? 'default'} <span className="separator">·</span> {report.scan.commit ?? 'no commit'}</span></div></div><div className="report-toolbar__actions"><button className="button button--secondary" onClick={() => onExport('json')}><Icon name="download" size={15} /> JSON</button><button className="button button--secondary" onClick={() => onExport('markdown')}><Icon name="download" size={15} /> Markdown</button></div></div>
      <div className="report-summary-grid"><div className="summary-card summary-card--score"><span className="section-label">Health score</span><div className="summary-card__score"><ScoreRing score={report.summary?.score ?? report.scan.score} size="lg" /><div><strong>{report.summary?.score ?? report.scan.score ?? '—'}<small>/100</small></strong><span>{report.summary?.score && report.summary.score >= 90 ? 'Healthy surface' : 'Needs a closer look'}</span></div></div></div><SummaryValue label="Files scanned" value={report.summary?.filesScanned?.toString() ?? '—'} icon="file" /><SummaryValue label="Checks passed" value={report.summary?.checks ? `${report.summary.checks.passed}` : '—'} icon="check" /><SummaryValue label="Not run" value={report.summary?.checks ? `${report.summary.checks.notRun}` : '—'} icon="clock" /></div>
      <section className="report-meta-grid"><div className="report-check-card"><span className="section-label">Severity breakdown</span><div className="report-counts"><span className="report-count report-count--critical"><strong>{counts.critical ?? 0}</strong><small>Critical</small></span><span className="report-count report-count--high"><strong>{counts.high ?? 0}</strong><small>High</small></span><span className="report-count report-count--medium"><strong>{counts.medium ?? 0}</strong><small>Medium</small></span><span className="report-count report-count--low"><strong>{counts.low ?? 0}</strong><small>Low</small></span></div></div><div className="report-check-card"><span className="section-label">Execution status</span><p>Tests: <strong>{report.summary?.execution?.tests ?? 'not_run'}</strong></p><p>Docker build: <strong>{report.summary?.execution?.dockerBuild ?? 'not_run'}</strong></p></div><div className="report-check-card"><span className="section-label">Limitations</span><ul>{(report.summary?.limitations ?? ['Static checks only; review heuristics before making release decisions.']).map(limitation => <li key={limitation}>{limitation}</li>)}</ul></div></section>
      <section className="findings-shell panel" aria-labelledby="findings-heading"><div className="findings-head"><div><span className="section-label">Review queue</span><h3 id="findings-heading">Findings <span>{report.findings.length}</span></h3></div><div className="findings-head__tools"><div className="search-shell"><Icon name="search" size={15} /><input aria-label="Search findings" placeholder="Search findings" value={query} onChange={event => setQuery(event.target.value)} /></div><button className="filter-button" aria-label="Clear finding filters" onClick={() => { setSeverity('all'); setQuery('') }}><Icon name="filter" size={16} />Clear</button></div></div><div className="severity-tabs" role="tablist" aria-label="Filter findings by severity"><button className={severity === 'all' ? 'severity-tab severity-tab--active' : 'severity-tab'} onClick={() => setSeverity('all')} role="tab" aria-selected={severity === 'all'}>All <span>{report.findings.length}</span></button>{(['critical', 'high', 'medium', 'low'] as Severity[]).filter(level => availableSeverities.includes(level)).map(level => <button key={level} className={`severity-tab severity-tab--${level} ${severity === level ? 'severity-tab--active' : ''}`} onClick={() => setSeverity(level)} role="tab" aria-selected={severity === level}>{severityLabel(level)} <span>{counts[level]}</span></button>)}</div>{report.findings.length === 0 ? <EmptyState icon="shield" title="No findings returned" body="The API returned a report with no findings. RepoReady keeps that result intact." action={<button className="button button--secondary" onClick={onRunScan}>Run another scan <Icon name="plus" size={15} /></button>} /> : <div className="findings-grid"><div className="finding-list">{filteredFindings.length ? filteredFindings.map(finding => <FindingRow key={finding.id} finding={finding} active={activeFinding?.id === finding.id} onClick={() => setSelectedFinding(finding.id)} />) : <EmptyState icon="search" title="No findings match" body="Try a different severity or search term." />}</div><FindingDetail finding={activeFinding} /></div>}</section>
      <div className="report-footnote"><Icon name="spark" size={14} /><span>Finding details are sourced from the connected scan API.</span></div>
    </>
  )
}

function SummaryValue({ label, value, icon }: { label: string; value: string; icon: IconName }) {
  return <div className="summary-card"><span className="summary-card__icon"><Icon name={icon} size={17} /></span><span className="section-label">{label}</span><strong>{value}</strong><span className="summary-card__muted">From this scan</span></div>
}

function FindingRow({ finding, active, onClick }: { finding: Finding; active: boolean; onClick: () => void }) {
  return <button className={`finding-row ${active ? 'finding-row--active' : ''}`} onClick={onClick}><span className={`severity-marker severity-marker--${finding.severity}`} /><span className="finding-row__copy"><strong>{finding.title}</strong><span>{finding.file}{finding.line ? `:${finding.line}` : ''} <span className="separator">·</span> {finding.rule}</span></span><span className={`severity-tag severity-tag--${finding.severity}`}>{severityLabel(finding.severity)}</span><Icon name="chevron-right" size={16} /></button>
}

function FindingDetail({ finding }: { finding?: Finding }) {
  if (!finding) return <EmptyState icon="file" title="Select a finding" body="Choose a finding to inspect its context and recommendation." />
  return <aside className="finding-detail"><div className="finding-detail__top"><span className={`severity-tag severity-tag--${finding.severity}`}>{severityLabel(finding.severity)}</span><span className="finding-detail__id">{finding.id}</span></div><h3>{finding.title}</h3><p>{finding.description}</p><div className="detail-location"><Icon name="file" size={15} /><span>{finding.file}</span>{finding.line ? <span className="line-number">Line {finding.line}</span> : null}</div>{finding.snippet ? <pre><code>{finding.snippet}</code></pre> : null}<div className="recommendation"><span className="recommendation__icon"><Icon name="spark" size={15} /></span><div><span className="section-label">Suggested next step</span><p>{finding.recommendation ?? 'Review this finding against your repository conventions.'}</p></div></div><div className="detail-meta"><span><strong>Rule</strong>{finding.rule}</span><span><strong>Category</strong>{finding.category}</span></div></aside>
}

function HistoryPage({ state, onRetry, onOpen, onDelete, onRerun }: { state: QueryState<ScanSummary[]>; onRetry: () => void; onOpen: (scan: ScanSummary) => void; onDelete: (scan: ScanSummary) => void; onRerun: (scan: ScanSummary) => void }) {
  if (state.status !== 'success') return state.status === 'loading' ? <LoadingState label="Loading scan history" /> : <ErrorState title="History unavailable" body={state.status === 'error' ? state.error : 'History is waiting for data.'} onRetry={onRetry} />
  const scans = state.data
  return <section className="panel history-panel"><div className="history-heading"><div><span className="section-label">Audit trail</span><h3>Scan history <span>{scans.length}</span></h3></div><div className="history-heading__meta"><span className="connection-badge"><span className="connection-badge__dot" />Live history</span></div></div>{scans.length ? <div className="history-table"><div className="history-table__head"><span>Repository</span><span>Commit</span><span>Score</span><span>Findings</span><span>Status</span><span>Run date</span><span>Actions</span></div>{scans.map(scan => <div key={scan.id} className="history-table__row"><button className="history-row-main" onClick={() => onOpen(scan)}><span className="history-repo"><span className="repo-avatar repo-avatar--muted"><Icon name="repo" size={15} /></span><strong>{scan.repository}</strong></span><span className="mono">{scan.commit ?? '—'}</span><span><ScoreRing score={scan.score} size="sm" /></span><span>{scan.findings ?? '—'} <small>{scan.critical ? `· ${scan.critical} critical` : ''}</small></span><span><StatusPill status={scan.status} /></span><span>{formatDate(scan.completedAt ?? scan.startedAt)}</span><span><Icon name="chevron-right" size={16} /></span></button><span className="history-row-actions">{scan.source?.toLowerCase() === 'git' ? <button className="icon-button" aria-label={`Rerun ${scan.repository}`} onClick={() => onRerun(scan)}><Icon name="refresh" size={15} /></button> : null}<button className="icon-button icon-button--danger" aria-label={`Delete ${scan.repository} scan`} onClick={() => onDelete(scan)}><Icon name="x" size={15} /></button></span></div>)}</div> : <EmptyState icon="history" title="No scan history" body="Completed and failed scans will collect here once the API returns them." />}</section>
}

function ComparePage({ history }: { history: ScanSummary[] }) {
  const [baselineId, setBaselineId] = useState(history[1]?.id ?? history[0]?.id ?? '')
  const [currentId, setCurrentId] = useState(history[0]?.id ?? '')
  const [state, setState] = useState<QueryState<ComparisonData>>({ status: 'idle' })

  useEffect(() => {
    if (history.length) {
      setBaselineId(current => history.some(scan => scan.id === current) ? current : history[1]?.id ?? history[0].id)
      setCurrentId(current => history.some(scan => scan.id === current) ? current : history[0].id)
    }
  }, [history])

  const runCompare = async (event: FormEvent) => {
    event.preventDefault()
    if (!baselineId || !currentId || baselineId === currentId) return
    setState({ status: 'loading' })
    try {
      setState({ status: 'success', data: await compareScans(baselineId, currentId) })
    } catch (error) {
      setState({ status: 'error', error: error instanceof Error ? error.message : 'Unable to compare scans.' })
    }
  }

  if (history.length < 2) return <EmptyState icon="compare" title="Nothing to compare yet" body="Run at least two scans to see what changed between repository states." />
  if (state.status === 'loading') return <LoadingState label="Building comparison" />
  if (state.status === 'error') return <ErrorState title="Comparison unavailable" body={state.error} />
  return <>
    <form className="compare-picker panel" onSubmit={runCompare}><div className="compare-picker__intro"><span className="section-label">Diff the signal</span><h3>Choose two scans</h3></div><div className="select-group"><label htmlFor="baseline">Baseline</label><div className="select-shell"><Icon name="history" size={15} /><select id="baseline" value={baselineId} onChange={event => setBaselineId(event.target.value)}>{history.map(scan => <option key={scan.id} value={scan.id}>{scan.repository} · {formatDate(scan.completedAt ?? scan.startedAt)}</option>)}</select><Icon name="chevron-down" size={15} /></div></div><div className="compare-arrow"><Icon name="compare" size={18} /></div><div className="select-group"><label htmlFor="current">Current</label><div className="select-shell"><Icon name="activity" size={15} /><select id="current" value={currentId} onChange={event => setCurrentId(event.target.value)}>{history.map(scan => <option key={scan.id} value={scan.id}>{scan.repository} · {formatDate(scan.completedAt ?? scan.startedAt)}</option>)}</select><Icon name="chevron-down" size={15} /></div></div><button className="button button--primary" disabled={baselineId === currentId} type="submit">Compare <Icon name="arrow-up-right" size={16} /></button></form>
    {state.status === 'success' ? <ComparisonResult state={state} /> : <EmptyState icon="compare" title="Ready to compare" body="Choose two different scans, then compare the repository signal." />}
  </>
}

function ComparisonResult({ state }: { state: Extract<QueryState<ComparisonData>, { status: 'success' }> }) {
  const comparison = state.data
  return <><div className="compare-banner"><div><span className="section-label">Comparing</span><strong>{comparison.baseline.repository}</strong><span>{comparison.baseline.commit ?? 'baseline'} <Icon name="arrow-up-right" size={13} /> {comparison.current.commit ?? 'current'}</span></div><span className="connection-badge"><span className="connection-badge__dot" />Live comparison</span></div><div className="comparison-summary"><div className="comparison-score"><span className="section-label">Health movement</span><div><ScoreRing score={comparison.baseline.score} size="md" /><Icon name="arrow-up-right" size={17} /><ScoreRing score={comparison.current.score} size="md" /></div><strong className={comparison.scoreDelta !== undefined && comparison.scoreDelta >= 0 ? 'delta-positive' : 'delta-negative'}>{comparison.scoreDelta === undefined ? '—' : `${comparison.scoreDelta > 0 ? '+' : ''}${comparison.scoreDelta} pts`}</strong></div><div className="delta-card"><span className="section-label">Finding movement</span><strong>{comparison.findingDelta === undefined ? '—' : `${comparison.findingDelta > 0 ? '+' : ''}${comparison.findingDelta}`}</strong><span>{comparison.findingDelta && comparison.findingDelta > 0 ? 'more findings in current' : 'fewer findings in current'}</span></div><div className="delta-card"><span className="section-label">Resolved</span><strong className="delta-positive">{comparison.resolved.length}</strong><span>findings closed</span></div><div className="delta-card"><span className="section-label">Introduced</span><strong className="delta-negative">{comparison.introduced.length}</strong><span>new findings</span></div></div><div className="comparison-columns"><ComparisonColumn title="Resolved" tone="positive" findings={comparison.resolved} /><ComparisonColumn title="Introduced" tone="negative" findings={comparison.introduced} /><ComparisonColumn title="Unchanged" tone="neutral" findings={comparison.unchanged} /></div></>
}

function ComparisonColumn({ title, tone, findings }: { title: string; tone: 'positive' | 'negative' | 'neutral'; findings: Finding[] }) {
  return <section className="comparison-column panel"><div className="comparison-column__head"><h3>{title}</h3><span className={`count-badge count-badge--${tone}`}>{findings.length}</span></div>{findings.length ? <div className="comparison-finding-list">{findings.map(finding => <div className="comparison-finding" key={finding.id}><span className={`severity-marker severity-marker--${finding.severity}`} /><div><strong>{finding.title}</strong><span>{finding.file}</span></div></div>)}</div> : <p className="muted-copy">No findings in this group.</p>}</section>
}

export default function App() {
  const [view, setView] = useState<View>('overview')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [dashboardState, setDashboardState] = useState<QueryState<DashboardData>>({ status: 'loading' })
  const [historyState, setHistoryState] = useState<QueryState<ScanSummary[]>>({ status: 'loading' })
  const [selectedScan, setSelectedScan] = useState<ScanSummary>()
  const [activeScan, setActiveScan] = useState<ActiveScan>()
  const [toast, setToast] = useState<string>()

  const loadDashboard = async () => {
    setDashboardState({ status: 'loading' })
    try {
      const data = await getDashboard()
      setDashboardState({ status: 'success', data })
      if (!selectedScan && data.recentScans.length) setSelectedScan(data.recentScans[0])
    } catch (error) {
      setDashboardState({ status: 'error', error: error instanceof Error ? error.message : 'Unable to load the repository overview.' })
    }
  }

  const loadHistory = async () => {
    setHistoryState({ status: 'loading' })
    try {
      setHistoryState({ status: 'success', data: await getHistory() })
    } catch (error) {
      setHistoryState({ status: 'error', error: error instanceof Error ? error.message : 'Unable to load scan history.' })
    }
  }

  useEffect(() => { void loadDashboard() }, [])
  useEffect(() => { if (view === 'history' || view === 'compare') void loadHistory() }, [view])

  const openReport = (scan?: ScanSummary) => {
    if (scan) setSelectedScan(scan)
    setView('reports')
    setMobileNavOpen(false)
  }

  const watchRemoteScan = async (summary: ScanSummary) => {
    let latest = summary
    const attempts = 8
    for (let attempt = 0; attempt < attempts && latest.status !== 'complete' && latest.status !== 'failed'; attempt += 1) {
      setActiveScan({ summary: latest, progress: latest.progress ?? Math.min(88, 16 + attempt * 10), status: latest.status })
      await new Promise(resolve => window.setTimeout(resolve, 900))
      latest = await getScanStatus(summary.id)
    }
    const progress = latest.status === 'complete' ? 100 : latest.progress ?? 92
    setActiveScan({ summary: latest, progress, status: latest.status })
    setSelectedScan(latest)
    if (latest.status === 'complete') void loadDashboard()
  }

  const startScan = async (input: ImportInput) => {
    const label = input.source === 'git' ? input.url?.replace(/^https?:\/\//, '').replace(/\.git$/, '') : input.file?.name ?? 'ZIP repository'
    const pending: ScanSummary = { id: `pending-${Date.now()}`, repository: label || 'Imported repository', branch: input.branch ?? 'main', status: 'queued', startedAt: new Date().toISOString(), source: input.source === 'git' ? 'Git URL' : 'ZIP upload', progress: 4 }
    setActiveScan({ summary: pending, progress: 4, status: 'queued' })
    try {
      const scan = await importRepository(input)
      setSelectedScan(scan)
      if (scan.status === 'complete') setActiveScan({ summary: scan, progress: 100, status: 'complete' })
      else await watchRemoteScan(scan)
    } catch (error) {
      setActiveScan({ summary: pending, progress: 4, status: 'failed', error: error instanceof Error ? error.message : 'Unable to start this scan.' })
    }
  }

  const download = (blob: Blob, fileName: string) => {
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = fileName
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  const handleExport = async (scan: ScanSummary, format: 'json' | 'markdown' = 'json') => {
    try {
      const blob = await exportScan(scan.id, format)
      download(blob, `${scan.repository.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}-${scan.id}.${format}`)
      setToast(`Exported ${format.toUpperCase()} report`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'Export failed')
      window.setTimeout(() => setToast(undefined), 3200)
    }
  }

  const handleDelete = async (scan: ScanSummary) => {
    if (!window.confirm(`Delete the saved scan for ${scan.repository}?`)) return
    try {
      await deleteScan(scan.id)
      if (selectedScan?.id === scan.id) setSelectedScan(undefined)
      await Promise.all([loadHistory(), loadDashboard()])
      setToast('Saved scan deleted')
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'Unable to delete this scan')
    }
    window.setTimeout(() => setToast(undefined), 3200)
  }

  const handleRerun = async (scan: ScanSummary) => {
    setActiveScan({ summary: { ...scan, status: 'queued', progress: 4 }, progress: 4, status: 'queued' })
    try {
      const rerun = await rerunScan(scan.id)
      setSelectedScan(rerun)
      setActiveScan({ summary: rerun, progress: rerun.status === 'complete' ? 100 : rerun.progress ?? 0, status: rerun.status })
      setView('reports')
      await Promise.all([loadHistory(), loadDashboard()])
    } catch (error) {
      setActiveScan({ summary: scan, progress: 4, status: 'failed', error: error instanceof Error ? error.message : 'Unable to rerun this scan.' })
    }
  }

  const currentMeta = viewMeta[view]
  const history = historyState.status === 'success' ? historyState.data : []
  const reportScan = selectedScan ?? (dashboardState.status === 'success' ? dashboardState.data.recentScans[0] : undefined)

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <aside className={`sidebar ${mobileNavOpen ? 'sidebar--open' : ''}`}>
        <button className="brand brand-button" onClick={() => { setView('landing'); setMobileNavOpen(false) }} aria-label="Open RepoReady start page"><AppMark /><span className="brand-wordmark">Repo<span>Ready</span></span><span className="brand-version">BETA</span></button>
        <div className="workspace-switcher"><span className="workspace-avatar">A</span><span><strong>Acme engineering</strong><small>Personal workspace</small></span><Icon name="chevron-down" size={15} /></div>
        <nav className="primary-nav" aria-label="Primary navigation">{navItems.map(item => <button key={item.id} className={`nav-item ${view === item.id ? 'nav-item--active' : ''}`} onClick={() => { setView(item.id); setMobileNavOpen(false) }}><Icon name={item.icon} size={17} /><span>{item.label}</span><kbd>{item.shortcut}</kbd></button>)}</nav>
        <div className="sidebar-section"><span className="sidebar-section__label">Workspace</span><button className="sidebar-link" onClick={() => { setView('repositories'); setMobileNavOpen(false) }}><Icon name="plus" size={15} />Add repository</button><button className="sidebar-link" onClick={() => setToast('Keyboard shortcuts are coming soon.')}><Icon name="terminal" size={15} />Command palette <kbd>⌘K</kbd></button></div>
        <div className="sidebar-bottom"><div className="api-status"><span className="api-status__dot" /><div><strong>API status</strong><span>{dashboardState.status === 'error' ? 'Unavailable' : dashboardState.status === 'loading' ? 'Checking…' : 'Connected'}</span></div><button className="icon-button" aria-label="Refresh API status" onClick={() => void loadDashboard()}><Icon name="refresh" size={15} /></button></div><button className="sidebar-link" onClick={() => setToast('Settings are managed through the API environment.') }><Icon name="settings" size={15} />Settings</button><button className="profile-row" onClick={() => setToast('Profile management is not enabled in this local workspace.') }><span className="profile-avatar">AK</span><span><strong>Alex Kim</strong><small>Developer</small></span><Icon name="chevron-right" size={15} /></button></div>
      </aside>
      {mobileNavOpen ? <button className="sidebar-overlay" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} /> : null}
      <div className="main-shell">
        <header className="topbar"><button className="mobile-menu icon-button" aria-label="Open navigation" onClick={() => setMobileNavOpen(true)}><Icon name="menu" size={20} /></button><div className="breadcrumbs"><button className="breadcrumbs-home" onClick={() => setView('landing')}>RepoReady</button><Icon name="chevron-right" size={14} /><strong>{currentMeta.eyebrow.split(' / ')[1]}</strong></div><div className="topbar-actions"><span className="topbar-env"><span className="live-dot" />Development</span><button className="icon-button" aria-label="Notifications" onClick={() => setToast('No new notifications')}><Icon name="bell" size={17} /></button><button className="avatar-button" aria-label="Open profile" onClick={() => setToast('Profile management is not enabled in this local workspace.')}>AK</button></div></header>
        <main id="main-content" className="main-content">{view !== 'landing' ? <div className="page-heading"><div><span className="eyebrow">{currentMeta.eyebrow}</span><h1>{currentMeta.title}</h1><p>{currentMeta.description}</p></div>{view === 'overview' || view === 'reports' ? <button className="button button--primary page-heading__cta" onClick={() => setView('repositories')}><Icon name="plus" size={16} /> New scan</button> : null}</div> : null}
          {view === 'landing' ? <LandingPage onStart={() => setView('repositories')} onWorkspace={() => setView('overview')} /> : null}
          {view === 'overview' ? <OverviewPage state={dashboardState} onRetry={() => void loadDashboard()} onRunScan={() => setView('repositories')} onOpenReport={openReport} onExport={scan => void handleExport(scan)} /> : null}
          {view === 'repositories' ? <ImportPage activeScan={activeScan} onStart={startScan} onOpenReport={() => openReport(activeScan?.summary ?? selectedScan)} /> : null}
          {view === 'reports' ? <ReportsPage scan={reportScan} onExport={format => { if (reportScan) void handleExport(reportScan, format) }} onRunScan={() => setView('repositories')} /> : null}
          {view === 'history' ? <HistoryPage state={historyState} onRetry={() => void loadHistory()} onOpen={openReport} onDelete={scan => void handleDelete(scan)} onRerun={scan => void handleRerun(scan)} /> : null}
          {view === 'compare' ? <ComparePage history={history} /> : null}
        </main>
        <footer className="app-footer"><button className="footer-link" onClick={() => setView('landing')}>RepoReady <span className="separator">·</span> repository intelligence for teams that ship.</button><span><Icon name="shield" size={13} /> Workspace data stays scoped to your API.</span></footer>
      </div>
      {toast ? <div className="toast" role="status"><Icon name="check" size={15} />{toast}<button className="icon-button" onClick={() => setToast(undefined)} aria-label="Dismiss notification"><Icon name="x" size={14} /></button></div> : null}
    </div>
  )
}
