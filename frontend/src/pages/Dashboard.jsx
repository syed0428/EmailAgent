import { useState, useEffect } from 'react'
import { getHealthFull } from '../api'

const STATUS_CLASS = {
  ok: 'badge-ok',
  error: 'badge-error',
  skipped: 'badge-skipped',
  degraded: 'badge-warning',
}

function CheckCard({ name, check }) {
  const cls = STATUS_CLASS[check.status] || 'badge-info'
  const details = Object.entries(check)
    .filter(([k]) => k !== 'status')
    .map(([k, v]) => `${k}: ${v}`)
    .join(' · ')

  return (
    <div className="health-check">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span className="check-name">{name}</span>
        <span className={`badge ${cls}`}>{check.status}</span>
      </div>
      {details && <div className="check-detail">{details}</div>}
    </div>
  )
}

export default function Dashboard() {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastChecked, setLastChecked] = useState(null)

  const runCheck = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getHealthFull()
      setHealth(res.data)
      setLastChecked(new Date())
    } catch (e) {
      setError(e.message || 'Backend unreachable')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { runCheck() }, [])

  const overallCls = health
    ? health.overall === 'ok' ? 'badge-ok' : 'badge-warning'
    : 'badge-info'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: '700', marginBottom: '4px' }}>
            System Dashboard
          </h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
            Phase 1 — Stack verification
            {lastChecked && ` · Last checked ${lastChecked.toLocaleTimeString()}`}
          </p>
        </div>
        <button className="btn btn-primary" onClick={runCheck} disabled={loading}>
          {loading ? '⟳ Checking…' : '⟳ Re-check'}
        </button>
      </div>

      {/* Overall status */}
      {health && (
        <div className="card" style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div>
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '4px' }}>Overall Status</div>
            <span className={`badge ${overallCls}`} style={{ fontSize: '14px', padding: '4px 14px' }}>
              {health.overall.toUpperCase()}
            </span>
          </div>
          <div style={{ height: '40px', width: '1px', background: 'var(--border)' }} />
          <div style={{ color: 'var(--text-secondary)', fontSize: '13px' }}>
            {Object.values(health.checks).filter(c => c.status === 'ok').length} /{' '}
            {Object.keys(health.checks).length} subsystems healthy
          </div>
        </div>
      )}

      {/* Gmail OAuth Connection Card */}
      <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <div className="card-title" style={{ marginBottom: '4px' }}>🔑 Gmail OAuth 2.0 Connection</div>
          <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
            Connect your Google account to authorize email operations securely with Fernet token encryption.
          </div>
        </div>
        <button
          className="btn btn-primary"
          onClick={async () => {
            try {
              const res = await (await import('../api')).getGoogleLoginUrl()
              if (res.data && res.data.auth_url) {
                window.location.href = res.data.auth_url
              }
            } catch (err) {
              alert(err.response?.data?.detail || 'Please configure GOOGLE_CLIENT_ID & GOOGLE_CLIENT_SECRET in .env first.')
            }
          }}
        >
          🔐 Connect Gmail Account
        </button>
      </div>

      {error && (
        <div className="card" style={{ borderColor: 'var(--danger)', background: 'rgba(239,68,68,0.05)' }}>
          <div style={{ color: 'var(--danger)', fontWeight: 600 }}>❌ {error}</div>
          <div style={{ color: 'var(--text-muted)', fontSize: '12.5px', marginTop: '6px' }}>
            Make sure the FastAPI backend is running on port 8000.
          </div>
        </div>
      )}

      {loading && !health && <div className="loading">Running health checks…</div>}

      {/* Check grid */}
      {health && (
        <div className="card">
          <div className="card-title">🔍 Subsystem Checks</div>
          <div className="health-grid">
            {Object.entries(health.checks).map(([name, check]) => (
              <CheckCard key={name} name={name} check={check} />
            ))}
          </div>
        </div>
      )}

      {/* Phase roadmap */}
      <div className="card">
        <div className="card-title">🗺 Phase Roadmap</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {[
            ['Phase 1', 'Stack verification', 'current'],
            ['Phase 2', 'Mock email dataset + processing pipeline', 'pending'],
            ['Phase 3', 'AI email classification (Ollama)', 'pending'],
            ['Phase 4', 'Semantic email search (pgvector)', 'pending'],
            ['Phase 5', 'AI cleanup suggestions + user approval', 'pending'],
            ['Phase 6', 'Gmail OAuth 2.0 integration', 'pending'],
            ['Phase 7', 'Real Gmail email ingestion', 'pending'],
            ['Phase 8', 'Job Application Assistant', 'pending'],
            ['Phase 9', 'Gmail email sending with confirmation', 'pending'],
          ].map(([phase, desc, state]) => (
            <div key={phase} style={{
              display: 'flex', alignItems: 'center', gap: '12px',
              padding: '8px 12px', borderRadius: 'var(--radius-sm)',
              background: state === 'current' ? 'var(--accent-dim)' : 'transparent',
            }}>
              <span style={{
                fontSize: '11px', fontWeight: 700, color: state === 'current' ? 'var(--accent-light)' : 'var(--text-muted)',
                width: '60px', flexShrink: 0,
              }}>{phase}</span>
              <span style={{ fontSize: '13px', color: state === 'current' ? 'var(--text-primary)' : 'var(--text-muted)' }}>
                {desc}
              </span>
              {state === 'current' && <span className="badge badge-info" style={{ marginLeft: 'auto' }}>Active</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
