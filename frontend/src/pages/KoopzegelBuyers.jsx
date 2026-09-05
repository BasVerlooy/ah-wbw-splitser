import { useEffect, useState } from 'react'
import { api } from '../api'

export default function KoopzegelBuyers() {
  const [buyers, setBuyers] = useState([])
  const [stores, setStores] = useState([])
  const [summary, setSummary] = useState(null)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [savingStore, setSavingStore] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([
      api.get('/koopzegel-buyers'),
      api.get('/koopzegel-summary'),
      api.get('/koopzegel-stores'),
    ])
      .then(([loadedBuyers, loadedSummary, loadedStores]) => {
        setBuyers(loadedBuyers)
        setSummary(loadedSummary)
        setStores(loadedStores)
      })
      .catch((loadError) => setError(loadError.message))
  }, [])

  async function addBuyer(event) {
    event.preventDefault()
    if (!name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const buyer = await api.post('/koopzegel-buyers', { name: name.trim() })
      setBuyers((previous) => [...previous, buyer].sort((a, b) => a.name.localeCompare(b.name)))
      setName('')
    } catch (submitError) {
      setError(submitError.message)
    } finally {
      setSaving(false)
    }
  }

  async function removeBuyer(id) {
    setError(null)
    try {
      await api.del(`/koopzegel-buyers/${id}`)
      setBuyers((previous) => previous.filter((buyer) => buyer.id !== id))
    } catch (deleteError) {
      setError(deleteError.message)
    }
  }

  async function updateStoreBuyer(storeInfo, value) {
    const buyerId = value ? Number(value) : null
    setSavingStore(storeInfo)
    setError(null)
    try {
      const result = await api.put('/koopzegel-stores', {
        store_info: storeInfo,
        buyer_id: buyerId,
      })
      setStores((previous) => previous.map((store) => (
        store.store_info === storeInfo ? { ...store, buyer: result.buyer } : store
      )))
      setSummary(await api.get('/koopzegel-summary'))
    } catch (updateError) {
      setError(updateError.message)
    } finally {
      setSavingStore(null)
    }
  }

  function storeAddress(store) {
    const address = store.address
    const street = [address.street, address.house_number].filter(Boolean).join(' ')
    return [street, address.city].filter(Boolean).join(', ') || `Store ${store.store_info}`
  }

  return (
    <div>
      <h1>Koopzegel buyers</h1>
      <div className="card">
        <h2>Your Koopzegels</h2>
        {summary ? (
          <>
            <p style={{ margin: '0 0 0.75rem', fontSize: '1.1rem', fontWeight: 600 }}>
              {summary.quantity} Koopzegels · €{summary.amount.toFixed(2)}
            </p>
            <table>
              <thead>
                <tr>
                  <th>Buyer</th>
                  <th>Koopzegels</th>
                  <th>Value</th>
                </tr>
              </thead>
              <tbody>
                {summary.buyers.map((buyer) => (
                  <tr key={buyer.id}>
                    <td>{buyer.name}</td>
                    <td>{buyer.quantity}</td>
                    <td>€{buyer.amount.toFixed(2)}</td>
                  </tr>
                ))}
                {summary.unassigned.quantity > 0 && (
                  <tr>
                    <td className="muted">Not selected</td>
                    <td>{summary.unassigned.quantity}</td>
                    <td>€{summary.unassigned.amount.toFixed(2)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </>
        ) : (
          <p className="muted" style={{ margin: 0 }}>Loading total…</p>
        )}
      </div>
      <div className="card">
        <h2>Add buyer</h2>
        <form onSubmit={addBuyer} className="row">
          <input
            type="text"
            placeholder="Name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            style={{ maxWidth: 220 }}
          />
          <button className="primary" type="submit" disabled={saving || !name.trim()}>
            Add
          </button>
        </form>
        {error && <p style={{ color: '#c00', marginTop: '0.5rem' }}>{error}</p>}
      </div>

      <div className="card">
        <h2>Stores</h2>
        <p className="muted">
          Link a store to a buyer to automatically assign existing and future Koopzegel receipts.
        </p>
        {stores.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>Store</th>
                <th>Receipts</th>
                <th>Buyer</th>
              </tr>
            </thead>
            <tbody>
              {stores.map((store) => (
                <tr key={store.store_info}>
                  <td>
                    {storeAddress(store)}
                    <div className="muted">Store {store.store_info}</div>
                  </td>
                  <td>{store.koopzegel_receipt_count} with Koopzegels</td>
                  <td>
                    <select
                      value={store.buyer?.id ?? ''}
                      onChange={(event) => updateStoreBuyer(store.store_info, event.target.value)}
                      disabled={savingStore === store.store_info || buyers.length === 0}
                    >
                      <option value="">Not linked</option>
                      {buyers.map((buyer) => (
                        <option key={buyer.id} value={buyer.id}>{buyer.name}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted" style={{ marginBottom: 0 }}>No stores found in synced receipts.</p>
        )}
      </div>

      {buyers.length > 0 && (
        <div className="card">
          <h2>Buyers</h2>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {buyers.map((buyer) => (
                <tr key={buyer.id}>
                  <td>{buyer.name}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button className="danger" onClick={() => removeBuyer(buyer.id)}>Remove</button>
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
