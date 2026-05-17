import { useEffect, useState } from 'react'
import { api } from '../api'

export default function Roommates() {
  const [roommates, setRoommates] = useState([])
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.get('/roommates').then(setRoommates).catch(console.error)
  }, [])

  async function addRoommate(e) {
    e.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const rm = await api.post('/roommates', { name: name.trim() })
      setRoommates((prev) => [...prev, rm])
      setName('')
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function remove(id) {
    await api.del(`/roommates/${id}`)
    setRoommates((prev) => prev.filter((r) => r.id !== id))
  }

  async function setDefaultPayer(id) {
    const current = roommates.find((r) => r.id === id)
    const next = !current?.is_default_payer
    const updated = await api.patch(`/roommates/${id}`, { is_default_payer: next })
    // Server clears all others, so refresh the full list
    setRoommates((prev) =>
      prev.map((r) => r.id === id ? updated : { ...r, is_default_payer: false })
    )
  }

  return (
    <div>
      <h1>Roommates</h1>

      <div className="card">
        <h2>Add roommate</h2>
        <form onSubmit={addRoommate} className="row">
          <input
            type="text"
            placeholder="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ maxWidth: 220 }}
          />
          <button className="primary" type="submit" disabled={saving || !name.trim()}>
            Add
          </button>
        </form>
        {error && <p style={{ color: '#c00', marginTop: '0.5rem' }}>{error}</p>}
      </div>

      {roommates.length > 0 && (
        <div className="card">
          <h2>Current roommates</h2>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th style={{ textAlign: 'center' }}>Default payer</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {roommates.map((r) => (
                <tr key={r.id}>
                  <td>{r.name}</td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      className={`default-payer ${r.is_default_payer ? 'is-active' : ''}`}
                      onClick={() => setDefaultPayer(r.id)}
                    >
                      {r.is_default_payer ? 'Default' : 'Set default'}
                    </button>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <button className="danger" onClick={() => remove(r.id)}>Remove</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
