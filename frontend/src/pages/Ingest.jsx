import { useState } from 'react'
import { ingestEmail } from '../api'

const MOCK_EMAILS = [
  {
    gmail_id: 'mock-001',
    subject: 'Your application for Senior AI Engineer has been shortlisted',
    sender: 'Talent Acquisition <talent@techcorp.io>',
    recipients: 'you@example.com',
    body_text: `Dear Candidate,

We are pleased to inform you that your application for the Senior AI Engineer role at TechCorp has been shortlisted for the next round.

Please expect a calendar invite for a technical interview within 48 hours.

Best regards,
TechCorp Talent Team`,
    snippet: 'Your application has been shortlisted for the next round.',
    received_at: new Date(Date.now() - 3600000).toISOString(),
    is_read: false,
    labels: 'INBOX',
  },
  {
    gmail_id: 'mock-002',
    subject: '50% off this weekend only — Flash Sale!',
    sender: 'Deals <noreply@shopping.example.com>',
    recipients: 'you@example.com',
    body_text: 'Huge discounts this weekend. Shop now and save big on all items.',
    snippet: 'Huge discounts this weekend. Don\'t miss out.',
    received_at: new Date(Date.now() - 86400000).toISOString(),
    is_read: true,
    labels: 'INBOX,PROMOTIONS',
  },
  {
    gmail_id: 'mock-003',
    subject: 'Interview scheduled: Machine Learning Engineer @ DataDriven Inc.',
    sender: 'HR Team <hr@datadriven.io>',
    recipients: 'you@example.com',
    body_text: `Hi,

We'd like to invite you for a technical interview for the Machine Learning Engineer position.

Date: Thursday, 10:00 AM IST
Format: Video call (Google Meet)

Please confirm your availability.

Regards,
DataDriven Hiring Team`,
    snippet: 'Technical interview scheduled for Thursday at 10 AM.',
    received_at: new Date(Date.now() - 172800000).toISOString(),
    is_read: false,
    labels: 'INBOX',
  },
  {
    gmail_id: 'mock-004',
    subject: 'Your weekly newsletter — Top Developer News',
    sender: 'DevDigest <weekly@devdigest.io>',
    recipients: 'you@example.com',
    body_text: 'This week in developer news: React 20 released, Rust overtakes Python in benchmarks, and more.',
    snippet: 'React 20 released, Rust overtakes Python…',
    received_at: new Date(Date.now() - 259200000).toISOString(),
    is_read: true,
    labels: 'INBOX',
  },
  {
    gmail_id: 'mock-005',
    subject: 'Offer Letter — Full Stack Developer at CloudBase',
    sender: 'CloudBase HR <hr@cloudbase.dev>',
    recipients: 'you@example.com',
    body_text: `Congratulations!

We are delighted to extend an offer of employment for the position of Full Stack Developer at CloudBase.

Start Date: 15 October 2026
CTC: As discussed

Please sign and return the attached offer letter within 3 business days.

Welcome to the team!`,
    snippet: 'We are delighted to extend an offer of employment.',
    received_at: new Date(Date.now() - 432000000).toISOString(),
    is_read: false,
    labels: 'INBOX',
  },
]

export default function Ingest() {
  const [accountId, setAccountId]   = useState('demo-account-001')
  const [results, setResults]       = useState([])
  const [loading, setLoading]       = useState(false)
  const [custom, setCustom]         = useState('')
  const [customErr, setCustomErr]   = useState(null)

  const ingestAll = async () => {
    setLoading(true)
    const out = []
    for (const email of MOCK_EMAILS) {
      try {
        const res = await ingestEmail({ ...email, account_id: accountId })
        out.push({ ...res.data, subject: email.subject, ok: true })
      } catch (e) {
        out.push({ subject: email.subject, ok: false, error: e.response?.data?.detail || e.message })
      }
    }
    setResults(out)
    setLoading(false)
  }

  const ingestCustom = async () => {
    setCustomErr(null)
    let parsed
    try { parsed = JSON.parse(custom) } catch { setCustomErr('Invalid JSON'); return }
    if (!parsed.account_id) parsed.account_id = accountId
    if (!parsed.gmail_id)   { setCustomErr('gmail_id is required'); return }
    try {
      const res = await ingestEmail(parsed)
      setResults(prev => [{ ...res.data, subject: parsed.subject, ok: true }, ...prev])
      setCustom('')
    } catch (e) {
      setCustomErr(e.response?.data?.detail || e.message)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <h1 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '4px' }}>Mock Email Ingest</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
          Load test emails into the pipeline (store → embed → AI-analyze) without Gmail.
        </p>
      </div>

      <div className="card">
        <div className="card-title">⚙️ Ingest Configuration</div>
        <div className="form-group">
          <label className="form-label">Account ID (mock)</label>
          <input className="input" value={accountId} onChange={e => setAccountId(e.target.value)} />
        </div>
        <div style={{ marginBottom: '14px' }}>
          <div style={{ color: 'var(--text-secondary)', fontSize: '13px', marginBottom: '8px' }}>
            {MOCK_EMAILS.length} mock emails ready: job shortlist, promotional, interview, newsletter, offer letter.
          </div>
          <button className="btn btn-primary" onClick={ingestAll} disabled={loading}>
            {loading ? '⟳ Processing…' : `🚀 Ingest All ${MOCK_EMAILS.length} Emails`}
          </button>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
          Each email is stored → embedded → AI-analyzed. Check the Emails tab when done.
        </p>
      </div>

      {results.length > 0 && (
        <div className="card">
          <div className="card-title">📊 Ingest Results</div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Subject</th>
                  <th>Status</th>
                  <th>Category</th>
                  <th>Importance</th>
                  <th>Embedded</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i}>
                    <td style={{ maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {r.subject}
                    </td>
                    <td>
                      <span className={`badge ${r.ok ? 'badge-ok' : 'badge-error'}`}>
                        {r.ok ? 'OK' : 'FAILED'}
                      </span>
                    </td>
                    <td>{r.category || r.error || '—'}</td>
                    <td>{r.importance || '—'}</td>
                    <td>{r.embedded != null ? (r.embedded ? '✓' : '—') : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Custom email ingest */}
      <div className="card">
        <div className="card-title">📝 Custom Email (JSON)</div>
        <div className="form-group">
          <label className="form-label">Paste email JSON</label>
          <textarea className="textarea" rows={8}
            placeholder={`{\n  "gmail_id": "custom-001",\n  "subject": "Test email",\n  "sender": "test@example.com",\n  "body_text": "Hello world"\n}`}
            value={custom} onChange={e => setCustom(e.target.value)} />
        </div>
        {customErr && <div style={{ color: 'var(--danger)', fontSize: '13px', marginBottom: '10px' }}>❌ {customErr}</div>}
        <button className="btn btn-ghost" onClick={ingestCustom}>
          ▶ Ingest Custom Email
        </button>
      </div>
    </div>
  )
}
