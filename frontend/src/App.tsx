import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import LeadDetail from './pages/LeadDetail'
import Leads from './pages/Leads'

const NAV = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/leads', label: 'Leads' },
]

export default function App() {
  return (
    <div className="min-h-screen bg-ink-50 text-ink-900">
      <header className="bg-white border-b border-ink-200 sticky top-0 z-20">
        <div className="max-w-7xl mx-auto px-6 h-14 flex items-center gap-8">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded bg-ink-900 text-white grid
              place-items-center text-xs font-bold">3PL</div>
            <span className="font-semibold">Intent Intelligence</span>
          </div>
          <nav className="flex gap-1">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    isActive ? 'bg-ink-100 text-ink-900'
                      : 'text-ink-500 hover:text-ink-900'}`}>
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto text-xs text-ink-400">
            Third-Party Logistics
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/leads/:id" element={<LeadDetail />} />
        </Routes>
      </main>

      <footer className="max-w-7xl mx-auto px-6 py-8 text-xs text-ink-400">
        This platform does not discover, verify or store email addresses.
        A complete lead is Company + Intent + Evidence + Decision Maker.
      </footer>
    </div>
  )
}
