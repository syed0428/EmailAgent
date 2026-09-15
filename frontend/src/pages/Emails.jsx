import { useState, useEffect, useCallback } from 'react'
import { listEmails, semanticSearch, syncGmailEmails, getGoogleAuthStatus, getGoogleLoginUrl } from '../api'

const CATEGORIES = ['', 'job', 'newsletter', 'promotional', 'personal', 'finance', 'notification', 'spam', 'other']
const IMPORTANCE  = ['', 'high', 'medium', 'low']

function avatar(sender = '') {
  const name = sender.replace(/<.*>/, '').trim()
  return name ? name[0].toUpperCase() : '?'
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diffDays = (now - d) / 86400000
  if (diffDays < 1) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  if (diffDays < 7) return d.toLocaleDateString([], { weekday: 'short' })
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export default function Emails() {
  const [authInfo, setAuthInfo]     = useState({ connected: false, gmail_address: null })
  const [emails, setEmails]         = useState([])
  const [total, setTotal]           = useState(0)
  const [loading, setLoading]       = useState(false)
  const [syncing, setSyncing]       = useState(false)
  const [syncMsg, setSyncMsg]       = useState(null)
  const [searchQ, setSearchQ]       = useState('')
  const [searchMode, setSearchMode] = useState(false)
  const [category, setCategory]     = useState('')
  const [importance, setImportance] = useState('')
  const [selected, setSelected]     = useState(null)

  const checkAuth = async () => {
    try {
      const res = await getGoogleAuthStatus()
      if (res.data) {
        setAuthInfo(res.data)
      }
    } catch {
      setAuthInfo({ connected: false, gmail_address: null })
    }
  }

  const fetchEmails = useCallback(async () => {
    setLoading(true)
    try {
      const params = {}
      if (category)   params.category   = category
      if (importance) params.importance  = importance
      const res = await listEmails(params)
      setEmails(res.data.emails)
      setTotal(res.data.total)
      setSearchMode(false)
    } catch {
      setEmails([])
    } finally {
      setLoading(false)
    }
  }, [category, importance])

  const handleSync = async () => {
    setSyncing(true)
    setSyncMsg(null)
    try {
      const res = await syncGmailEmails(15)
      const data = res.data
      setSyncMsg(`Synced ${data.synced_count} new emails from ${data.gmail_address} (${data.skipped_count} skipped as duplicates)`)
      await fetchEmails()
    } catch (err) {
      setSyncMsg(`❌ Sync failed: ${err.response?.data?.detail || err.message}`)
    } finally {
      setSyncing(false)
    }
  }

  const handleConnectGmail = async () => {
    try {
      const res = await getGoogleLoginUrl()
      if (res.data?.auth_url) {
        window.location.href = res.data.auth_url
      }
    } catch (err) {
      alert(err.response?.data?.detail || 'Please configure GOOGLE_CLIENT_ID & GOOGLE_CLIENT_SECRET in .env first.')
    }
  }

  const runSearch = async () => {
    if (!searchQ.trim()) return fetchEmails()
    setLoading(true)
    try {
      const res = await semanticSearch(searchQ)
      setEmails(res.data.results.map(r => ({
        id: r.email_id,
        subject: r.subject,
        sender: r.sender,
        snippet: r.snippet,
        received_at: r.received_at,
        analysis: { category: r.category, importance: r.importance, summary: r.summary },
        _similarity: r.similarity,
      })))
      setTotal(res.data.results.length)
      setSearchMode(true)
    } catch {
      setEmails([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    checkAuth()
    fetchEmails()
  }, [fetchEmails])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '4px' }}>Emails</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
            {!authInfo.connected
              ? 'No Gmail account connected'
              : searchMode
              ? `Semantic search results for "${searchQ}"`
              : `${total} emails stored for ${authInfo.gmail_address || 'connected account'}`}
          </p>
        </div>
        {authInfo.connected && (
          <button className="btn btn-primary" onClick={handleSync} disabled={syncing || loading}>
            {syncing ? '📥 Syncing Gmail…' : '📥 Sync Gmail Inbox'}
          </button>
        )}
      </div>

      {!authInfo.connected && (
        <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
          <div style={{ fontSize: '32px', marginBottom: '12px' }}>🔑</div>
          <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '8px' }}>No Gmail Account Connected</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '13px', maxWidth: '420px', margin: '0 auto 20px auto' }}>
            Connect your Google account from the Dashboard to start managing and syncing your real Gmail inbox.
          </p>
          <button className="btn btn-primary" onClick={handleConnectGmail}>
            🔐 Connect Gmail Account
          </button>
        </div>
      )}

      {syncMsg && (
        <div className="card" style={{
          padding: '12px 16px',
          background: syncMsg.startsWith('❌') ? 'rgba(239,68,68,0.1)' : 'var(--accent-dim)',
          borderColor: syncMsg.startsWith('❌') ? 'var(--danger)' : 'var(--accent-light)',
          fontSize: '13px',
        }}>
          {syncMsg}
        </div>
      )}

      {/* Search + filters */}
      <div className="card" style={{ padding: '16px 20px' }}>
        <div className="search-bar" style={{ marginBottom: '12px' }}>
          <input
            className="input"
            placeholder="Semantic search — e.g. 'AI engineer interview'"
            value={searchQ}
            onChange={e => setSearchQ(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && runSearch()}
          />
          <button className="btn btn-primary" onClick={runSearch} disabled={loading}>
            🔍 Search
          </button>
          {searchMode && (
            <button className="btn btn-ghost btn-sm" onClick={() => { setSearchQ(''); fetchEmails() }}>
              Clear
            </button>
          )}
        </div>
        <div style={{ display: 'flex', gap: '10px' }}>
          <select className="select" style={{ width: 'auto' }}
            value={category} onChange={e => setCategory(e.target.value)}>
            {CATEGORIES.map(c => <option key={c} value={c}>{c || 'All categories'}</option>)}
          </select>
          <select className="select" style={{ width: 'auto' }}
            value={importance} onChange={e => setImportance(e.target.value)}>
            {IMPORTANCE.map(i => <option key={i} value={i}>{i || 'All importance'}</option>)}
          </select>
        </div>
      </div>

      {/* Email list */}
      <div className="card" style={{ padding: '0' }}>
        {loading && <div className="loading">Loading emails…</div>}
        {!loading && emails.length === 0 && (
          <div className="empty">
            No emails found.{' '}
            <span style={{ color: 'var(--text-muted)' }}>
              Use the Ingest tab to load mock data, or connect Gmail.
            </span>
          </div>
        )}
        <div className="email-list">
          {emails.map(e => (
            <div
              key={e.id}
              className={`email-row ${!e.is_read ? 'unread' : ''}`}
              onClick={() => setSelected(selected?.id === e.id ? null : e)}
            >
              <div className="email-avatar">{avatar(e.sender)}</div>
              <div className="email-meta">
                <div className="email-from">{(e.sender || 'Unknown').replace(/<.*>/, '').trim()}</div>
                <div className="email-subject">{e.subject || '(no subject)'}</div>
                <div className="email-snippet">{e.snippet || e.analysis?.summary || ''}</div>
              </div>
              <div className="email-right">
                <span className="email-date">{formatDate(e.received_at)}</span>
                {e.analysis?.importance && (
                  <span className={`badge ${e.analysis.importance === 'high' ? 'badge-error' : e.analysis.importance === 'medium' ? 'badge-warning' : 'badge-info'}`}>
                    {e.analysis.importance}
                  </span>
                )}
                {e._similarity != null && (
                  <span className="badge badge-ok">{(e._similarity * 100).toFixed(0)}% match</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Inline detail panel */}
        {selected && (
          <div style={{
            borderTop: '1px solid var(--border)',
            padding: '20px 24px',
            background: 'var(--bg-base)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
              <div>
                <div style={{ fontSize: '16px', fontWeight: 600, marginBottom: '4px' }}>
                  {selected.subject || '(no subject)'}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '12.5px' }}>From: {selected.sender}</div>
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>✕ Close</button>
            </div>
            {selected.analysis && (
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '14px' }}>
                {selected.analysis.category  && <span className="badge badge-info">{selected.analysis.category}</span>}
                {selected.analysis.importance && <span className="badge badge-warning">{selected.analysis.importance}</span>}
                {selected.analysis.sentiment  && <span className="badge badge-ok">{selected.analysis.sentiment}</span>}
                {selected.analysis.cleanup_recommended && <span className="badge badge-error">Cleanup suggested</span>}
              </div>
            )}
            {selected.analysis?.summary && (
              <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '10px', fontStyle: 'italic' }}>
                AI Summary: {selected.analysis.summary}
              </div>
            )}
            <div style={{ color: 'var(--text-secondary)', fontSize: '13px', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
              {selected.body_text || selected.snippet || '(no preview available)'}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
