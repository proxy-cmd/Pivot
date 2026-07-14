import { useMemo, useRef, useState } from 'react'
import {
  Activity, ArrowDownRight, ArrowUpRight, BarChart3, Bell, Bot, CalendarDays, ChevronRight,
  CircleHelp, CloudUpload, Download, FileSpreadsheet, Gauge, LayoutDashboard, Moon, MoreHorizontal,
  Package, PanelLeftClose, Search, Send, Settings, ShieldCheck, Sparkles, Sun, Target, Users,
} from 'lucide-react'
import { Area, AreaChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { findings, notes, revenue, segments } from './data'
import { formatMoney, inferDataset, parseCsv } from './utils'

const api = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const nav = [
  [LayoutDashboard, 'Overview'], [Activity, 'Health score'], [BarChart3, 'Explore'],
  [Target, 'Forecasts'], [Package, 'Simulator'], [FileSpreadsheet, 'Reports'],
]

function Stat({ label, value, change, down }) {
  return <article className="stat-card">
    <span>{label}</span><strong>{value}</strong>
    <small className={down ? 'down' : 'up'}>{down ? <ArrowDownRight size={14} /> : <ArrowUpRight size={14} />}{change} <i>vs last period</i></small>
  </article>
}

function App() {
  const [active, setActive] = useState('Overview')
  const [dark, setDark] = useState(false)
  const [panel, setPanel] = useState(false)
  const [upload, setUpload] = useState(null)
  const [scenario, setScenario] = useState({ price: 0, marketing: 0, costs: 0 })
  const [scenarioResult, setScenarioResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('Ask a question about your business. I’ll ground the answer in the data currently on screen.')
  const fileRef = useRef()
  const projection = useMemo(() => scenarioResult?.revenue || 238000 * (1 + scenario.price / 100 + scenario.marketing / 200 - scenario.costs / 150), [scenario, scenarioResult])

  async function handleUpload(file) {
    if (!file) return
    setBusy(true)
    try {
      const form = new FormData(); form.append('file', file)
      const response = await fetch(`${api}/api/profile`, { method: 'POST', body: form })
      if (response.ok) {
        const result = await response.json()
        setUpload({ id: result.dataset_id, name: result.file_name, rows: result.rows, headers: Array(result.columns).fill('field'), type: result.role, quality: result.quality_score, issues: result.issues, recommendations: result.recommendations })
        setPanel(false); setBusy(false); return
      }
    } catch { /* API is optional in front-end demo mode */ }
    const reader = new FileReader()
    reader.onload = () => {
      const data = parseCsv(String(reader.result))
      setUpload({ name: file.name, rows: data.rows.length, headers: data.headers, type: inferDataset(data.headers), quality: 84, issues: [] })
      setPanel(false)
      setBusy(false)
    }
    reader.readAsText(file)
  }

  async function updateScenario(next) {
    setScenario(next)
    try {
      const response = await fetch(`${api}/api/scenario`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ price_change: next.price, marketing_change: next.marketing, cost_change: next.costs }) })
      if (response.ok) setScenarioResult(await response.json())
    } catch { setScenarioResult(null) }
  }

  async function ask() {
    const text = question.trim().toLowerCase()
    if (!text) return
    setBusy(true)
    try {
      const response = await fetch(`${api}/api/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, dataset_id: upload?.id, context: { revenue: 238000, revenue_growth: '10.2%', gross_margin: '38.4%', margin_change: '-1.8 points', shipping_cost_growth: '18%', data_quality: upload?.quality } }) })
      if (response.ok) { setAnswer((await response.json()).answer); setQuestion(''); setBusy(false); return }
    } catch { /* fall back to local concise answers */ }
    if (text.includes('profit') || text.includes('margin')) setAnswer('Profitability softened because fulfillment costs increased 18% while revenue rose 11%. The West region creates 42% of the shipping increase. Renegotiating carrier rates there is the highest-impact next action.')
    else if (text.includes('churn') || text.includes('customer')) setAnswer('Customer health remains positive: repeat buyers drive 54% of revenue. Eighteen accounts show lower engagement and should receive a targeted retention touchpoint before their next renewal window.')
    else setAnswer('Revenue is trending up and expected to finish 12% above last quarter. The main constraint is margin pressure from shipping and returns; see the insights panel for the supporting signals.')
    setQuestion('')
    setBusy(false)
  }

  function exportReport() {
    const report = `VERDANT / BUSINESS HEALTH BRIEF\n\nHealth score: 82 / 100\nRevenue: $238,000 (+10.2%)\nGross margin: 38.4% (-1.8 pts)\n\nKey finding\nFulfillment costs grew 18% while revenue grew 11%.\n\nRecommended action\nReview West-region carrier contracts and protect repeat customers with a loyalty offer.`
    const blob = new Blob([report], { type: 'text/plain' })
    const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = 'verdant-health-brief.txt'; link.click(); URL.revokeObjectURL(link.href)
  }

  return <div className={dark ? 'app dark' : 'app'}>
    <aside className="sidebar">
      <div className="brand"><span>V</span><b>verdant</b></div>
      <div className="workspace"><div className="avatar">FN</div><div><b>Field Notes</b><small>Growth workspace</small></div><ChevronRight size={16} /></div>
      <nav>{nav.map(([Icon, item]) => <button key={item} className={active === item ? 'selected' : ''} onClick={() => setActive(item)}><Icon size={18} />{item}</button>)}</nav>
      <div className="sidebar-foot"><button><Settings size={18} />Settings</button><button><CircleHelp size={18} />Help centre</button><div className="profile"><div className="avatar peach">AK</div><div><b>Amelia King</b><small>Owner</small></div><MoreHorizontal size={17} /></div></div>
    </aside>

    <main>
      <header>
        <div className="crumb"><span>Overview</span><small>Tuesday, 14 July</small></div>
        <div className="head-actions"><button className="icon-btn" onClick={() => setDark(!dark)}>{dark ? <Sun size={18} /> : <Moon size={18} />}</button><button className="icon-btn"><Bell size={18} /><i /></button><button className="upload-btn" onClick={() => setPanel(true)}><CloudUpload size={17} />Add data</button></div>
      </header>
      <section className="intro"><div><p className="eyebrow">YOUR BUSINESS, AT A GLANCE</p><h1>Good morning, Amelia.</h1><p className="sub">Here’s the clearest picture of your business right now.</p></div><button className="date"><CalendarDays size={16} />Last 30 days <ChevronRight size={15} /></button></section>

      {upload && <section className="data-banner"><ShieldCheck size={18}/><div><b>{upload.type} is ready for analysis</b><span>{upload.rows} records · Data quality {upload.quality}/100 · {upload.issues?.length || 0} quality signals detected</span></div><button onClick={() => setActive('Explore')}>Review profile <ChevronRight size={15}/></button></section>}
      <section className="health-row">
        <article className="health-card"><div className="card-title"><span>Business health</span><button><MoreHorizontal size={18} /></button></div><div className="health-main"><div className="score"><svg viewBox="0 0 120 120"><circle cx="60" cy="60" r="49"/><circle className="meter" cx="60" cy="60" r="49"/></svg><div><strong>82</strong><small>/100</small></div></div><div><h2>Looking healthy</h2><p>Your growth is steady. Margin pressure is the one area worth addressing this month.</p><button className="text-btn" onClick={() => setActive('Health score')}>See score details <ChevronRight size={15} /></button></div></div><div className="pill-row"><span><b>↑</b> Growth strong</span><span><b>!</b> Margin watch</span><span><b>✓</b> Customers solid</span></div></article>
        <article className="brief-card"><div className="card-title"><span>Executive brief</span><Sparkles size={17} /></div><h3>One minute read</h3>{notes.map((note) => <p key={note}><span>•</span>{note}</p>)}<button className="brief-link" onClick={exportReport}>Download brief <Download size={15} /></button></article>
      </section>

      <section className="stat-grid"><Stat label="Revenue" value="$238,000" change="10.2%"/><Stat label="Gross margin" value="38.4%" change="1.8 pts" down/><Stat label="Active customers" value="1,284" change="6.4%"/><Stat label="Avg. order value" value="$186" change="4.1%"/></section>

      <section className="grid-main"><article className="chart-card"><div className="card-title"><div><span>Revenue trend</span><p>{formatMoney(238000)} <b>↑ 10.2%</b></p></div><button className="plain">Revenue <ChevronRight size={14} /></button></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={revenue} margin={{ top: 12, right: 5, bottom: 0, left: -24 }}><defs><linearGradient id="fill" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor="#d77a40" stopOpacity=".28"/><stop offset="100%" stopColor="#d77a40" stopOpacity="0"/></linearGradient></defs><XAxis dataKey="month" axisLine={false} tickLine={false}/><YAxis axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}k`}/><Tooltip formatter={(v) => [`$${v}k`, 'Revenue']}/><Area type="monotone" dataKey="value" stroke="#c96530" strokeWidth={2.5} fill="url(#fill)"/></AreaChart></ResponsiveContainer></div><p className="chart-note">November’s lift is led by returning customers, not discounting.</p></article>
        <article className="segment-card"><div className="card-title"><span>Customer mix</span><button><MoreHorizontal size={18} /></button></div><div className="donut"><ResponsiveContainer width={150} height={150}><PieChart><Pie data={segments} dataKey="value" innerRadius={48} outerRadius={66} paddingAngle={3}>{segments.map((item) => <Cell key={item.name} fill={item.color}/>)}</Pie></PieChart></ResponsiveContainer><div><strong>1,284</strong><small>active customers</small></div></div><div className="legend">{segments.map((item) => <p key={item.name}><i style={{ background: item.color }}/>{item.name}<b>{item.value}%</b></p>)}</div></article>
      </section>

      <section className="insight-section"><div className="section-title"><div><p className="eyebrow">WHAT NEEDS ATTENTION</p><h2>Signals worth acting on</h2></div><button className="text-btn">View all insights <ChevronRight size={15}/></button></div><div className="finding-grid">{findings.map((item) => <article className={`finding ${item.type}`} key={item.title}><div className="finding-icon">{item.type === 'risk' ? <ShieldCheck size={18}/> : item.type === 'opportunity' ? <Sparkles size={18}/> : <Package size={18}/>}</div><small>{item.type}</small><h3>{item.title}</h3><p>{item.body}</p><button>{item.action} <ChevronRight size={15}/></button></article>)}</div></section>

      <section className="bottom-grid"><article className="simulator"><div><p className="eyebrow">DECISION LAB</p><h2>Test a move before you make it.</h2><p>Adjust the levers and see the likely revenue effect.</p></div><div className="sliders">{[['Price change', 'price'], ['Marketing spend', 'marketing'], ['Supplier costs', 'costs']].map(([label, key]) => <label key={key}>{label}<b>{scenario[key] > 0 ? '+' : ''}{scenario[key]}%</b><input type="range" min="-15" max="20" value={scenario[key]} onChange={(e) => updateScenario({ ...scenario, [key]: Number(e.target.value) })}/></label>)}</div><div className="projection"><small>PROJECTED MONTHLY REVENUE</small><strong>{formatMoney(projection)}</strong><span><ArrowUpRight size={14}/> {scenarioResult?.change ?? ((projection / 238000 - 1) * 100).toFixed(1)}% from baseline</span></div></article>
        <article className="consultant"><div className="consultant-head"><div className="bot"><Bot size={18}/></div><div><b>Pivot analyst <i className="live-dot"/></b><small>{upload?.id ? 'Grounded in your dataset · live' : 'Evidence-backed answers'}</small></div></div><p className={`answer ${busy ? 'thinking' : ''}`}>{busy ? 'Reading metadata, lineage and relevant records' : answer}</p>{busy && <div className="typing"><i/><i/><i/></div>}<div className="ask"><input value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && ask()} placeholder="Ask about your business..."/><button onClick={ask}><Send size={16}/></button></div></article></section>
    </main>

    {panel && <div className="modal-backdrop" onMouseDown={() => setPanel(false)}><section className="upload-modal" onMouseDown={(e) => e.stopPropagation()}><button className="close" onClick={() => setPanel(false)}>×</button><div className="upload-mark"><CloudUpload size={26}/></div><p className="eyebrow">DATA INTAKE</p><h2>Add a business dataset</h2><p>Drop in CSV or Excel. Verdant profiles the schema, quality risks, keys and business role automatically.</p><button className="dropzone" onClick={() => fileRef.current.click()}><FileSpreadsheet size={24}/><b>{busy ? 'Profiling data…' : 'Choose CSV or Excel'}</b><span>or drag and drop it here</span></button><input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,text/csv" hidden onChange={(e) => handleUpload(e.target.files?.[0])}/>{upload && <div className="upload-result"><b>{upload.name}</b><span>{upload.rows} records · quality {upload.quality}/100 · {upload.type}</span></div>}<small className="supported">Secure API profiling · Excel, CSV supported · Sheets and SQL connectors ready to add</small></section></div>}
    {upload && <div className="toast"><ShieldCheck size={18}/><div><b>{upload.type} detected</b><span>{upload.rows} records ready for analysis</span></div><button onClick={() => setUpload(null)}>×</button></div>}
  </div>
}

export default App
