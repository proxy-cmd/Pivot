import { Database, Settings } from 'lucide-react'

export default function Sidebar({ data, nav, page, setPage, reset }) {
  return <aside className="app-sidebar">
    <div className="app-logo"><span>✕</span>PIVOT</div>
    <button className="dataset-picker" onClick={reset}><Database size={16}/><div><b>{data.file_name}</b><small>{data.rows.toLocaleString()} rows · {data.columns} columns</small></div><i>›</i></button>
    <p className="nav-caption">WORKSPACE</p>
    <nav className="app-nav">{nav.map(item => <button key={item} className={page === item ? 'selected' : ''} onClick={() => setPage(item)}>{item}</button>)}</nav>
    <button className="settings-link" onClick={() => setPage('Settings')}><Settings size={15}/>Settings</button>
  </aside>
}
