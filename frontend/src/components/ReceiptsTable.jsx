import { Link, useLocation } from 'react-router-dom'

function formatAddress(address) {
  if (!address) return null
  const line1 = [address.street, address.house_number].filter(Boolean).join(' ')
  const line2 = [address.postal_code, address.city].filter(Boolean).join(' ')
  return [line1, line2].filter(Boolean).join(', ') || null
}

export default function ReceiptsTable({ receipts }) {
  const location = useLocation()
  return (
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Store</th>
          <th>Address</th>
          <th>Total</th>
          <th>Koopzegels</th>
          <th>Splits</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {receipts.map((r) => (
          <tr key={r.id}>
            <td>{r.date_time ? new Date(r.date_time).toLocaleDateString('nl-NL') : '—'}</td>
            <td className="muted">{r.store_info ?? '—'}</td>
            <td className="muted">{formatAddress(r.address) ?? '—'}</td>
            <td>€ {r.total_amount?.toFixed(2) ?? '—'}</td>
            <td className="muted">
              {r.stamps?.quantity > 0
                ? (r.koopzegel_buyer?.name ?? '✕')
                : '—'}
            </td>
            <td className="muted">
              {r.has_splits ? `${r.split_product_count}/${r.product_count}` : '—'}
            </td>
            <td><Link to={`/receipts/${r.id}`} state={{ from: location.pathname + location.search }}>View →</Link></td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
