import { useState } from 'react'
import Dashboard from './pages/Dashboard'
import Emails from './pages/Emails'
import Cleanup from './pages/Cleanup'
import JobAssistant from './pages/JobAssistant'
import Ingest from './pages/Ingest'
import './index.css'

const NAV = [
  { id: 'dashboard',  icon: '⬡', label: 'Dashboard'      },
  { id: 'emails',     icon: '✉', label: 'Emails'          },
  { id: 'cleanup',    icon: '🗑', label: 'Cleanup'         },
  { id: 'jobs',       icon: '💼', label: 'Job Assistant'   },
  { id: 'ingest',     icon: '⬆', label: 'Ingest (Dev)'    },
]

const PAGES = {
  dashboard: <Dashboard />,
  emails:    <Emails />,
  cleanup:   <Cleanup />,
  jobs:      <JobAssistant />,
  ingest:    <Ingest />,
}

export default function App() {
  const [page, setPage] = useState('dashboard')

  return (
    <div className="app-shell">
      {/* Sidebar */}
      <nav className="sidebar">
        <div className="sidebar-logo">
          <div className="logo-icon">✉</div>
          <span>EmailAgent</span>
        </div>
        {NAV.map(item => (
          <button
            key={item.id}
            className={`nav-item ${page === item.id ? 'active' : ''}`}
            onClick={() => setPage(item.id)}
          >
            <span className="icon">{item.icon}</span>
            {item.label}
          </button>
        ))}

        {/* Bottom info */}
        <div style={{ marginTop: 'auto', padding: '16px 18px',
          fontSize: '11.5px', color: 'var(--text-muted)', borderTop: '1px solid var(--border)' }}>
          <div style={{ marginBottom: '4px', fontWeight: 600 }}>Phase 1</div>
          <div>Stack verification</div>
          <div style={{ marginTop: '8px' }}>
            <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer"
              style={{ color: 'var(--accent-light)', fontSize: '11px' }}>
              API Docs ↗
            </a>
          </div>
        </div>
      </nav>

      {/* Main */}
      <main className="main-content">
        {PAGES[page]}
      </main>
    </div>
  )
}
