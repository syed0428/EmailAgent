import { useState, useEffect } from 'react'
import { getCleanupSuggestions, approveCleanup } from '../api'

export default function Cleanup() {
  const [data, setData]         = useState(null)
  const [loading, setLoading]   = useState(true)
  const [selected, setSelected] = useState(new Set())
  const [confirming, setConfirming] = useState(false)
  const [done, setDone]         = useState(false)

  useEffect(() => {
    getCleanupSuggestions()
      .then(r => setData(r.data))
      .catch(() => setData({ total: 0, by_category: {}, items: [] }))
      .finally(() => setLoading(false))
  }, [])

  const toggle = (id) => {
    const next = new Set(selected)
    next.has(id) ? next.delete(id) : next.add(id)
    setSelected(next)
  }

  const toggleAll = () => {
    if (!data) return
    if (selected.size === data.items.length) setSelected(new Set())
    else setSelected(new Set(data.items.map(i => i.email_id)))
  }

  const handleApprove = async () => {
    if (selected.size === 0) return
    await approveCleanup([...selected])
    setDone(true)
    setConfirming(false)
  }

  if (loading) return <div className="loading">Loading cleanup suggestions…</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <h1 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '4px' }}>AI Cleanup Suggestions</h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
          Review AI recommendations. Nothing is deleted until you explicitly confirm.
        </p>
      </div>

      {done && (
        <div className="card" style={{ borderColor: 'var(--success)', background: 'rgba(34,197,94,0.05)' }}>
          <div style={{ color: 'var(--success)', fontWeight: 600 }}>
            ✓ {selected.size} emails marked for cleanup. (Move to Trash is a future phase action.)
          </div>
        </div>
      )}

      {/* Summary tiles */}
      {data && (
        <div className="stats-grid">
          <div className="stat-tile">
            <div className="stat-label">Total suggested</div>
            <div className="stat-value">{data.total}</div>
          </div>
          {Object.entries(data.by_category || {}).map(([cat, count]) => (
            <div className="stat-tile" key={cat}>
              <div className="stat-label">{cat}</div>
              <div className="stat-value">{count}</div>
            </div>
          ))}
        </div>
      )}

      {data?.total === 0 && (
        <div className="empty">No cleanup suggestions yet. Run email analysis first.</div>
      )}

      {data?.total > 0 && (
        <>
          {/* Actions bar */}
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <button className="btn btn-ghost btn-sm" onClick={toggleAll}>
              {selected.size === data.items.length ? 'Deselect All' : 'Select All'}
            </button>
            <span style={{ color: 'var(--text-muted)', fontSize: '12.5px' }}>
              {selected.size} selected
            </span>
            {selected.size > 0 && !confirming && (
              <button className="btn btn-danger btn-sm" style={{ marginLeft: 'auto' }}
                onClick={() => setConfirming(true)}>
                🗑 Mark {selected.size} for cleanup
              </button>
            )}
          </div>

          {/* Confirmation prompt */}
          {confirming && (
            <div className="card" style={{ borderColor: 'var(--warning)', background: 'rgba(245,158,11,0.06)' }}>
              <div style={{ fontWeight: 600, marginBottom: '8px' }}>
                ⚠ You are about to mark {selected.size} emails for cleanup.
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: '12.5px', marginBottom: '14px' }}>
                This will flag them as approved for future Trash move. No email is deleted now.
              </div>
              <div style={{ display: 'flex', gap: '10px' }}>
                <button className="btn btn-danger" onClick={handleApprove}>Confirm</button>
                <button className="btn btn-ghost" onClick={() => setConfirming(false)}>Cancel</button>
              </div>
            </div>
          )}

          {/* Table */}
          <div className="card" style={{ padding: 0 }}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th style={{ width: 40 }}>
                      <input type="checkbox"
                        checked={selected.size === data.items.length}
                        onChange={toggleAll} />
                    </th>
                    <th>Subject</th>
                    <th>Sender</th>
                    <th>Category</th>
                    <th>Reason</th>
                    <th>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map(item => (
                    <tr key={item.email_id}>
                      <td>
                        <input type="checkbox"
                          checked={selected.has(item.email_id)}
                          onChange={() => toggle(item.email_id)} />
                      </td>
                      <td style={{ maxWidth: '260px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.subject || '(no subject)'}
                      </td>
                      <td style={{ maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {(item.sender || '').replace(/<.*>/, '').trim()}
                      </td>
                      <td><span className="badge badge-info">{item.category}</span></td>
                      <td style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{item.cleanup_reason || '—'}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {item.received_at ? new Date(item.received_at).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
