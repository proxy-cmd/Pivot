export default function DataTable({ columns = [], rows = [], title = 'Data preview' }) {
  return <section className="data-table"><div className="table-title"><b>{title}</b><span>{rows.length} displayed rows</span></div><div className="table-scroll"><table><thead><tr>{columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map(column => <td key={column}>{String(row[column] ?? '')}</td>)}</tr>)}</tbody></table></div></section>
}
