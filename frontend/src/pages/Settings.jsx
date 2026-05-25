import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Settings() {
  const [splitserGroup, setSplitserGroup] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  const [ahEmail, setAhEmail] = useState('')
  const [ahPassword, setAhPassword] = useState('')
  const [ahLoginStep, setAhLoginStep] = useState('idle') // idle | loading | mfa | success | error
  const [ahMfaCode, setAhMfaCode] = useState('')
  const [ahError, setAhError] = useState(null)

  useEffect(() => {
    api.get('/settings')
      .then((s) => setSplitserGroup(s.splitser_group ?? ''))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      await api.patch('/settings', { splitser_group: splitserGroup || null })
      setSaved(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleAhLogin(e) {
    e.preventDefault()
    setAhLoginStep('loading')
    setAhError(null)
    try {
      const result = await api.post('/auth/ah/login', { email: ahEmail, password: ahPassword })
      if (result.status === 'mfa_required') {
        setAhLoginStep('mfa')
      } else if (result.status === 'success') {
        setAhLoginStep('success')
      }
    } catch (e) {
      setAhError(e.message)
      setAhLoginStep('error')
    }
  }

  async function handleAhMfa(e) {
    e.preventDefault()
    setAhLoginStep('loading')
    setAhError(null)
    try {
      await api.post('/auth/ah/mfa', { code: ahMfaCode })
      setAhLoginStep('success')
      setAhMfaCode('')
    } catch (e) {
      setAhError(e.message)
      setAhLoginStep('error')
    }
  }

  if (loading) return <p className="muted">Loading…</p>

  return (
    <div>
      <h1>Settings</h1>

      <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ margin: '0 0 0.25rem' }}>AH Login</h2>
          <p className="muted" style={{ margin: '0 0 1rem', fontSize: '0.875rem' }}>
            Log in with your Albert Heijn account to sync receipts.
          </p>

          {ahLoginStep === 'success' && (
            <p style={{ color: '#1c7a4b', fontWeight: 600 }}>Logged in successfully. AH token saved.</p>
          )}

          {(ahLoginStep === 'idle' || ahLoginStep === 'error') && (
            <form onSubmit={handleAhLogin} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                <input
                  type="email"
                  placeholder="AH email"
                  value={ahEmail}
                  onChange={(e) => setAhEmail(e.target.value)}
                  required
                  style={{ flex: '1', minWidth: '180px' }}
                />
                <input
                  type="password"
                  placeholder="Password"
                  value={ahPassword}
                  onChange={(e) => setAhPassword(e.target.value)}
                  required
                  style={{ flex: '1', minWidth: '160px' }}
                />
                <button className="primary" type="submit">Login</button>
              </div>
              {ahError && <p style={{ color: '#c00', fontSize: '0.875rem', margin: 0 }}>{ahError}</p>}
            </form>
          )}

          {ahLoginStep === 'loading' && (
            <p className="muted">Logging in…</p>
          )}

          {ahLoginStep === 'mfa' && (
            <form onSubmit={handleAhMfa} style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <p style={{ margin: 0, fontSize: '0.875rem' }}>
                An SMS code was sent to your phone. Enter it below.
              </p>
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                <input
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  placeholder="123456"
                  value={ahMfaCode}
                  onChange={(e) => setAhMfaCode(e.target.value.replace(/\D/g, ''))}
                  required
                  autoFocus
                  style={{ fontFamily: 'monospace', letterSpacing: '0.2em', width: '120px', fontSize: '1.1rem' }}
                />
                <button className="primary" type="submit">Verify</button>
                <button type="button" onClick={() => setAhLoginStep('idle')}>Cancel</button>
              </div>
              {ahError && <p style={{ color: '#c00', fontSize: '0.875rem', margin: 0 }}>{ahError}</p>}
            </form>
          )}
        </div>
      </div>

      <form onSubmit={handleSave}>
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: '0.35rem' }}>
              Splitser Group UUID
            </label>
            <p className="muted" style={{ marginBottom: '0.5rem', fontSize: '0.875rem' }}>
              The UUID of the Splitser / wiebetaaltwat group to post expenses to.
            </p>
            <input
              type="text"
              value={splitserGroup}
              onChange={(e) => setSplitserGroup(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              style={{ fontFamily: 'monospace' }}
            />
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
            <button className="primary" type="submit" disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
            {saved && <span style={{ color: '#1c7a4b', fontSize: '0.9rem' }}>Saved</span>}
            {error && <span style={{ color: '#c00', fontSize: '0.9rem' }}>{error}</span>}
          </div>
        </div>
      </form>
    </div>
  )
}
