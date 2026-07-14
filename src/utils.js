export function formatMoney(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

export function parseCsv(text) {
  const rows = text.trim().split(/\r?\n/).map((line) => line.split(',').map((cell) => cell.trim().replace(/^"|"$/g, '')))
  if (rows.length < 2) return { headers: [], rows: [] }
  return { headers: rows[0], rows: rows.slice(1) }
}

export function inferDataset(headers) {
  const fields = headers.map((field) => field.toLowerCase())
  if (fields.some((field) => /order|revenue|sale|price|amount/.test(field))) return 'Sales & orders'
  if (fields.some((field) => /stock|inventory|sku|warehouse/.test(field))) return 'Inventory'
  if (fields.some((field) => /customer|email|company|segment/.test(field))) return 'Customers'
  if (fields.some((field) => /expense|cost|vendor|invoice/.test(field))) return 'Expenses'
  return 'Operational data'
}
