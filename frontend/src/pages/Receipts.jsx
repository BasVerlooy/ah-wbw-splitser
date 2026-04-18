import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import ReceiptsTable from '../components/ReceiptsTable'

const PAGE_SIZE = 25

function toTitleCase(str) {
  if (!str) return str
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase()
}

function StoreCombobox({ stores, value, onChange }) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const containerRef = useRef(null)
  const inputRef = useRef(null)

  const selected = stores.find((s) => s.storeInfo === value)
  const displayLabel = selected ? selected.label : ''

  const filtered = useMemo(() => {
    const q = search.toLowerCase()
    return q ? stores.filter((s) => s.label.toLowerCase().includes(q)) : stores
  }, [stores, search])

  // Close on outside click
  useEffect(() => {
    function onPointerDown(e) {
      if (!containerRef.current?.contains(e.target)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [])

  function handleOpen() {
    setSearch('')
    setOpen(true)
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  function handleSelect(storeInfo) {
    onChange(storeInfo)
    setOpen(false)
    setSearch('')
  }

  return (
    <div ref={containerRef} style={{ position: 'relative', flex: '0 0 auto', minWidth: 220 }}>
      {/* Trigger */}
      <button
        type="button"
        onClick={open ? () => setOpen(false) : handleOpen}
        style={{
          width: '100%', textAlign: 'left', padding: '0.4rem 2rem 0.4rem 0.6rem',
          border: '1px solid #ccc', borderRadius: 6, fontSize: '0.875rem',
          background: '#fff', cursor: 'pointer', position: 'relative',
          color: value ? 'inherit' : '#888', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}
      >
        {value ? displayLabel : 'All stores'}
        <span style={{ position: 'absolute', right: '0.5rem', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: '#888' }}>▾</span>
      </button>

      {open && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, zIndex: 100,
          background: '#fff', border: '1px solid #ccc', borderRadius: 6,
          boxShadow: '0 4px 12px rgba(0,0,0,0.1)', overflow: 'hidden',
        }}>
          <div style={{ padding: '0.4rem' }}>
            <input
              ref={inputRef}
              type="search"
              placeholder="Search store…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: '100%', marginBottom: 0 }}
            />
          </div>
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', maxHeight: 260, overflowY: 'auto' }}>
            <li
              onPointerDown={() => handleSelect('')}
              style={{
                padding: '0.45rem 0.75rem', cursor: 'pointer', fontSize: '0.875rem',
                background: value === '' ? '#f0f0f0' : 'transparent',
                fontStyle: 'italic', color: '#666',
              }}
            >
              All stores
            </li>
            {filtered.map((s) => (
              <li
                key={s.storeInfo}
                onPointerDown={() => handleSelect(s.storeInfo)}
                style={{
                  padding: '0.45rem 0.75rem', cursor: 'pointer', fontSize: '0.875rem',
                  background: value === s.storeInfo ? '#f0f0f0' : 'transparent',
                }}
                onMouseEnter={(e) => { if (value !== s.storeInfo) e.currentTarget.style.background = '#fafafa' }}
                onMouseLeave={(e) => { if (value !== s.storeInfo) e.currentTarget.style.background = 'transparent' }}
              >
                {s.label}
              </li>
            ))}
            {filtered.length === 0 && (
              <li style={{ padding: '0.45rem 0.75rem', color: '#888', fontSize: '0.875rem' }}>No results</li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}

export default function Receipts() {
  const [receipts, setReceipts] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchParams, setSearchParams] = useSearchParams()

  const store = searchParams.get('store') ?? ''
  const query = searchParams.get('q') ?? ''
  const page = parseInt(searchParams.get('page') ?? '1', 10)

  function setPage(p) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (p > 1) next.set('page', String(p)); else next.delete('page')
      return next
    }, { replace: true })
  }

  useEffect(() => {
    api.get('/receipts')
      .then(setReceipts)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const stores = useMemo(() => {
    const seen = new Map()
    for (const r of receipts) {
      if (r.store_info && !seen.has(r.store_info)) {
        seen.set(r.store_info, toTitleCase(r.address?.city) ?? '—')
      }
    }
    return [...seen.entries()]
      .map(([storeInfo, city]) => ({ storeInfo, city, label: `${city} (${storeInfo})` }))
      .sort((a, b) => a.city.localeCompare(b.city) || a.storeInfo.localeCompare(b.storeInfo))
  }, [receipts])

  const filtered = useMemo(() => {
    let result = store ? receipts.filter((r) => r.store_info === store) : receipts
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      result = result.filter((r) => {
        const date = r.date_time ? new Date(r.date_time).toLocaleDateString('nl-NL') : ''
        return (
          r.store_info?.toLowerCase().includes(q) ||
          r.address?.city?.toLowerCase().includes(q) ||
          r.address?.street?.toLowerCase().includes(q) ||
          r.address?.postal_code?.toLowerCase().includes(q) ||
          date.includes(q) ||
          r.total_amount?.toFixed(2).includes(q)
        )
      })
    }
    return result
  }, [receipts, store, query])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageReceipts = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  function handleStoreChange(val) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (val) next.set('store', val); else next.delete('store')
      next.delete('page')
      return next
    }, { replace: true })
  }

  function handleQueryChange(e) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (e.target.value) next.set('q', e.target.value); else next.delete('q')
      next.delete('page')
      return next
    }, { replace: true })
  }

  if (loading) return <p className="muted">Loading…</p>

  return (
    <div>
      <h1>Receipts</h1>

      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <input
          type="search"
          placeholder="Search date, city, street, total…"
          value={query}
          onChange={handleQueryChange}
          style={{ flex: '1 1 200px', minWidth: 160, width: 'auto' }}
        />
        <StoreCombobox stores={stores} value={store} onChange={handleStoreChange} />
        <span className="muted" style={{ whiteSpace: 'nowrap' }}>{filtered.length} receipt{filtered.length !== 1 ? 's' : ''}</span>
      </div>

      {filtered.length === 0 ? (
        <p className="muted">No receipts found.</p>
      ) : (
        <div className="card">
          <ReceiptsTable receipts={pageReceipts} />

          {totalPages > 1 && (
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', marginTop: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
              <button onClick={() => setPage(1)} disabled={currentPage === 1}>«</button>
              <button onClick={() => setPage(currentPage - 1)} disabled={currentPage === 1}>‹</button>
              <span className="muted" style={{ padding: '0 0.5rem' }}>
                Page {currentPage} of {totalPages}
              </span>
              <button onClick={() => setPage(currentPage + 1)} disabled={currentPage === totalPages}>›</button>
              <button onClick={() => setPage(totalPages)} disabled={currentPage === totalPages}>»</button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
