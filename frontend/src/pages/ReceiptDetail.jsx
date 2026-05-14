import { useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { api } from '../api'

export default function ReceiptDetail() {
  const { id } = useParams()
  const { state: navState } = useLocation()
  const backTo = navState?.from ?? '/receipts'
  const [receipt, setReceipt] = useState(null)
  const [roommates, setRoommates] = useState([])
  const [splits, setSplits] = useState([])
  const [newName, setNewName] = useState('')
  // selectedProducts: { [productId]: quantity (null = full qty) }
  const [selectedProducts, setSelectedProducts] = useState({})
  const [selectedRoommateIds, setSelectedRoommateIds] = useState([])
  const [overrideInput, setOverrideInput] = useState('')
  // splitOverrides: { [splitId]: string } — override inputs for existing splits
  const [splitOverrides, setSplitOverrides] = useState({})
  const [splitPaidBy, setSplitPaidBy] = useState({})   // { [splitId]: roommateId | null }
  const [newPaidBy, setNewPaidBy] = useState(null)      // for create form
  const [saving, setSaving] = useState(false)
  const [savingOverride, setSavingOverride] = useState(null)
  const [pushingToSplitser, setPushingToSplitser] = useState(null)
  const [updatingSplitser, setUpdatingSplitser] = useState(null)
  const [deletingFromSplitser, setDeletingFromSplitser] = useState(null)

  async function load() {
    const [r, rm, s] = await Promise.all([
      api.get(`/receipts/${id}`),
      api.get('/roommates'),
      api.get(`/receipts/${id}/splits`),
    ])
    setReceipt(r)
    setRoommates(rm)
    setSplits(s.splits)
    setSelectedRoommateIds(rm.map((r) => r.id))
    const defaultPayer = rm.find((r) => r.is_default_payer)
    setNewPaidBy(defaultPayer?.id ?? null)
    const overrides = {}
    const paidBy = {}
    for (const split of s.splits) {
      overrides[split.id] = split.override_amount != null ? String(split.override_amount) : ''
      paidBy[split.id] = split.payed_by_roommate_id ?? defaultPayer?.id ?? null
    }
    setSplitOverrides(overrides)
    setSplitPaidBy(paidBy)
  }

  useEffect(() => { load().catch(console.error) }, [id])

  const allocatedIds = new Set(splits.flatMap((s) => s.products.map((p) => p.product_id)))

  function toggleProduct(pid) {
    setSelectedProducts((prev) => {
      const next = { ...prev }
      if (pid in next) {
        delete next[pid]
      } else {
        next[pid] = null // null = use full product quantity
      }
      return next
    })
  }

  function setProductQty(pid, qty) {
    setSelectedProducts((prev) => ({ ...prev, [pid]: qty }))
  }

  function toggleRoommate(rid) {
    setSelectedRoommateIds((prev) =>
      prev.includes(rid) ? prev.filter((r) => r !== rid) : [...prev, rid]
    )
  }

  function buildSplitsPayload() {
    return splits.map((s) => ({
      name: s.name,
      products: s.products.map((p) => ({ product_id: p.product_id, quantity: p.quantity })),
      roommates: s.roommates.map((r) => ({ roommate_id: r.roommate_id })),
      override_amount: splitOverrides[s.id] != null && splitOverrides[s.id] !== ''
        ? parseFloat(splitOverrides[s.id])
        : s.override_amount,
      payed_by_roommate_id: splitPaidBy[s.id] ?? s.payed_by_roommate_id ?? null,
    }))
  }

  async function createSplit() {
    const selectedIds = Object.keys(selectedProducts)
    if (selectedIds.length === 0 || selectedRoommateIds.length === 0) return
    setSaving(true)
    try {
      const newSplitProducts = selectedIds.map((pid) => ({
        product_id: Number(pid),
        quantity: selectedProducts[pid],
      }))
      const overrideAmt = overrideInput !== '' ? parseFloat(overrideInput) : null
      const result = await api.put(`/receipts/${id}/splits`, {
        splits: [
          ...buildSplitsPayload(),
          {
            name: newName.trim() || 'Split',
            products: newSplitProducts,
            roommates: selectedRoommateIds.map((rid) => ({ roommate_id: rid })),
            override_amount: overrideAmt,
            payed_by_roommate_id: newPaidBy,
          },
        ],
      })
      setSplits(result.splits)
      const overrides = {}
      for (const split of result.splits) {
        overrides[split.id] = split.override_amount != null ? String(split.override_amount) : ''
      }
      setSplitOverrides(overrides)
      setNewName('')
      setSelectedProducts({})
      setOverrideInput('')
      setNewPaidBy(roommates.find((r) => r.is_default_payer)?.id ?? null)
    } catch (e) {
      alert(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function deleteSplit(splitId) {
    const remaining = splits
      .filter((s) => s.id !== splitId)
      .map((s) => ({
        name: s.name,
        products: s.products.map((p) => ({ product_id: p.product_id, quantity: p.quantity })),
        roommates: s.roommates.map((r) => ({ roommate_id: r.roommate_id })),
        override_amount: s.override_amount,
        payed_by_roommate_id: s.payed_by_roommate_id ?? null,
      }))
    const result = await api.put(`/receipts/${id}/splits`, { splits: remaining })
    setSplits(result.splits)
    setSplitOverrides((prev) => {
      const next = { ...prev }
      delete next[splitId]
      return next
    })
  }

  async function pushToSplitser(splitId) {
    setPushingToSplitser(splitId)
    try {
      const result = await api.post(`/receipts/${id}/splits/${splitId}/push-to-splitser`, {})
      setSplits((prev) =>
        prev.map((s) => s.id === splitId ? { ...s, splitser_expense_id: result.splitser_expense_id } : s)
      )
    } catch (e) {
      alert(e.message)
    } finally {
      setPushingToSplitser(null)
    }
  }

  async function updateInSplitser(splitId) {
    setUpdatingSplitser(splitId)
    try {
      await api.patch(`/receipts/${id}/splits/${splitId}/splitser-expense`, {})
    } catch (e) {
      alert(e.message)
    } finally {
      setUpdatingSplitser(null)
    }
  }

  async function deleteFromSplitser(splitId) {
    setDeletingFromSplitser(splitId)
    try {
      await api.del(`/receipts/${id}/splits/${splitId}/splitser-expense`)
      setSplits((prev) =>
        prev.map((s) => s.id === splitId ? { ...s, splitser_expense_id: null } : s)
      )
    } catch (e) {
      alert(e.message)
    } finally {
      setDeletingFromSplitser(null)
    }
  }

  async function saveOverride(splitId) {
    setSavingOverride(splitId)
    try {
      const updatedSplits = splits.map((s) => ({
        name: s.name,
        products: s.products.map((p) => ({ product_id: p.product_id, quantity: p.quantity })),
        roommates: s.roommates.map((r) => ({ roommate_id: r.roommate_id })),
        override_amount: s.id === splitId
          ? (splitOverrides[splitId] !== '' ? parseFloat(splitOverrides[splitId]) : null)
          : s.override_amount,
        payed_by_roommate_id: splitPaidBy[s.id] ?? s.payed_by_roommate_id ?? null,
      }))
      const result = await api.put(`/receipts/${id}/splits`, { splits: updatedSplits })
      setSplits(result.splits)
      const overrides = {}
      for (const split of result.splits) {
        overrides[split.id] = split.override_amount != null ? String(split.override_amount) : ''
      }
      setSplitOverrides(overrides)
    } catch (e) {
      alert(e.message)
    } finally {
      setSavingOverride(null)
    }
  }

  if (!receipt) return <p className="muted">Loading…</p>

  const products = receipt.products
  const date = receipt.date_time ? new Date(receipt.date_time).toLocaleDateString('nl-NL') : null
  const addr = receipt.address ?? {}
  const addressLine = [addr.street, addr.house_number].filter(Boolean).join(' ')
  const cityLine = [addr.postal_code, addr.city].filter(Boolean).join(' ')

  return (
    <div>
      <Link to={backTo} style={{ display: 'inline-block', marginBottom: '0.75rem', color: '#888', fontSize: '0.9rem', textDecoration: 'none' }}>
        ← Back to receipts
      </Link>
      <h1 style={{ fontSize: '2rem', margin: '0 0 0.15rem' }}>
        Receipt — {[receipt.address?.city, date].filter(Boolean).join(', ')}
      </h1>
      {(addressLine || cityLine) && (
        <p className="muted" style={{ margin: '0 0 0.25rem', fontSize: '0.95rem' }}>
          {[addressLine, cityLine].filter(Boolean).join(', ')}
          {receipt.store_info && <span> · {receipt.store_info}</span>}
        </p>
      )}
      <p className="muted" style={{ marginBottom: '1.75rem' }}>
        ID: {receipt.id} | Total: €{receipt.total_amount?.toFixed(2)}
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2.5rem', alignItems: 'start' }}>

        {/* ── Left: existing splits ── */}
        <div>
          <h2 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Splits ({splits.length})</h2>

          {splits.length === 0 && (
            <p className="muted">No splits yet — create one on the right.</p>
          )}

          {splits.map((split) => {
            const splitProducts = products.filter((p) =>
              split.products.some((sp) => sp.product_id === p.id)
            )
            const names = split.roommates.map((r) => r.roommate_name).join(', ')
            const overrideVal = splitOverrides[split.id] ?? ''
            const overrideFloat = overrideVal !== '' ? parseFloat(overrideVal) : null
            const overrideInvalid = overrideFloat !== null && overrideFloat > split.calculated_total

            return (
              <div key={split.id} className="card" style={{ marginBottom: '1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
                  <strong style={{ fontSize: '1.05rem' }}>{split.name}</strong>
                  <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                    {split.splitser_expense_id ? (
                      <>
                        <span className="muted" style={{ fontSize: '0.78rem' }} title={split.splitser_expense_id}>
                          ✓ {split.splitser_expense_id.slice(0, 8)}…
                        </span>
                        <button
                          style={{ fontSize: '0.78rem', padding: '0.3rem 0.55rem' }}
                          disabled={updatingSplitser === split.id}
                          onClick={() => updateInSplitser(split.id)}
                        >
                          {updatingSplitser === split.id ? '…' : 'Update'}
                        </button>
                        <button
                          className="danger"
                          style={{ fontSize: '0.78rem', padding: '0.3rem 0.55rem' }}
                          disabled={deletingFromSplitser === split.id}
                          onClick={() => deleteFromSplitser(split.id)}
                        >
                          {deletingFromSplitser === split.id ? '…' : 'Remove from Splitser'}
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          style={{ background: '#1c7a4b', color: '#fff', border: 'none', borderRadius: 6, padding: '0.35rem 0.75rem', fontSize: '0.8rem', cursor: pushingToSplitser === split.id ? 'wait' : 'pointer' }}
                          disabled={pushingToSplitser === split.id}
                          onClick={() => pushToSplitser(split.id)}
                        >
                          {pushingToSplitser === split.id ? 'Pushing…' : 'Submit to Splitser'}
                        </button>
                        <button className="danger" onClick={() => deleteSplit(split.id)}>Delete</button>
                      </>
                    )}
                  </div>
                </div>

                <p className="muted" style={{ marginBottom: '0.75rem' }}>Housemates: {names || '—'}</p>

                {splitProducts.map((p) => {
                  const sp = split.products.find((x) => x.product_id === p.id)
                  const effectiveTotal = (p.amount ?? p.price ?? 0) + (sp?.discount_amount ?? p.discount_amount ?? 0)
                  const unitCost = effectiveTotal / (p.quantity || 1)
                  const displayQty = sp?.quantity != null ? sp.quantity : p.quantity
                  const displayCost = sp?.quantity != null
                    ? unitCost * sp.quantity
                    : effectiveTotal
                  return (
                    <div key={p.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.1rem 0', fontSize: '0.9rem' }}>
                      <span>
                        {p.name}
                        {displayQty != null && displayQty !== 1 && (
                          <span className="muted" style={{ marginLeft: '0.35rem' }}>×{displayQty}</span>
                        )}
                        {(sp?.discount_amount ?? p.discount_amount ?? 0) !== 0 && (
                          <span className="badge" style={{ marginLeft: '0.35rem', background: '#e8f5e9', color: '#1c7a4b' }} title={`Discount: €${(sp?.discount_amount ?? p.discount_amount ?? 0).toFixed(2)}`}>
                            disc.
                          </span>
                        )}
                      </span>
                      <span>€{displayCost.toFixed(2)}</span>
                    </div>
                  )
                })}

                <div style={{ marginTop: '0.75rem', paddingTop: '0.6rem', borderTop: '1px solid #f0f0f0' }}>
                  <span className="muted" style={{ fontSize: '0.85rem' }}>Total </span>
                  <strong>€{split.total.toFixed(2)}</strong>
                  {split.override_amount != null && (
                    <span className="muted" style={{ fontSize: '0.8rem', marginLeft: '0.4rem' }}>(overridden from €{split.calculated_total.toFixed(2)})</span>
                  )}
                </div>
                {split.roommates.length > 0 && (
                  <p className="muted" style={{ marginTop: '0.2rem', fontSize: '0.85rem' }}>
                    {split.roommates.map((r) => `${r.roommate_name}: €${r.amount.toFixed(2)}`).join(' · ')}
                  </p>
                )}

                {/* Paid by */}
                <div style={{ marginTop: '0.75rem', display: 'flex', gap: '0.5rem', alignItems: 'center', fontSize: '0.85rem' }}>
                  <span className="muted" style={{ whiteSpace: 'nowrap' }}>Paid by</span>
                  <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                    <select
                      value={splitPaidBy[split.id] ?? ''}
                      onChange={(e) => setSplitPaidBy((prev) => ({ ...prev, [split.id]: e.target.value ? Number(e.target.value) : null }))}
                      style={{ fontSize: '0.8rem', padding: '0.25rem 0.4rem', borderColor: !splitPaidBy[split.id] ? '#e53e3e' : undefined }}
                    >
                      <option value="" disabled>Select payer…</option>
                      {roommates.map((r) => (
                        <option key={r.id} value={r.id}>{r.name}</option>
                      ))}
                    </select>
                    {!splitPaidBy[split.id] && (
                      <span style={{ color: '#e53e3e', fontSize: '0.75rem' }}>Select a payer before pushing to Splitser</span>
                    )}
                  </div>
                </div>

                {/* Override amount */}
                <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max={split.calculated_total}
                    placeholder={`Override (max €${split.calculated_total.toFixed(2)})`}
                    value={overrideVal}
                    onChange={(e) => setSplitOverrides((prev) => ({ ...prev, [split.id]: e.target.value }))}
                    style={{ flex: 1, fontSize: '0.8rem', padding: '0.3rem 0.5rem' }}
                  />
                  <button
                    style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
                    disabled={overrideInvalid || savingOverride === split.id}
                    onClick={() => saveOverride(split.id)}
                    title={overrideInvalid ? `Must be ≤ €${split.calculated_total.toFixed(2)}` : ''}
                  >
                    {savingOverride === split.id ? '…' : 'Save'}
                  </button>
                  {overrideInvalid && (
                    <span style={{ color: '#c00', fontSize: '0.78rem' }}>max €{split.calculated_total.toFixed(2)}</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* ── Right: create new split ── */}
        <div>
          <h2 style={{ fontSize: '1.5rem', marginBottom: '1rem' }}>Create new split</h2>

          <p style={{ fontWeight: 600, marginBottom: '0.35rem', fontSize: '0.9rem' }}>Label (optional)</p>
          <input
            type="text"
            placeholder="e.g. Dinner Tuesday"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            style={{ marginBottom: '1.25rem' }}
          />

          <p style={{ fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.9rem' }}>Products</p>
          <table style={{ marginBottom: '1.25rem', background: '#fff', border: '1px solid #e5e5e5', borderRadius: 8 }}>
            <thead>
              <tr style={{ background: '#f5f5f5' }}>
                <th style={{ width: 36, padding: '0.5rem 0.75rem' }}>
                  {(() => {
                    const available = products.filter((p) => !allocatedIds.has(p.id))
                    const allSelected = available.length > 0 && available.every((p) => p.id in selectedProducts)
                    return (
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={() => {
                          if (allSelected) {
                            setSelectedProducts({})
                          } else {
                            const next = {}
                            available.forEach((p) => { next[p.id] = null })
                            setSelectedProducts(next)
                          }
                        }}
                        title={allSelected ? 'Deselect all' : 'Select all'}
                      />
                    )
                  })()}
                </th>
                <th>Product</th>
                <th style={{ textAlign: 'right' }}>Qty</th>
                <th style={{ textAlign: 'right' }}>Price</th>
              </tr>
            </thead>
            <tbody>
              {products.map((p) => {
                const allocated = allocatedIds.has(p.id)
                const isSelected = p.id in selectedProducts
                const splitQty = selectedProducts[p.id]
                const hasMultiple = (p.quantity || 1) > 1
                return (
                  <tr key={p.id} style={{ opacity: allocated ? 0.55 : 1 }}>
                    <td style={{ padding: '0.4rem 0.75rem' }}>
                      <input
                        id={`product-${p.id}`}
                        type="checkbox"
                        checked={isSelected}
                        disabled={allocated}
                        onChange={() => toggleProduct(p.id)}
                      />
                    </td>
                    <td>
                      <label htmlFor={`product-${p.id}`} style={{ cursor: allocated ? 'default' : 'pointer' }}>
                      {p.name}</label>
                      {allocated && (
                        <span className="badge" style={{ marginLeft: '0.4rem', color: '#666' }}>allocated</span>
                      )}
                      {p.indicator_name && (
                        <span className="badge" style={{ marginLeft: '0.4rem', background: '#e8f5e9', color: '#1c7a4b' }}>
                          {p.indicator_name}
                        </span>
                      )}
                      {p.matched_discounts?.length > 0 && (
                        <span className="badge" style={{ marginLeft: '0.4rem', background: '#fff3e0', color: '#e65100' }} title={p.matched_discounts.join(', ')}>
                          discount
                        </span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {isSelected && hasMultiple ? (
                        <input
                          type="number"
                          min={1}
                          max={p.quantity}
                          step={1}
                          value={splitQty ?? p.quantity}
                          onChange={(e) => setProductQty(p.id, Number(e.target.value) || null)}
                          style={{ width: 56, textAlign: 'right', padding: '0.2rem 0.4rem', fontSize: '0.85rem' }}
                        />
                      ) : (
                        <span className="muted">{p.quantity ?? 1}</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {p.discount_amount ? (
                        <span>
                          <span className="muted" style={{ textDecoration: 'line-through', marginRight: '0.3rem', fontSize: '0.8rem' }}>
                            €{((p.amount ?? p.price) ?? 0).toFixed(2)}
                          </span>
                          €{((p.amount ?? p.price ?? 0) + p.discount_amount).toFixed(2)}
                        </span>
                      ) : (
                        <span>€{((p.amount ?? p.price) ?? 0).toFixed(2)}</span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          <p style={{ fontWeight: 600, marginBottom: '0.5rem', fontSize: '0.9rem' }}>Housemates</p>
          {roommates.length === 0 ? (
            <p className="muted" style={{ marginBottom: '1rem' }}>No roommates defined yet.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem', marginBottom: '1.25rem' }}>
              {roommates.map((rm) => (
                <label key={rm.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer', fontSize: '0.95rem' }}>
                  <input
                    type="checkbox"
                    checked={selectedRoommateIds.includes(rm.id)}
                    onChange={() => toggleRoommate(rm.id)}
                  />
                  {rm.name}
                </label>
              ))}
            </div>
          )}

          <p style={{ fontWeight: 600, marginBottom: '0.35rem', fontSize: '0.9rem' }}>Paid by</p>
          <select
            value={newPaidBy ?? ''}
            onChange={(e) => setNewPaidBy(e.target.value ? Number(e.target.value) : null)}
            style={{ marginBottom: newPaidBy ? '1.25rem' : '0.25rem', borderColor: !newPaidBy ? '#e53e3e' : undefined }}
          >
            <option value="" disabled>Select payer…</option>
            {roommates.map((rm) => (
              <option key={rm.id} value={rm.id}>{rm.name}</option>
            ))}
          </select>
          {!newPaidBy && (
            <p style={{ color: '#e53e3e', fontSize: '0.8rem', marginBottom: '1rem', marginTop: 0 }}>Select a payer before pushing to Splitser</p>
          )}

          <p style={{ fontWeight: 600, marginBottom: '0.35rem', fontSize: '0.9rem' }}>Override amount (optional)</p>
          <input
            type="number"
            step="0.01"
            min="0"
            placeholder="Leave empty to use product totals"
            value={overrideInput}
            onChange={(e) => setOverrideInput(e.target.value)}
            style={{ marginBottom: '1.25rem' }}
          />

          <button
            className="primary"
            onClick={createSplit}
            disabled={saving || Object.keys(selectedProducts).length === 0 || selectedRoommateIds.length === 0}
            style={{ width: '100%', padding: '0.6rem' }}
          >
            {saving ? 'Creating…' : 'Create split'}
          </button>
        </div>

      </div>

      {receipt.discounts.length > 0 && (
        <div className="card" style={{ marginTop: '2rem' }}>
          <h2>Discounts</h2>
          <table>
            <thead><tr><th>Name</th><th>Type</th><th style={{ textAlign: 'right' }}>Amount</th></tr></thead>
            <tbody>
              {receipt.discounts.map((d, i) => (
                <tr key={i}>
                  <td>{d.name}</td>
                  <td><span className="badge">{d.type}</span></td>
                  <td style={{ textAlign: 'right' }}>{d.amount != null ? `€${d.amount.toFixed(2)}` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
