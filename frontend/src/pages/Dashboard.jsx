import { useEffect, useState } from 'react'
import { api } from '../api'
import ReceiptsTable from '../components/ReceiptsTable'

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000

export default function Dashboard() {
  const [summary, setSummary] = useState(null)
  const [recentReceipts, setRecentReceipts] = useState([])
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)
  const [nextOffset, setNextOffset] = useState(null)
  const [error, setError] = useState(null)
  const [pushing, setPushing] = useState(false)
  const [pushResult, setPushResult] = useState(null)
  const [pushError, setPushError] = useState(null)

  async function loadData() {
    const [sum, receipts] = await Promise.all([
      api.get('/summary'),
      api.get('/receipts'),
    ])
    setSummary(sum)
    const cutoff = Date.now() - SEVEN_DAYS_MS
    setRecentReceipts(receipts.filter((r) => new Date(r.date_time).getTime() >= cutoff))
  }

  useEffect(() => { loadData().catch(console.error) }, [])

  async function handlePushAll() {
    setPushing(true)
    setPushResult(null)
    setPushError(null)
    try {
      const result = await api.post('/push-all-to-splitser')
      setPushResult(result)
      await loadData()
    } catch (e) {
      setPushError(e.message)
    } finally {
      setPushing(false)
    }
  }

  async function handleSync(offset = 0) {
    setSyncing(true)
    setError(null)
    try {
      const result = await api.post(`/sync?offset=${offset}`)
      setSyncResult(result)
      setNextOffset(result.has_more ? result.next_offset : null)
      await loadData()
    } catch (e) {
      setError(e.message)
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div>
      <h1>Dashboard</h1>

      <div className="card">
        <h2>Sync receipts</h2>
        <p className="muted" style={{ marginBottom: '0.75rem' }}>
          Fetches the latest receipts from Albert Heijn and stores new ones in the database.
        </p>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button className="primary" onClick={() => handleSync(0)} disabled={syncing}>
            {syncing ? 'Syncing…' : 'Sync now'}
          </button>
          {nextOffset != null && (
            <button onClick={() => handleSync(nextOffset)} disabled={syncing}>
              Sync earlier receipts
            </button>
          )}
        </div>
        {syncResult && (
          <p className="muted" style={{ marginTop: '0.5rem' }}>
            Done — {syncResult.synced} new, {syncResult.skipped} skipped (total {syncResult.total}
            {syncResult.total_available > 0 && `, ${syncResult.total_available} on AH`})
            {syncResult.has_more && ' — more available'}
          </p>
        )}
        {error && <p style={{ color: '#c00', marginTop: '0.5rem' }}>{error}</p>}
      </div>

      <div className="card">
        <h2>Last 7 days</h2>
        {recentReceipts.length === 0 ? (
          <p className="muted">No receipts in the last 7 days.</p>
        ) : (
          <ReceiptsTable receipts={recentReceipts} />
        )}
      </div>

      <div className="card">
        <h2>Splits</h2>
        {summary == null ? (
          <p className="muted">Loading…</p>
        ) : summary.total_splits === 0 ? (
          <p className="muted">No splits configured yet.</p>
        ) : (
          <>
            <table style={{ marginBottom: '0.75rem' }}>
              <tbody>
                <tr>
                  <td>Total splits</td>
                  <td><strong>{summary.total_splits}</strong></td>
                </tr>
                <tr>
                  <td>Pushed to Splitser</td>
                  <td><strong>{summary.pushed_splits}</strong></td>
                </tr>
                <tr>
                  <td>Not yet pushed</td>
                  <td><strong>{summary.unpushed_splits}</strong></td>
                </tr>
              </tbody>
            </table>
            {summary.unpushed_splits > 0 && (
              <div>
                <button className="primary" onClick={handlePushAll} disabled={pushing}>
                  {pushing ? 'Pushing…' : `Push ${summary.unpushed_splits} unpushed split${summary.unpushed_splits !== 1 ? 's' : ''} to Splitser`}
                </button>
                {pushResult && (
                  <p className="muted" style={{ marginTop: '0.5rem' }}>
                    Done — {pushResult.pushed} pushed
                    {pushResult.failed.length > 0 && `, ${pushResult.failed.length} failed: ${pushResult.failed.map(f => f.name).join(', ')}`}
                  </p>
                )}
                {pushError && <p style={{ color: '#c00', marginTop: '0.5rem' }}>{pushError}</p>}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
