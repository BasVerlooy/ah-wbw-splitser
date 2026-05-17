import { useState, useEffect } from 'react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import ReceiptDetail from './pages/ReceiptDetail'
import Receipts from './pages/Receipts'
import Roommates from './pages/Roommates'
import Settings from './pages/Settings'
import './index.css'

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))
  }

  return (
    <BrowserRouter>
      <nav>
        <span className="brand">AH Splitser</span>
        <NavLink to="/">Dashboard</NavLink>
        <NavLink to="/receipts">Receipts</NavLink>
        <NavLink to="/roommates">Roommates</NavLink>
        <NavLink to="/settings">Settings</NavLink>
        <div style={{ marginLeft: 'auto' }}>
          <button onClick={toggleTheme} className="theme-toggle">
            {theme === 'light' ? '🌙 Dark' : '☀️ Light'}
          </button>
        </div>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/receipts" element={<Receipts />} />
          <Route path="/receipts/:id" element={<ReceiptDetail />} />
          <Route path="/roommates" element={<Roommates />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
