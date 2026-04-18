import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Settings() {
  const [values, setValues] = useState({ ah_cookie: '', splitser_group: '' })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/settings')
      .then((s) => setValues({ ah_cookie: s.ah_cookie ?? '', splitser_group: s.splitser_group ?? '' }))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  async function handleSave(e) {
    e.preventDefault()
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      await api.patch('/settings', {
        ah_cookie: values.ah_cookie || null,
        splitser_group: values.splitser_group || null,
      })
      setSaved(true)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="muted">Loading…</p>

  return (
    <div>
      <h1>Settings</h1>

      <form onSubmit={handleSave}>
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>

          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: '0.35rem' }}>
              AH Cookie
            </label>
            <p className="muted" style={{ marginBottom: '0.5rem', fontSize: '0.875rem' }}>
              The full <code>Cookie</code> header value from an authenticated Albert Heijn session.
            </p>
            <textarea
              rows={4}
              value={values.ah_cookie}
              onChange={(e) => setValues((v) => ({ ...v, ah_cookie: e.target.value }))}
              placeholder="Paste your AH cookie here…"
              style={{ width: '100%', fontFamily: 'monospace', fontSize: '0.8rem', resize: 'vertical' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontWeight: 600, marginBottom: '0.35rem' }}>
              Splitser Group UUID
            </label>
            <p className="muted" style={{ marginBottom: '0.5rem', fontSize: '0.875rem' }}>
              The UUID of the Splitser / wiebetaaltwat group to post expenses to.
            </p>
            <input
              type="text"
              value={values.splitser_group}
              onChange={(e) => setValues((v) => ({ ...v, splitser_group: e.target.value }))}
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
