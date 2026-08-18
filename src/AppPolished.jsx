import { useEffect, useMemo, useRef, useState } from 'react'
import { Activity, AlertCircle, BarChart3, Bell, Bot, Check, CheckCircle2, ChevronDown, ChevronRight, Code2, Command, Database, Download, FileBarChart2, GitBranch, LayoutDashboard, LineChart, LockKeyhole, Menu, Play, Plus, RefreshCw, Rocket, Search, Send, Settings2, ShieldCheck, Sparkles, Table2, UserRound, WandSparkles, X } from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { downloadFile, request } from './api'
import { useAuth } from './auth'

const API = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const NAV = [['Home', LayoutDashboard], ['Data', Table2], ['Analyze', BarChart3], ['Ask Pivot', Bot], ['SQL', Code2], ['Reports', FileBarChart2]]
const text = value => value && typeof value === 'object' ? JSON.stringify(value) : String(value ?? '')
const number = value => typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value ?? '—')
const readJson = key => { try { return JSON.parse(localStorage.getItem(key) || '{}') } catch { return {} } }
const initials = profile => (profile.fullName || profile.name || 'Pivot User').split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase()

function notify(message) { window.dispatchEvent(new CustomEvent('pivot:notice', { detail: text(message) })) }
function normalizeDataset(item) { const profile = item?.profile || item || {}; return { ...item, profile, dataset_id: item?.id || item?.dataset_id, file_name: item?.name || profile.file_name || item?.file_name || 'Untitled dataset', rows: profile.rows ?? item?.rows ?? 0, columns: profile.columns ?? item?.columns ?? 0, quality_score: profile.quality_score ?? item?.quality_score ?? 0 } }
async function download(url) { await downloadFile(url.startsWith('http') ? url : `${API}${url}`) }
function downloadText(name, content, type = 'application/json') { const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([content], { type })); link.download = name; link.click(); URL.revokeObjectURL(link.href) }
function Logo({ light = false }) { return <div className={`logo ${light ? 'logo-light' : ''}`}><span className="logo-mark"><i /><i /></span><b>PIVOT</b></div> }
function Button({ children, variant = 'primary', onClick, disabled = false, type = 'button' }) { return <button type={type} className={`btn btn-${variant}`} onClick={onClick} disabled={disabled}>{children}</button> }
function Badge({ children, tone = 'gray' }) { return <span className={`badge ${tone}`}>{children}</span> }
function Head({ eyebrow, title, copy, action }) { return <div className="page-head"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1>{copy && <p className="page-copy">{copy}</p>}</div>{action}</div> }
function Grid({ columns = [], rows = [] }) { return <div className="grid-scroll"><table><thead><tr>{columns.map(column => <th key={column}>{column}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={index}>{columns.map(column => <td key={column}>{text(row[column])}</td>)}</tr>)}</tbody></table></div> }
function MiniChart({ points = [] }) { const values = points.map(point => Number(point.value) || 0); const max = Math.max(...values, 1); const min = Math.min(...values, 0); const width = 760; const height = 190; const pointsString = points.map((point, index) => `${(index / Math.max(points.length - 1, 1)) * width},${height - ((Number(point.value) - min) / Math.max(max - min, 1)) * 145 - 12}`).join(' '); return <div className="analysis-chart"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Analysis chart"><polyline points={pointsString} fill="none" stroke="#138463" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />{points.map((point, index) => <circle key={index} cx={(index / Math.max(points.length - 1, 1)) * width} cy={height - ((Number(point.value) - min) / Math.max(max - min, 1)) * 145 - 12} r="4" fill="#fff" stroke="#138463" strokeWidth="3" />)}</svg><div className="analysis-chart-labels"><span>{points[0]?.label || ''}</span><span>{points[Math.floor(points.length / 2)]?.label || ''}</span><span>{points[points.length - 1]?.label || ''}</span></div></div> }
function GoogleMark() { return <span className="google-mark">G</span> }

function LandingV2({ start, signIn }) { const [metric, setMetric] = useState('Revenue'); const [grain, setGrain] = useState('Monthly'); const chart = metric === 'Revenue' ? [42, 54, 47, 66, 70, 84, 78, 92] : metric === 'Orders' ? [31, 36, 42, 48, 45, 58, 62, 72] : [26, 34, 31, 39, 43, 38, 50, 57]; return <div className="pivot-landing"><header className="pivot-nav"><Logo light /><nav><a href="#platform">Platform</a><a href="#evidence">Evidence</a><a href="#security">Security</a><a href="#resources">Resources</a></nav><div><button onClick={signIn}>Sign in</button><Button onClick={start}>Get started <ChevronRight size={15}/></Button></div></header><main><section className="pivot-hero"><div className="pivot-grid"/><div className="pivot-hero-copy"><p className="eyebrow">EVIDENCE-FIRST DATA INTELLIGENCE</p><h1>Your data already<br/><em>knows the answer.</em></h1><p>Pivot turns raw business data into a traceable workspace for cleaning, analysis, reporting, and evidence-backed AI.</p><div className="hero-ctas"><Button onClick={start}>Start with your data <ChevronRight size={16}/></Button><button className="text-link" onClick={() => document.getElementById('platform')?.scrollIntoView({ behavior: 'smooth' })}>Explore the workspace <ChevronRight size={14}/></button></div></div><div className="pipeline" aria-label="Pivot data pipeline"><div className="pipeline-head"><span><i/> LIVE WORKSPACE</span><small>ORIGINAL PRESERVED</small></div>{[['Raw file', Database], ['Profile', Table2], ['Quality', ShieldCheck], ['Clean', WandSparkles], ['Analyze', BarChart3], ['Ask', Bot]].map(([label, Icon], i) => <div className={`pipeline-step step-${i}`} key={label}><span><Icon size={17}/></span><b>{label}</b><small>{i === 0 ? 'Source safe' : i === 2 ? 'Issues found' : i === 5 ? 'Evidence linked' : 'Ready'}</small></div>)}<div className="pipeline-orbit"/></div></section><section className="evidence-strip"><span><b>51,290</b> rows profiled</span><span><b>21</b> fields understood</span><span><b>500</b> anomalies detected</span><span><b>0</b> source rows overwritten</span><span><b>12</b> analyses generated</span><span>Every change versioned</span></section><section className="story-section" id="platform"><div className="story-copy"><p className="eyebrow">FROM FILE TO UNDERSTANDING</p><h2>One workspace. Every turn your data takes.</h2><p>Bring the source once. Pivot profiles it, surfaces what needs attention, and keeps every decision tied to evidence.</p><div className="story-list">{['Upload a source that stays untouched', 'Understand fields and data quality', 'Preview changes before a version exists', 'Analyze, ask, and report with lineage'].map((item, i) => <span key={item}><b>0{i + 1}</b>{item}</span>)}</div></div><div className="story-canvas"><small>ACTIVE DATASET / Q2 PERFORMANCE</small><div className="canvas-columns"><span>customer_id</span><span>region</span><span>order_date</span><span>revenue</span><span>margin</span></div><div className="canvas-insight"><i/><div><small>PIVOT NOTICED</small><b>Revenue softened 16% in Central</b><span>Backed by 1,294 source rows</span></div><ChevronRight size={16}/></div><div className="canvas-footer"><span><GitBranch size={14}/> Version 3 active</span><span><CheckCircle2 size={14}/> Evidence attached</span></div></div></section><section className="proof-section" id="evidence"><div><p className="eyebrow">YOUR DATA, NOT OUR ASSUMPTIONS</p><h2>Answers you can inspect.</h2><p>Pivot does not ask you to trust a black box. Every answer travels with its fields, calculation, source version, and supporting rows.</p></div><div className="proof-chain"><span>Question</span><i/><span>Fields</span><i/><span>Calculation</span><i/><span className="result">Result</span><i/><span>Evidence</span></div></section><section className="playground"><div className="playground-head"><div><p className="eyebrow">INTERACTIVE ANALYTICS PLAYGROUND</p><h2>Signal, not dashboard noise.</h2></div><div className="playground-controls"><div>{['Revenue', 'Orders', 'Margin'].map(item => <button className={metric === item ? 'active' : ''} onClick={() => setMetric(item)} key={item}>{item}</button>)}</div><div>{['Monthly', 'Quarterly', 'Yearly'].map(item => <button className={grain === item ? 'active' : ''} onClick={() => setGrain(item)} key={item}>{item}</button>)}</div></div></div><div className="demo-chart"><div className="chart-y"><span>$100k</span><span>$50k</span><span>$0</span></div><div className="chart-area">{chart.map((value, index) => <i key={index} style={{height: `${value}%`}} title={`${metric}: ${value}`}/>)}</div></div><small className="demo-note">Marketing demo data · {metric} by {grain.toLowerCase()}</small></section><section className="quality-section"><div className="scan-visual"><i/><i/><i/><i/><i/><span>SCANNING</span></div><div><p className="eyebrow">DATA HEALTH SCAN</p><h2>Find the problems before they become decisions.</h2><p>Missing values, duplicates, outliers, invalid dates, and format inconsistencies are made visible before they reach an analysis.</p><Button variant="outline" onClick={start}>See your data health <ChevronRight size={14}/></Button></div></section><section className="dark-cta" id="security"><p className="eyebrow">BUILT FOR REAL DATA WORK</p><h2>Stop cleaning the same spreadsheet twice.</h2><p>Original sources stay preserved. Every approved change becomes a traceable version.</p><Button onClick={start}>Bring your data <ChevronRight size={16}/></Button></section></main><footer className="pivot-footer" id="resources"><Logo/><span>Product · Resources · Security · Documentation</span><span>© 2026 Pivot</span></footer></div> }

function Landing({ start, signIn }) { return <div className="landing-shell"><div className="landing-hero"><div className="ambient ambient-one" /><div className="ambient ambient-two" /><header className="landing-header content-width"><Logo light /><nav className="landing-nav"><a href="#product">Product</a><a href="#solutions">Solutions</a><a href="#product">Resources</a><a href="#solutions">Docs</a></nav><div className="landing-actions"><button className="signin" onClick={signIn}>Sign in</button><Button onClick={start}>Get started free <ChevronRight size={15} /></Button></div><button className="mobile-menu" aria-label="Menu"><Menu size={21} /></button></header><section className="hero-content content-width"><div className="hero-copy"><div className="hero-kicker"><Sparkles size={13} /> AI analyst for your actual data <ChevronRight size={12} /></div><h1>The data platform that <em>understands</em> your business.</h1><p>Upload a structured file and get a versioned workspace for profiling, quality, analysis, reports, and evidence-backed AI.</p><div className="hero-ctas"><Button onClick={start}>Get started free <ChevronRight size={16} /></Button><Button variant="ghost-light" onClick={() => document.getElementById('product')?.scrollIntoView({ behavior: 'smooth' })}><Play size={11} fill="currentColor" /> See how it works</Button></div><div className="trusted"><span>Built around the data you actually have.</span><div className="trust-logos"><b>CSV</b><b>Excel</b><b>JSON</b><b>Parquet</b></div></div></div><div className="product-preview landing-signal-shell"><div className="landing-signal"><div className="signal-top"><span><i className="signal-live" /> PIVOT WORKSPACE</span><Badge tone="green">SOURCE SAFE</Badge></div><div className="signal-title"><small>FROM RAW DATA TO SIGNAL</small><h2>Understand first.<br /><em>Decide with evidence.</em></h2></div><div className="signal-flow"><div><span className="signal-node"><Database size={16} /></span><b>Upload</b><small>Original preserved</small></div><i /><div><span className="signal-node mint"><Table2 size={16} /></span><b>Profile</b><small>Schema detected</small></div><i /><div><span className="signal-node violet"><Bot size={16} /></span><b>Investigate</b><small>AI grounded</small></div></div><div className="signal-chart"><div className="signal-chart-head"><span>Evidence pipeline</span><span>READY WHEN YOU ARE</span></div><div className="signal-bars"><i /><i /><i /><i /><i /><i /><i /><i /></div><div className="signal-foot"><span><CheckCircle2 size={13} /> No invented numbers</span><span><GitBranch size={13} /> Every change traceable</span></div></div></div></div></section></div><section className="landing-section content-width" id="product"><div className="section-intro"><p className="eyebrow">FROM RAW DATA TO REAL DECISIONS</p><h2>Everything your data has been missing.</h2><p>Pivot adapts its workspace to whatever your file contains.</p></div><div className="feature-grid">{[[Table2, 'Smart profiling', 'Schema, statistics, quality, and semantic hints from your file.'], [WandSparkles, 'Safe cleaning', 'Preview every transformation before approving a new version.'], [Bot, 'AI analyst', 'Questions become investigations backed by executed evidence.'], [FileBarChart2, 'Traceable reports', 'Export live summaries from the current dataset.'], [GitBranch, 'Lineage', 'Follow the source, transformations, exports, and versions.']].map(([Icon, title, copy]) => <article className="feature-card" key={title}><span className="feature-icon"><Icon size={17} /></span><h3>{title}</h3><p>{copy}</p></article>)}</div></section><section className="builder-section content-width" id="solutions"><div className="builder-copy"><p className="eyebrow">BUILT FOR DATA TEAMS</p><h2>Make your data work <em>harder.</em></h2><p>Bring a raw structured file and get a clear, versioned starting point for analysis.</p><div className="check-list"><span><Check size={14} /> Original source preserved</span><span><Check size={14} /> Read-only SQL</span><span><Check size={14} /> Evidence-backed AI</span></div><Button onClick={start}>Upload a dataset <ChevronRight size={15} /></Button></div></section><footer className="landing-footer content-width"><Logo /><span>© 2025 Pivot Analytics</span><span>Built for better decisions.</span></footer></div> }

function Auth({ back }) { function signIn() { window.location.assign(`${API}/api/auth/google/login`) }
  return <div className="auth-shell"><header className="auth-header"><button className="auth-brand" onClick={back}><Logo light /></button></header><main className="auth-card"><section className="auth-story"><div className="auth-story-mark"><Sparkles size={18} /></div><p className="eyebrow">PIVOT DATA INTELLIGENCE</p><h1>Welcome to your <em>data.</em></h1><p>Sign in with Google to access your private Pivot workspace.</p></section><section className="auth-form-panel"><button className="auth-back" onClick={back}>Back to home</button><div className="auth-heading"><span className="eyebrow">SECURE SIGN IN</span><h2>Continue to Pivot.</h2><p>Google is the only sign-in method for this workspace.</p></div><button className="social-button" onClick={signIn}><GoogleMark /> Continue with Google <ChevronRight size={14} /></button><small className="auth-terms">Your account and data remain private to your verified Google identity.</small></section></main></div>
  return <div className="auth-shell"><div className="auth-orbit auth-orbit-one" /><div className="auth-orbit auth-orbit-two" /><header className="auth-header"><button className="auth-brand" onClick={back}><Logo light /></button><span className="auth-header-switch">{signup ? 'Already have an account?' : 'New to Pivot?'} <button className="auth-switch" onClick={() => { setError(''); changeMode(signup ? 'login' : 'signup') }}>{signup ? 'Sign in' : 'Create an account'}</button></span></header><main className="auth-card"><section className="auth-story"><div className="auth-story-mark"><Sparkles size={18} /></div><p className="eyebrow">PIVOT DATA INTELLIGENCE</p><h1>{signup ? <>A clearer view of <em>what’s next.</em></> : <>Welcome back to your <em>data.</em></>}</h1><p>{signup ? 'Create your account, then upload the source file you want Pivot to understand.' : 'Sign in to continue to your private dataset upload workspace.'}</p><div className="auth-metric"><span><b>01</b><small>source first</small></span><i /><span><b>100%</b><small>traceable</small></span></div></section><section className="auth-form-panel"><button className="auth-back" onClick={back}><span className="back-chevron"><ChevronRight size={14} /></span> Back to home</button><div className="auth-heading"><span className="eyebrow">{signup ? 'CREATE YOUR ACCOUNT' : 'WELCOME BACK'}</span><h2>{signup ? 'Start with Pivot.' : 'Sign in to Pivot.'}</h2><p>{signup ? 'Your upload workspace is one step away.' : 'Your source stays protected from the first upload.'}</p></div><button className="social-button" onClick={() => setError('Google sign-in will be connected with the account service.')}><GoogleMark /> Continue with Google <ChevronRight size={14} /></button><div className="auth-divider"><span>or continue with email</span></div><form onSubmit={submit}>{signup && <label>Full name<input value={name} onChange={event => setName(event.target.value)} placeholder="Amelia King" required /></label>}<label>Email address<input type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="you@company.com" required /></label><label>Password<div className="password-field"><input type={show ? 'text' : 'password'} value={password} onChange={event => setPassword(event.target.value)} placeholder="At least 8 characters" minLength="8" required /><button type="button" onClick={() => setShow(value => !value)}>{show ? 'Hide' : 'Show'}</button></div></label>{error && <p className="auth-error">{error}</p>}<button className="auth-submit" type="submit">{signup ? 'Create account' : 'Sign in'} <ChevronRight size={15} /></button></form><div className="auth-inline-switch">{signup ? 'Already have an account?' : 'New to Pivot?'} <button onClick={() => { setError(''); changeMode(signup ? 'login' : 'signup') }}>{signup ? 'Sign in' : 'Create an account'}</button></div><small className="auth-terms">This local account gate will connect to the secure auth service before production.</small></section></main></div> }

function Upload({ input, busy, message, upload, logout, user }) { const firstName = user?.full_name?.trim().split(/\s+/)[0]; return <div className="upload-shell"><header className="upload-header"><Logo /><button className="upload-logout" onClick={logout}>Sign out</button></header><main className="upload-main"><div className="upload-intro"><span className="upload-kicker"><Database size={14} /> PRIVATE DATA WORKSPACE</span><h1>Bring your data.<br /><em>We’ll find the signal.</em></h1><p>Welcome{firstName ? `, ${firstName}` : ''}. Pivot will preserve the original, profile every field, and prepare your workspace.</p></div><button className="upload-dropzone" onClick={() => input.current?.click()} disabled={busy}><span className="upload-orb"><Database size={28} /></span><strong>{busy ? 'Building your workspace…' : 'Choose a dataset to upload'}</strong><small>CSV, Excel, JSON, or Parquet · up to 50MB</small><span className="upload-button">{busy ? <RefreshCw size={15} className="spin" /> : <Download size={15} />} {busy ? 'Processing file' : 'Select file'}</span></button>{message && <div className="upload-message"><AlertCircle size={16} />{message}</div>}<div className="upload-promises"><span><LockKeyhole size={15} /><b>Original preserved</b><small>Nothing overwrites your source.</small></span><span><Sparkles size={15} /><b>Profile generated</b><small>Schema and quality come from your file.</small></span><span><Bot size={15} /><b>AI-ready context</b><small>Answers use your actual evidence.</small></span></div></main><input ref={input} hidden type="file" accept=".csv,.xlsx,.xls,.json,.parquet" onChange={event => upload(event.target.files?.[0])} /></div> }

function CommandPalette({ open, close, setPage, reset }) { const commands = [['Switch dataset', reset, Database], ['Ask Pivot', () => setPage('Ask Pivot'), Bot], ['Run analysis', () => setPage('Analyze'), BarChart3], ['Generate report', () => setPage('Reports'), FileBarChart2], ['Open SQL', () => setPage('SQL'), Code2], ['Review quality', () => setPage('Data'), ShieldCheck], ['View history', () => setPage('History'), GitBranch]]; const [query, setQuery] = useState(''); useEffect(() => { if (open) setQuery('') }, [open]); if (!open) return null; const matches = commands.filter(([label]) => label.toLowerCase().includes(query.toLowerCase())); return <div className="command-backdrop" onMouseDown={close}><section className="command-palette" onMouseDown={event => event.stopPropagation()} role="dialog" aria-label="Pivot command palette"><div><Search size={17} /><input autoFocus value={query} onChange={event => setQuery(event.target.value)} placeholder="Search Pivot…" /><kbd>ESC</kbd></div><small>WORKSPACE COMMANDS</small>{matches.map(([label, action, Icon]) => <button key={label} onClick={() => { action(); close() }}><Icon size={16} /><span>{label}</span><ChevronRight size={14} /></button>)}</section></div> }
function Header({ data, profile, setPage, openCommands }) { const [open, setOpen] = useState(null); const initialsText = initials(profile); return <header className="workspace-header"><button className="command-trigger" onClick={openCommands}><Search size={15} /><span>Search Pivot…</span><kbd>Ctrl K</kbd></button><div className="header-actions"><button className="header-icon-button" aria-label="Help" onClick={() => setOpen(open === 'help' ? null : 'help')}>?</button><button className="header-icon-button notification" aria-label="Notifications" onClick={() => setOpen(open === 'notifications' ? null : 'notifications')}><Bell size={17} /><i /></button><button className="header-avatar" aria-label="Open profile" onClick={() => setPage('My Profile')}>{profile.avatar ? <img src={profile.avatar} alt="Profile" /> : initialsText}</button>{open === 'help' && <div className="header-popover"><b>Need a hand?</b><span>Use Search Pivot to move through the workspace or ask a question with evidence.</span><button onClick={() => { setPage('Ask Pivot'); setOpen(null) }}>Ask Pivot <ChevronRight size={13} /></button></div>}{open === 'notifications' && <div className="header-popover notification-popover"><b>Workspace health</b><span><i className="green-dot" /> {data.profile?.issues?.length || 0} quality items detected.</span><button onClick={() => { setPage('Data'); setOpen(null) }}>Review quality <ChevronRight size={13} /></button></div>}</div></header> }
function Shell({ data, profile, page, setPage, reset, children }) { const [mobileOpen, setMobileOpen] = useState(false); const [commandsOpen, setCommandsOpen] = useState(false); useEffect(() => { const handler = event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setCommandsOpen(true) } if (event.key === 'Escape') setCommandsOpen(false) }; window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler) }, []); return <div className="app-shell"><aside className={`workspace-sidebar ${mobileOpen ? 'open' : ''}`}><div className="sidebar-top"><Logo light /><button className="sidebar-close" onClick={() => setMobileOpen(false)}><X size={18} /></button></div><button className="workspace-picker" onClick={reset}><span className="workspace-badge"><Database size={14} /></span><span><b>{data.file_name}</b><small>v{data.active_version || 0} · {number(data.rows)} rows</small></span><ChevronDown size={14} /></button><p className="sidebar-label">WORKSPACE</p><nav className="workspace-nav">{NAV.map(([label, Icon]) => <button key={label} className={page === label ? 'active' : ''} onClick={() => { setPage(label); setMobileOpen(false) }}><Icon size={16} /><span>{label}</span>{label === 'Ask Pivot' && <i className="new-dot" />}</button>)}</nav><button className="brief-action" onClick={() => setPage('Generate Brief')}><Sparkles size={15} /> Generate brief</button><div className="sidebar-bottom"><button onClick={() => setPage('History')}><Activity size={16} /> History</button><button onClick={() => setPage('Settings')}><Settings2 size={16} /> Settings</button><button className="profile-mini" onClick={() => setPage('My Profile')}><span>{profile.avatar ? <img src={profile.avatar} alt="" /> : initials(profile)}</span><div><b>{profile.fullName || 'Workspace user'}</b><small>{profile.role || 'Owner'}</small></div><ChevronRight size={14} /></button></div></aside><main className="workspace-main"><button className="mobile-sidebar" onClick={() => setMobileOpen(true)}><Menu size={20} /></button><Header data={data} profile={profile} setPage={setPage} openCommands={() => setCommandsOpen(true)} />{children}</main><CommandPalette open={commandsOpen} close={() => setCommandsOpen(false)} setPage={setPage} reset={reset} /></div> }

function Overview({ data, overview, go }) { const trend = overview?.trend || []; return <div className="workspace-page"><Head eyebrow="CURRENT DATASET" title="A clear view of what matters." copy={`${data.file_name} is profiled from the preserved source file.`} action={<Button variant="outline" onClick={() => go('Reports')}><Download size={15} /> Export report</Button>} /><div className="dashboard-banner"><div><span className="live-pill"><i /> ACTIVE VERSION</span><h2>{data.file_name} <small>{number(data.rows)} rows · {number(data.columns)} columns</small></h2></div><Button variant="dark-outline" onClick={() => go('Data')}>Open data workspace <ChevronRight size={15} /></Button></div><div className="stats-grid">{(overview?.cards || []).map(card => <article className="stat-card" key={`${card.label}-${card.column || ''}`}><div className="stat-icon green"><LineChart size={17} /></div><div className="stat-info"><span>{card.label}</span><b>{number(card.value)}{card.suffix || ''}</b><small>Detected from this dataset</small></div></article>)}</div><div className="dashboard-grid"><article className="panel chart-panel"><div className="panel-heading"><div><span className="panel-kicker">DETECTED TIME SERIES</span><h3>{overview?.trend_columns?.value || 'No time series detected'}</h3></div><Badge tone={trend.length ? 'green' : 'gray'}>{trend.length ? `${trend.length} periods` : 'Unavailable'}</Badge></div>{trend.length ? <ResponsiveContainer width="100%" height={240}><AreaChart data={trend}><CartesianGrid vertical={false} stroke="#edf0eb" /><XAxis dataKey="period" /><YAxis /><Tooltip /><Area type="monotone" dataKey="value" stroke="#0b6958" fill="#dbeee7" /></AreaChart></ResponsiveContainer> : <div className="lineage-empty"><LineChart size={20} /><b>No compatible date and numeric fields were detected.</b><span>Pivot will generate this view when the source contains both.</span></div>}</article><article className="panel quality-card"><span className="panel-kicker">NEEDS ATTENTION</span><h3>{number(data.quality_score)}/100</h3><p>{data.profile?.issues?.length || 0} quality findings need review.</p><Button variant="outline" onClick={() => go('Data')}>Review quality <ChevronRight size={14} /></Button></article><article className="panel quick-panel"><span className="panel-kicker">SUGGESTED NEXT MOVE</span><h3>Ask Pivot</h3><p>Investigate trends, values, and quality findings with evidence from this dataset.</p><button className="text-button" onClick={() => go('Ask Pivot')}>Ask a question <ChevronRight size={13} /></button></article></div></div> }
function Profile({ data }) { const stats = data.profile?.schema?.column_stats || []; return <div className="workspace-page"><Head eyebrow="DATASET / SCHEMA" title="What each field means." copy="This is the dataset profile. Your personal profile lives under My Profile." /><section className="schema-cards">{stats.map(item => <article className="schema-card" key={item.column}><Badge tone="purple">{item.role.replaceAll('_', ' ')}</Badge><b>{item.column}</b><p>{item.dtype} · {item.unique_count} unique · {item.null_pct}% null</p><small>Examples: {(item.examples || []).join(', ') || 'No non-null examples'}</small></article>)}</section></div> }
function Quality({ data, go }) { const issues = data.profile?.issues || []; const metrics = data.profile?.metrics || {}; return <div className="workspace-page"><Head eyebrow="DATASET / QUALITY" title={`Quality score: ${number(data.quality_score)}/100`} copy="These are findings, not automatic changes." action={<Button variant="outline" onClick={() => go('Cleaning')}><WandSparkles size={15} /> Review cleaning</Button>} /><section className="quality-hero"><div><Badge tone="green">PROFILE COMPLETE</Badge><h2>{issues.length ? 'A few things deserve attention.' : 'Your source looks healthy.'}</h2><p>Pivot found {issues.length} issue categories across {number(data.rows)} rows.</p></div><div className="quality-metrics"><span><b>{metrics.completeness ?? 0}%</b>completeness</span><span><b>{metrics.consistency ?? 0}%</b>consistency</span><span><b>{metrics.uniqueness ?? 0}%</b>uniqueness</span></div></section><div className="issue-grid">{issues.length ? issues.map(issue => <article className="issue-card" key={issue.type}><Badge tone="orange">{issue.type.replaceAll('_', ' ')}</Badge><h3>{number(issue.count)} affected</h3><p>{issue.impact}</p><small>Suggested: {issue.fix}</small></article>) : <div className="lineage-empty"><CheckCircle2 size={20} /><b>No obvious quality issues detected.</b><span>Pivot checked missing values, duplicates, dates, negatives, and outliers.</span></div>}</div></div> }
function Cleaning({ data, busy, preview, previewOp, approve, reject }) { const ops = [['standardize_format', 'Standardize messy formats'], ['trim_text', 'Trim text fields'], ['remove_duplicates', 'Remove exact duplicates'], ['normalize_columns', 'Normalize column names'], ['parse_dates', 'Parse date fields'], ['fill_missing', 'Fill missing values'], ['remove_outliers', 'Review numeric outliers']]; const afterColumns = preview?.after?.columns || (preview?.after_preview?.[0] ? Object.keys(preview.after_preview[0]) : []); return <div className="workspace-page"><Head eyebrow="CLEANING / VERSIONED" title="Review before changing." copy="Every action creates a temporary preview. The source is untouched until approval. You can also ask the AI Analyst to prepare an updated CSV." /><div className="cleaning-grid">{ops.map(([op, title]) => <article className="clean-action" key={op}><span className="clean-icon"><WandSparkles size={17} /></span><div><h3>{title}</h3><p>{op === 'standardize_format' ? 'Normalize text, dates, and numeric formats in one safe pass.' : 'Create a safe, reversible candidate version.'}</p></div><Button variant="outline" disabled={busy} onClick={() => previewOp(op)}>Preview change <ChevronRight size={14} /></Button></article>)}</div>{preview && <section className="panel preview-review"><div className="panel-heading"><div><span className="panel-kicker">TEMPORARY PREVIEW</span><h3>{preview.operation.replaceAll('_', ' ')}</h3></div><Badge tone="orange">Awaiting approval</Badge></div><div className="analysis-detail-grid"><div className="mini-metric"><span>Rows before</span><b>{number(preview.rows_before ?? preview.before?.rows)}</b></div><div className="mini-metric"><span>Rows after</span><b>{number(preview.rows_after ?? preview.after?.rows)}</b></div><div className="mini-metric"><span>Rows affected</span><b>{number(preview.metrics?.affected_rows)}</b></div></div><Grid columns={afterColumns} rows={preview.after?.preview || preview.after_preview || []} /><div className="preview-actions"><Button onClick={approve}><Check size={15} /> Accept and create version</Button><Button variant="outline" onClick={reject}>Reject preview</Button></div></section>}</div> }
function SchemaExplorer({ data }) { const fields = data.profile?.schema?.column_stats || []; const [selected, setSelected] = useState(fields[0]?.column || ''); const [query, setQuery] = useState(''); const selectedField = fields.find(field => field.column === selected) || fields[0]; const visible = fields.filter(field => field.column.toLowerCase().includes(query.toLowerCase())); return <div className="workspace-page schema-explorer"><Head eyebrow="DATA / SCHEMA" title="Know every field." copy="Search, inspect, and understand the structure Pivot detected from the active dataset." /><div className="schema-toolbar"><Search size={15}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search fields"/><span>{fields.length} fields</span></div><div className="schema-layout"><section className="schema-table"><div className="schema-row schema-labels"><span>Field</span><span>Type</span><span>Role</span><span>Unique</span><span>Missing</span><span>Example</span></div>{visible.map(field => <button className={`schema-row ${selectedField?.column === field.column ? 'selected' : ''}`} onClick={() => setSelected(field.column)} key={field.column}><b>{field.column}</b><span>{field.dtype}</span><span><Badge tone="purple">{field.role?.replaceAll('_', ' ') || 'field'}</Badge></span><span>{number(field.unique_count)}</span><span>{field.null_pct || 0}%</span><span>{field.examples?.[0] ?? '—'}</span></button>)}</section><aside className="field-inspector">{selectedField ? <><span className="panel-kicker">FIELD INSPECTOR</span><h2>{selectedField.column}</h2><Badge tone="purple">{selectedField.role?.replaceAll('_', ' ') || 'field'}</Badge><div className="field-facts"><span><small>Data type</small><b>{selectedField.dtype}</b></span><span><small>Unique values</small><b>{number(selectedField.unique_count)}</b></span><span><small>Missing</small><b>{selectedField.null_pct || 0}%</b></span></div><div className="mini-distribution"><span>Distribution preview</span><i/><i/><i/><i/><i/><i/><i/></div><div className="field-examples"><small>EXAMPLES</small>{(selectedField.examples || []).slice(0, 4).map(example => <code key={String(example)}>{String(example)}</code>)}</div></> : <div className="lineage-empty"><Table2 size={20}/><b>No fields were profiled.</b></div>}</aside></div></div> }
function DataWorkspace({ data, busy, preview, previewOp, approve, reject }) { const [tab, setTab] = useState('Schema'); return <><div className="data-tabs"><span>DATA</span>{['Schema', 'Quality', 'Clean'].map(item => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item}</button>)}</div>{tab === 'Schema' ? <SchemaExplorer data={data} /> : tab === 'Quality' ? <Quality data={data} go={() => setTab('Clean')} /> : <Cleaning data={data} busy={busy} preview={preview} previewOp={previewOp} approve={approve} reject={reject} />}</> }
function Analysis({ analyses, busy, selected, run }) { const result = selected?.result; const points = result?.chart || []; const rows = points.map(point => result.kind === 'trend' ? { period: point.label, [result.field || 'value']: point.value } : result.kind === 'breakdown' ? { [result.field || 'group']: point.label, count: point.value } : { range: point.label, count: point.value }); const columns = result?.kind === 'trend' ? ['period', result.field || 'value'] : result?.kind === 'breakdown' ? [result.field || 'group', 'count'] : ['range', 'count']; return <div className="workspace-page"><Head eyebrow="ANALYSIS / GENERATED" title="Analyses your data supports." copy="These options come from detected fields, so Pivot does not assume a business domain." /><div className="analysis-grid">{analyses.map(item => <article className={`analysis-card ${item.enabled ? '' : 'disabled'}`} key={item.id}><span className="analysis-icon"><BarChart3 size={17} /></span><h3>{item.title}</h3><p>{item.description}</p><Button variant="outline" disabled={!item.enabled || busy} onClick={() => run(item)}>{busy && selected?.id === item.id ? <RefreshCw size={14} className="spin" /> : 'Run analysis'} <ChevronRight size={14} /></Button></article>)}</div>{result && <section className="panel analysis-detail"><div className="panel-heading"><div><span className="panel-kicker">ANALYSIS RESULT</span><h3>{result.title}</h3><p className="result-context">Field: <b>{result.field || 'dataset'}</b> · Calculation: <b>{result.aggregation || 'profile review'}</b></p></div></div>{result.metrics && <div className="result-metrics">{Object.entries(result.metrics).filter(([, value]) => value !== null && typeof value !== 'object').map(([key, value]) => <div key={key}><span>{key.replaceAll('_', ' ')}</span><b>{typeof value === 'number' ? number(value) : text(value)}</b></div>)}</div>}{points.length > 1 && <MiniChart points={points} />}<Grid columns={columns} rows={rows} /></section>}</div> }
function Analyst({ data, question, setQuestion, messages, ask, busy }) { return <div className="workspace-page"><Head eyebrow="AI ANALYST / GROUNDED" title="Ask better questions." copy="Pivot investigates the data, executes read-only evidence queries, and explains only what the evidence supports." action={<span className="ai-status"><i /> Evidence mode</span>} /><div className="analyst-layout"><div className="analyst-main"><div className="analyst-intro"><span className="analyst-orb"><Bot size={27} /></span><h2>What would you like to know?</h2><p>Ask about trends, quality, categories, or values in your file.</p></div><div className="suggested-prompts"><button onClick={() => setQuestion('Which values are highest?')}>Which values are highest? <ChevronRight size={14} /></button><button onClick={() => setQuestion('What quality issues should I review?')}>What quality issues should I review? <ChevronRight size={14} /></button><button onClick={() => setQuestion('Show me the trend by month')}>Show me the trend by month <ChevronRight size={14} /></button></div><div className="chat-thread">{messages.length === 0 && <div className="chat-empty"><Bot size={18} /><span>Start a conversation. I’ll keep every question and evidence-backed answer here.</span></div>}{messages.map((message, index) => <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}><div className="chat-bubble"><div className="answer-head"><span className="analyst-avatar">{message.role === 'user' ? initials(readJson('pivot-personal-profile')) : <Bot size={15} />}</span><b>{message.role === 'user' ? 'You' : 'Pivot Analyst'}</b>{message.source && <Badge tone="green">{message.source}</Badge>}</div>{message.pending ? <p className="chat-pending"><RefreshCw size={14} className="spin" /> Investigating the source…</p> : <><p>{message.text}</p>{message.sql && <><small className="answer-label">EVIDENCE SQL</small><pre>{message.sql}</pre></>}{message.query_result && <div className="answer-result"><CheckCircle2 size={14} /> {number(message.query_result.count)} rows returned · fields: {(message.query_result.columns || []).join(', ')}</div>} {message.role === 'assistant' && <small>Sources: {(message.citations || []).map(source => source.source).join(', ') || data.file_name}</small>}</>}</div></div>)}</div><div className="ask-composer"><textarea value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); ask() } }} placeholder="Ask anything about your data..." rows="2" /><div><span><Sparkles size={14} /> Grounded in {data.file_name}</span><button onClick={ask} disabled={busy || !question.trim()}>{busy ? <RefreshCw size={14} className="spin" /> : <Send size={16} />}</button></div></div></div><aside className="analyst-aside"><div className="aside-card"><span className="panel-kicker">HOW IT WORKS</span><div className="how-step"><span>1</span><div><b>Understand the schema</b><small>Relevant fields and profile facts are loaded.</small></div></div><div className="how-step"><span>2</span><div><b>Execute evidence</b><small>Queries are validated as read-only.</small></div></div><div className="how-step"><span>3</span><div><b>Explain with evidence</b><small>Answers show the query and returned fields.</small></div></div></div></aside></div></div> }
function AnalystVisualization({ visualization }) {
  if (!visualization || visualization.type === 'table') return null;
  
  if (visualization.type === 'line') {
    return (
      <div className="analyst-visual" style={{ margin: '15px 0' }}>
        <div className="visual-title" style={{ fontWeight: '600', fontSize: '13px', color: '#153f36', marginBottom: '10px' }}>
          {visualization.title}
        </div>
        <MiniChart points={(visualization.data || []).map(point => ({ label: point.label, value: point.value }))} />
      </div>
    );
  }

  // Bar Chart using Recharts
  const data = (visualization.data || []).slice(0, 10).map(p => ({
    name: p.label,
    value: Number(p.value) || 0
  }));

  if (!data.length) return null;

  return (
    <div className="analyst-visual" style={{ margin: '15px 0' }}>
      <div className="visual-title" style={{ fontWeight: '600', fontSize: '13px', color: '#153f36', marginBottom: '10px' }}>
        {visualization.title}
      </div>
      <div style={{ height: '220px', width: '100%' }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2ee" />
            <XAxis 
              dataKey="name" 
              tick={{ fill: '#7f958b', fontSize: 10 }} 
              axisLine={{ stroke: '#cbd9cf' }} 
              tickLine={{ stroke: '#cbd9cf' }}
              interval={0}
              tickFormatter={(text) => text.length > 12 ? `${text.substring(0, 10)}...` : text}
            />
            <YAxis 
              tickFormatter={(val) => {
                if (val >= 1e6) return `${(val / 1e6).toFixed(1)}M`
                if (val >= 1e3) return `${(val / 1e3).toFixed(1)}K`
                return val
              }}
              tick={{ fill: '#7f958b', fontSize: 10 }}
              axisLine={{ stroke: '#cbd9cf' }} 
              tickLine={{ stroke: '#cbd9cf' }}
            />
            <Tooltip 
              contentStyle={{ 
                background: '#073a31', 
                border: 'none', 
                borderRadius: '6px', 
                color: 'white',
                fontSize: '11px',
                fontFamily: 'inherit'
              }}
              formatter={(value) => [`${value.toLocaleString()}`, 'Value']}
            />
            <Bar dataKey="value" fill="#138463" radius={[4, 4, 0, 0]} barSize={32}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={index === 0 ? '#10634c' : '#138463'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}


function AnalystV2({ data, question, setQuestion, messages, ask, busy }) {
  const userInitials = initials(readJson('pivot-personal-profile'))
  return <div className="workspace-page"><Head eyebrow="AI ANALYST / GROUNDED" title="Ask anything about your data." copy="Pivot calculates answers from the active dataset, then shows the evidence, visualization, and reasoning behind each response." action={<span className="ai-status"><i /> Evidence mode</span>} /><div className="analyst-layout"><div className="analyst-main"><div className="analyst-intro"><span className="analyst-orb"><Bot size={27} /></span><h2>What would you like to investigate?</h2><p>Ask naturally: “Which product sales are highest?” or “When did sales drop most, and what changed?”</p></div><div className="suggested-prompts"><button onClick={() => setQuestion('Which product sales are highest?')}>Which product sales are highest? <ChevronRight size={14} /></button><button onClick={() => setQuestion('When did sales drop the most, and what changed?')}>When did sales drop the most? <ChevronRight size={14} /></button><button onClick={() => setQuestion('What quality issues should I review?')}>What quality issues should I review? <ChevronRight size={14} /></button></div><div className="chat-thread">{messages.length === 0 && <div className="chat-empty"><Bot size={18} /><span>Start a conversation. I’ll calculate answers from {data.file_name} and keep the supporting evidence in this thread.</span></div>}{messages.map((message, index) => <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}><div className="chat-bubble"><div className="answer-head"><span className="analyst-avatar">{message.role === 'user' ? userInitials : <Bot size={15} />}</span><b>{message.role === 'user' ? 'You' : 'Pivot Analyst'}</b>{message.source && <Badge tone="green">{message.source}</Badge>}</div>{message.pending ? <p className="chat-pending"><RefreshCw size={14} className="spin" /> Investigating the source…</p> : <>{<p>{message.text}</p>}{message.insights?.length > 0 && <div className="analyst-insights"><b>What stands out</b>{message.insights.map((insight, insightIndex) => <span key={insightIndex}><CheckCircle2 size={13} />{insight}</span>)}</div>}<AnalystVisualization visualization={message.visualization} />{message.driver_rows?.length > 0 && <><div className="answer-label">ASSOCIATED CHANGE BY GROUP</div><Grid columns={Object.keys(message.driver_rows[0])} rows={message.driver_rows} /></>}{message.query_result?.rows?.length > 0 && <><div className="answer-label">SUPPORTING DATA</div><Grid columns={message.query_result.columns || Object.keys(message.query_result.rows[0])} rows={message.query_result.rows} /></>}{message.sql && <details className="evidence-details"><summary>Show calculation query</summary><pre>{message.sql}</pre></details>}{message.role === 'assistant' && <small>Based on: {(message.citations || []).map(source => source.source).join(', ') || data.file_name}</small>}</>}</div></div>)}</div><div className="ask-composer"><textarea value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); ask() } }} placeholder="Ask anything about your data..." rows="2" /><div><span><Sparkles size={14} /> Calculated from {data.file_name}</span><button onClick={ask} disabled={busy || !question.trim()}>{busy ? <RefreshCw size={14} className="spin" /> : <Send size={16} />}</button></div></div></div><aside className="analyst-aside"><div className="aside-card"><span className="panel-kicker">HOW IT WORKS</span><div className="how-step"><span>1</span><div><b>Understand the schema</b><small>Relevant dates, metrics, and grouping fields are detected.</small></div></div><div className="how-step"><span>2</span><div><b>Calculate from the source</b><small>Answers use the active dataframe, not invented sample numbers.</small></div></div><div className="how-step"><span>3</span><div><b>Explain the evidence</b><small>Charts, rows, and the safe calculation trace stay attached to the answer.</small></div></div></div></aside></div></div>
}

function SQL({ data, sql, setSql, result, run, busy }) { const [filter, setFilter] = useState(''); const visibleRows = result?.rows?.filter(row => !filter.trim() || Object.values(row).some(value => text(value).toLowerCase().includes(filter.toLowerCase()))) || []; return <div className="workspace-page"><Head eyebrow="SQL / SAFE WORKSPACE" title="Query your data." copy="Use read-only SQL against the normalized dataset table." action={<Badge tone="green"><LockKeyhole size={12} /> Read-only mode</Badge>} /><div className="sql-layout"><div className="sql-editor panel"><div className="editor-bar"><span><Code2 size={15} /> query-01.sql</span><span>SQLite · dataset</span></div><div className="editor-body"><textarea value={sql} onChange={event => setSql(event.target.value)} spellCheck="false" /></div><div className="editor-footer"><span><ShieldCheck size={13} /> Query guard active</span><Button variant="small" onClick={run} disabled={busy}>{busy ? <RefreshCw size={13} className="spin" /> : <Play size={13} fill="currentColor" />} Run query</Button></div></div><div className="sql-help panel"><span className="panel-kicker">DETECTED COLUMNS</span><h3>Use the profile</h3><p>{(data.profile?.columns_list || []).join(', ') || 'No columns detected'}</p><div className="sql-tip"><LockKeyhole size={14} /><span>Only SELECT and WITH statements can run.</span></div></div></div>{result && <div className="panel sql-result"><div className="panel-heading"><div><h3>{number(result.count)} rows returned</h3><small className="result-context">Showing {number(visibleRows.length)} returned rows · search exact results below</small></div><Button variant="outline" onClick={() => downloadText('pivot-query-result.csv', `${result.columns.join(',')}\n${result.rows.map(row => result.columns.map(column => JSON.stringify(row[column] ?? '')).join(',')).join('\n')}`, 'text/csv')}><Download size={14} /> Export CSV</Button></div><label className="result-search"><Search size={14} /><input value={filter} onChange={event => setFilter(event.target.value)} placeholder="Search returned rows..." /></label><Grid columns={result.columns} rows={visibleRows} /></div>}</div> }
function AutoPilot({ data, busy, report, run }) {
  const charts = report?.charts || []
  return <div className="workspace-page">
    <Head eyebrow="AUTO PILOT / LOCAL-FIRST" title="One click. A complete first briefing." copy="Pivot uses one small AI planning call when configured, then validates and calculates every result locally. The preserved source never changes." action={<Button onClick={run} disabled={busy}>{busy ? <RefreshCw size={15} className="spin" /> : <Rocket size={15} />}{busy ? 'Running Auto Pilot…' : report ? 'Run again' : 'Run Auto Pilot'}</Button>} />
    {!report?.domain ? <section className="autopilot-hero panel"><div className="autopilot-orb"><Rocket size={28} /></div><div><span className="panel-kicker">READY FOR {data.file_name}</span><h2>Turn the first analyst pass into a single action.</h2><p>Auto Pilot standardizes safe formats, removes exact duplicates, creates a traceable dataset version, lets AI choose the analysis plan from the schema, calculates the results, and writes a briefing.</p><div className="autopilot-checks"><span><CheckCircle2 size={14} /> One lightweight AI plan</span><span><CheckCircle2 size={14} /> Original source protected</span><span><CheckCircle2 size={14} /> Version and report included</span></div></div></section> : <>
      <section className="autopilot-hero panel complete"><div className="autopilot-orb"><CheckCircle2 size={28} /></div><div><span className="panel-kicker">AUTO PILOT COMPLETE</span><h2>{report.domain.name}</h2><p>{report.domain.evidence} The cleaned result is saved as version {report.version}; your original file remains unchanged.</p>{report.headline && <p className="autopilot-headline">{report.headline}</p>}<div className="autopilot-actions"><Button variant="outline" onClick={() => download(report.download_url)}><Download size={14} /> Download cleaned version</Button>{report.briefing_url && <Button variant="outline" onClick={() => download(report.briefing_url)}><FileBarChart2 size={14} /> Download briefing</Button>}</div></div></section>
      <div className="autopilot-coverage"><span><b>{number(report.coverage?.numeric_fields)}</b> measures scanned</span><span><b>{number(report.coverage?.group_fields)}</b> dimensions scanned</span><span><b>{number(report.coverage?.time_series)}</b> trends checked</span><span><b>{number(report.coverage?.relationships)}</b> relationships ranked</span></div>
      <section className="autopilot-kpis">{(report.kpis || []).map(card => <article className="autopilot-kpi" key={card.label}><span>{card.label}</span><b>{number(card.value)}{card.suffix || ''}</b><small>Calculated from the active version</small></article>)}</section>
      <section className="autopilot-grid"><article className="panel autopilot-insights"><div className="panel-heading"><div><span className="panel-kicker">WHAT STOOD OUT</span><h3>Executive takeaways</h3></div><Badge tone="green">Data-backed</Badge></div>{report.insights.map(item => <div className="autopilot-insight" key={item.text}><Sparkles size={14} /><span>{item.text}</span></div>)}</article><article className="panel autopilot-cleaning"><span className="panel-kicker">SAFE CLEANUP APPLIED</span><h3>What changed</h3>{report.cleaning.map(step => <div className="autopilot-step" key={step.operation}><Check size={13} /><span>{step.label}</span><b>{number(step.rows_before)} → {number(step.rows_after)}</b></div>)}</article></section>
      <section className="autopilot-charts">{charts.map(chart => <article className="panel autopilot-chart" key={chart.title}><span className="panel-kicker">AUTOMATIC ANALYSIS</span><h3>{chart.title}</h3>{chart.type === 'line' ? <MiniChart points={chart.data} /> : <AutoPilotBars points={chart.data} />}</article>)}</section>
      <section className="panel autopilot-next"><span className="panel-kicker">NEXT BEST CHECKS</span><h3>Continue with confidence</h3><ol>{report.recommendations.map(item => <li key={item}>{item}</li>)}</ol></section>
    </>}
  </div>
}

function AutoPilotBars({ points = [] }) {
  const max = Math.max(...points.map(point => Number(point.value) || 0), 1)
  return <div className="autopilot-bars">{points.map(point => <div className="autopilot-bar" key={point.label}><span title={point.label}>{point.label}</span><i><b style={{ width: `${(Number(point.value) / max) * 100}%` }} /></i><strong>{number(point.value)}</strong></div>)}</div>
}

function Reports({ data, refresh }) { const [title, setTitle] = useState('Dataset report'); const [format, setFormat] = useState('md'); const [busy, setBusy] = useState(false); async function generate() { setBusy(true); try { const report = await request(`/api/datasets/${data.dataset_id}/reports`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, format }) }); await refresh(data.dataset_id); download(report.download_url); notify('Report generated from live dataset evidence.') } catch (error) { notify(error.message) } finally { setBusy(false) } } return <div className="workspace-page"><Head eyebrow="REPORTS / EXPORT" title="Tell the story." copy="Generate a live report from the current profile, quality findings, and version history." /><section className="report-feature report-feature-polished"><div className="report-preview"><Badge tone="green">LIVE DATASET</Badge><h2>Evidence, shaped into a story.</h2><p>Profile, quality, analysis, and lineage in one export.</p><div className="report-preview-line" /></div><div className="report-copy"><h2>Generate a traceable report</h2><p>No template numbers are used. This report is generated from <b>{data.file_name}</b> at export time.</p><div className="report-form-grid"><label>Report title<input value={title} onChange={event => setTitle(event.target.value)} /></label><label>Format<select value={format} onChange={event => setFormat(event.target.value)}><option value="md">Markdown</option><option value="csv">CSV</option><option value="pdf">PDF</option></select></label></div><Button onClick={generate} disabled={busy}><Download size={15} /> {busy ? 'Generating…' : 'Generate report'}</Button></div></section><section className="report-history panel"><div className="panel-heading"><div><span className="panel-kicker">REPORT HISTORY</span><h3>{data.reports?.length ? 'Generated reports' : 'No reports yet'}</h3></div></div>{(data.reports || []).map(report => <article key={report.id}><span className="report-file-icon"><FileBarChart2 size={17} /></span><div><b>{report.title}</b><small>{report.format.toUpperCase()} · {new Date(report.created_at).toLocaleString()}</small></div><button className="text-button" onClick={() => download(`/api/datasets/${data.dataset_id}/reports/${report.id}/download`)}>Download <ChevronRight size={13} /></button></article>)}</section></div> }
function formatVersionDetail(detail, operation) {
  if (!detail) return 'Original source preserved; no changes applied.'
  if (!detail.startsWith('{')) return detail
  try {
    const parsed = JSON.parse(detail)
    const metrics = parsed.metrics || {}
    const parts = []

    if (operation.includes('trim_text')) {
      parts.push(`Trimmed leading/trailing whitespace in text columns.`)
      if (metrics.affected_rows) parts.push(`Affected rows: ${metrics.affected_rows.toLocaleString()}`)
    } else if (operation.includes('remove_duplicates')) {
      parts.push(`Removed duplicate records.`)
      if (metrics.removed_rows) parts.push(`Removed rows: ${metrics.removed_rows.toLocaleString()}`)
    } else if (operation.includes('normalize_columns')) {
      parts.push(`Normalized column headers to SQL-safe snake_case.`)
      if (metrics.renamed) {
        const renamedList = Object.entries(metrics.renamed).map(([old, next]) => `${old} → ${next}`).join(', ')
        parts.push(`Renamed columns: ${renamedList}`)
      }
    } else if (operation.includes('parse_dates')) {
      parts.push(`Intelligently detected and parsed date columns.`)
      if (metrics.columns && metrics.columns.length) {
        parts.push(`Date columns standardized: ${metrics.columns.join(', ')}`)
      }
    } else if (operation.includes('fill_missing')) {
      parts.push(`Filled missing values using median/mode strategy.`)
      if (metrics.filled_values) parts.push(`Filled cells count: ${metrics.filled_values.toLocaleString()}`)
    } else if (operation.includes('remove_outliers')) {
      parts.push(`Excluded extreme outliers using 1.5× IQR fence.`)
      if (metrics.removed_rows) parts.push(`Excluded rows count: ${metrics.removed_rows.toLocaleString()}`)
    } else if (operation.includes('standardize_format')) {
      parts.push(`Standardized formats dynamically: unified numeric types, parsed date values, and trimmed text.`)
      const stats = []
      if (metrics.trimmed_cells) stats.push(`trimmed ${metrics.trimmed_cells.toLocaleString()} cells`)
      if (metrics.numeric_cells_normalized) stats.push(`normalized ${metrics.numeric_cells_normalized.toLocaleString()} numbers`)
      if (metrics.invalid_dates_normalized) stats.push(`parsed ${metrics.invalid_dates_normalized.toLocaleString()} dates`)
      if (stats.length) parts.push(`Action stats: ${stats.join(', ')}`)
    } else {
      parts.push(`Applied operation: ${operation.replaceAll('_', ' ')}`)
    }

    if (parsed.profile?.quality_score) {
      parts.push(`Quality Score: ${parsed.profile.quality_score}/100`)
    }

    return parts.join(' · ')
  } catch (error) {
    return detail
  }
}

function parseBold(text) {
  if (typeof text !== 'string') return text;
  const parts = [];
  const regex = /\*\*(.*?)\*\*/g;
  let match;
  let lastIndex = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }
    parts.push(<strong key={match.index}>{match[1]}</strong>);
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }
  return parts.length > 0 ? parts : text;
}

function MarkdownText({ content }) {
  if (!content) return null;
  const lines = content.split('\n');
  return (
    <div className="markdown-content" style={{ fontSize: '12px', color: '#45695c' }}>
      {lines.map((line, lineIndex) => {
        const trimmed = line.trim();
        if (trimmed.startsWith('### ')) {
          return <h4 key={lineIndex} style={{ margin: '14px 0 6px', color: '#153f36', fontSize: '13px', fontWeight: '600' }}>{parseBold(trimmed.substring(4))}</h4>;
        }
        if (trimmed.startsWith('## ')) {
          return <h3 key={lineIndex} style={{ margin: '16px 0 8px', color: '#153f36', fontSize: '14px', fontWeight: '600' }}>{parseBold(trimmed.substring(3))}</h3>;
        }
        if (trimmed.startsWith('* ') || trimmed.startsWith('- ')) {
          return (
            <div key={lineIndex} style={{ display: 'flex', gap: '8px', paddingLeft: '8px', margin: '4px 0', alignItems: 'start' }}>
              <span style={{ color: '#138463' }}>•</span>
              <div>{parseBold(trimmed.substring(2))}</div>
            </div>
          );
        }
        const numberedMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
        if (numberedMatch) {
          return (
            <div key={lineIndex} style={{ display: 'flex', gap: '8px', paddingLeft: '8px', margin: '4px 0', alignItems: 'start' }}>
              <span style={{ color: '#138463', fontWeight: '500' }}>{numberedMatch[1]}.</span>
              <div>{parseBold(numberedMatch[2])}</div>
            </div>
          );
        }
        if (trimmed === '') return <div key={lineIndex} style={{ height: '6px' }} />;
        return <p key={lineIndex} style={{ margin: '6px 0', lineHeight: '1.6' }}>{parseBold(line)}</p>;
      })}
    </div>
  );
}

function SupportingDataTable({ columns, rows }) {
  const [expanded, setExpanded] = useState(false);
  const displayLimit = 5;
  const hasMore = rows.length > displayLimit;
  const visibleRows = expanded ? rows : rows.slice(0, displayLimit);
  return (
    <div className="supporting-data-wrap" style={{ margin: '12px 0 6px' }}>
      <Grid columns={columns} rows={visibleRows} />
      {hasMore && (
        <button 
          type="button"
          className="text-button" 
          style={{ marginTop: '8px', fontWeight: '500', display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'Show less' : `Show all ${rows.length} rows`} <ChevronRight size={13} style={{ transform: expanded ? 'rotate(-90deg)' : 'none', transition: 'transform 0.2s' }} />
        </button>
      )}
    </div>
  );
}

function Lineage({ data, page, activate }) {
  const versions = data.versions || [];
  return (
    <div className="workspace-page">
      <Head
        eyebrow={`DATASET / ${page.toUpperCase()}`}
        title={page === 'Lineage' ? 'See every connection.' : 'Version history'}
        copy="The original source is preserved. Approved transformations are recorded here."
      />
      <div className="lineage-list">
        {versions.length ? (
          versions.map((version, index) => (
            <div className="lineage-item" key={version.id}>
              <span className={`lineage-node ${index ? 'clean' : 'source'}`}>
                {index ? <WandSparkles size={16} /> : <Database size={16} />}
              </span>
              <div className="lineage-detail">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Badge tone={index ? 'green' : 'purple'}>
                    {index ? `VERSION ${version.number}` : 'SOURCE'}
                  </Badge>
                  <span style={{ fontSize: '9px', color: '#9aa69f' }}>
                    {new Date(version.created_at).toLocaleString()}
                  </span>
                </div>
                <h3 style={{ textTransform: 'uppercase', letterSpacing: '0.03em' }}>{index ? version.operation.replace('executed:', '').replaceAll('_', ' ') : data.file_name}</h3>
                <p style={{ marginTop: '8px', color: '#537167', fontSize: '11px', lineHeight: '1.5' }}>
                  {formatVersionDetail(version.detail, version.operation)}
                </p>
              </div>
              {index > 0 && data.active_version !== version.number && (
                <button type="button" className="text-button" style={{ alignSelf: 'center', marginLeft: '12px' }} onClick={() => activate(version.number)}>
                  Activate
                </button>
              )}
              {index > 0 && data.active_version === version.number && (
                <Badge tone="green" style={{ alignSelf: 'center', marginLeft: '12px' }}>Active</Badge>
              )}
            </div>
          ))
        ) : (
          <div className="lineage-empty">
            <GitBranch size={20} />
            <b>No lineage entries yet.</b>
            <span>Upload a dataset to begin the lineage.</span>
          </div>
        )}
      </div>
    </div>
  );
}

function ProfilePage({ profile, save }) { const [draft, setDraft] = useState(profile); const fileInput = useRef(); const update = key => event => setDraft(current => ({ ...current, [key]: event.target.value })); function chooseImage(event) { const file = event.target.files?.[0]; if (!file) return; if (!file.type.startsWith('image/')) return notify('Choose an image file.'); const reader = new FileReader(); reader.onload = () => setDraft(current => ({ ...current, avatar: reader.result })); reader.readAsDataURL(file) } const initialsText = initials(draft); return <div className="workspace-page"><Head eyebrow="ACCOUNT / PERSONAL PROFILE" title="Your profile." copy="These details personalize the workspace, sidebar, avatar, and future reports." action={<Button onClick={() => save(draft)}><Check size={15} /> Save changes</Button>} /><section className="personal-profile-grid"><div className="profile-form-card"><div className="profile-cover"><div className="profile-avatar-large">{draft.avatar ? <img src={draft.avatar} alt="Profile" /> : initialsText}</div><div><h2>{draft.fullName || 'Workspace user'}</h2><p>{draft.role || 'Add your role'}{draft.company ? ` · ${draft.company}` : ''}</p></div></div><div className="form-section"><div className="profile-form-grid"><label>Full name<input value={draft.fullName || ''} onChange={update('fullName')} placeholder="Amelia King" /></label><label>Email address<input type="email" value={draft.email || ''} onChange={update('email')} placeholder="you@company.com" /></label><label>Role / title<input value={draft.role || ''} onChange={update('role')} placeholder="Data lead" /></label><label>Company<input value={draft.company || ''} onChange={update('company')} placeholder="Pivot Labs" /></label><label>Profile image<button type="button" className="file-choose" onClick={() => fileInput.current?.click()}>Choose an image</button><input ref={fileInput} hidden type="file" accept="image/*" onChange={chooseImage} /></label><label>Timezone<select value={draft.timezone || 'Asia/Calcutta'} onChange={update('timezone')}><option>Asia/Calcutta</option><option>UTC</option><option>America/New_York</option><option>Europe/London</option></select></label><label className="full-field">Short bio<textarea value={draft.bio || ''} onChange={update('bio')} rows="4" placeholder="What do you work on?" /></label></div></div></div><aside className="profile-side-column"><div className="account-card"><span className="panel-kicker">ACCOUNT STATUS</span><div className="account-status"><i /> Local account active</div><p>Production authentication and team access will be connected later.</p><div className="account-line"><span>Email</span><b>{draft.email || 'Not set'}</b></div><div className="account-line"><span>Timezone</span><b>{draft.timezone || 'Asia/Calcutta'}</b></div></div><div className="profile-tip"><Sparkles size={17} /><b>Your profile travels with you.</b><p>Saved identity details appear in the avatar, sidebar, and generated report context.</p></div></aside></section></div> }
function SettingsPage({ data, profile, onReset }) { const [settings, setSettings] = useState(() => ({ grounded: true, emailAlerts: false, compact: false, theme: 'light', ...readJson('pivot-settings') })); const [active, setActive] = useState('general'); function update(key, value) { const next = { ...settings, [key]: value }; setSettings(next); localStorage.setItem('pivot-settings', JSON.stringify(next)); if (key === 'compact') document.body.classList.toggle('compact-tables', value) } function jump(id) { setActive(id); document.getElementById(`setting-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) } return <div className="workspace-page"><Head eyebrow="WORKSPACE / SETTINGS" title="Settings that matter." copy="Control how this browser presents and protects your Pivot workspace." /><div className="settings-layout-polished"><aside className="settings-nav-card"><b>Workspace settings</b>{[['general', 'General'], ['ai', 'AI Analyst'], ['notifications', 'Notifications'], ['safeguards', 'Data safeguards']].map(([id, label]) => <button className={active === id ? 'active' : ''} key={id} onClick={() => jump(id)}>{label}<ChevronRight size={12} /></button>)}</aside><div className="settings-panels"><section id="setting-general" className="settings-panel"><span className="panel-kicker">GENERAL</span><h3>Workspace preferences</h3><p>{data.file_name} is your active source.</p><label>Display theme<select value={settings.theme} onChange={event => update('theme', event.target.value)}><option value="light">Light</option><option value="system">System</option></select></label><label className="setting-check"><input type="checkbox" checked={settings.compact} onChange={event => update('compact', event.target.checked)} /> Use compact data tables</label></section><section id="setting-ai" className="settings-panel"><span className="panel-kicker">AI ANALYST</span><h3>Evidence controls</h3><div className="setting-row"><span><b>Grounded evidence mode</b><small>AI answers must use detected schema and executed evidence.</small></span><button className={`toggle ${settings.grounded ? 'on' : ''}`} onClick={() => update('grounded', !settings.grounded)}><i /></button></div><div className="setting-row"><span><b>Model</b><small>Gemini · {settings.grounded ? 'evidence-first' : 'standard explanation'}</small></span><Badge tone="green">Connected</Badge></div></section><section id="setting-notifications" className="settings-panel"><span className="panel-kicker">NOTIFICATIONS</span><h3>Workspace updates</h3><label className="setting-check"><input type="checkbox" checked={settings.emailAlerts} onChange={event => update('emailAlerts', event.target.checked)} /> Notify me about quality findings</label><p className="settings-note">Email delivery will activate when production auth is connected.</p></section><section id="setting-safeguards" className="settings-panel safeguards"><span className="panel-kicker">DATA SAFEGUARDS</span><h3>Always enforced</h3><div className="safeguard-grid"><span><LockKeyhole size={16} /><b>Original preserved</b><small>Source files are never overwritten.</small></span><span><ShieldCheck size={16} /><b>Read-only SQL</b><small>Only SELECT and WITH queries run.</small></span><span><GitBranch size={16} /><b>Versioned cleaning</b><small>Approved changes create new versions.</small></span></div></section><section className="settings-panel danger"><span className="panel-kicker">DATASET SESSION</span><h3>Choose another source</h3><p>This returns to the upload workspace without deleting stored files.</p><Button variant="outline" onClick={onReset}>Choose another dataset</Button></section></div></div></div> }

function AnalystV3({ data, question, setQuestion, messages, ask, busy, attachContext, profile }) {
  const userInitials = initials(profile || {})
  const threadRef = useRef(null)
  const contextInput = useRef(null)
  
  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight
    }
  }, [messages, busy])

  return (
    <div className="workspace-page analyst-page">
      <Head 
        eyebrow="AI ANALYST / GROUNDED" 
        title="Ask anything about your data." 
        copy="Answers, actions, exports, and evidence from the active dataset." 
        action={<span className="ai-status"><i /> Evidence mode</span>} 
      />
      <div className="analyst-layout">
        <div className="analyst-main">
          <div className="analyst-intro">
            <span className="analyst-orb"><Bot size={27} /></span>
            <h2>What would you like to investigate?</h2>
            <p>Ask naturally: “Which product sales are highest?” or “Fix messy date formats and give me an updated CSV.”</p>
          </div>
          <div className="suggested-prompts">
            <button type="button" onClick={() => ask('Which product sales are highest?')}>Which product sales are highest? <ChevronRight size={14} /></button>
            <button type="button" onClick={() => ask('When did sales drop the most, and what changed?')}>When did sales drop the most? <ChevronRight size={14} /></button>
            <button type="button" onClick={() => ask('Fix the messy date formats and give me an updated CSV')}>Fix messy formats + export <ChevronRight size={14} /></button>
          </div>
          <div className="chat-thread" ref={threadRef}>
            {messages.length === 0 ? (
              <div className="chat-empty">
                <Bot size={18} />
                <span>Start a conversation. I’ll calculate answers from {data.file_name} and keep the supporting evidence here.</span>
              </div>
            ) : (
              messages.map((message, index) => (
                <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                  <div className="chat-bubble">
                    <div className="answer-head">
                      <span className="analyst-avatar">
                        {message.role === 'user' ? userInitials : <Bot size={15} />}
                      </span>
                      <b>{message.role === 'user' ? 'You' : 'Pivot Analyst'}</b>
                      {message.source && <Badge tone="green">{message.source}</Badge>}
                    </div>
                    {message.pending ? (
                      <p className="chat-pending"><RefreshCw size={14} className="spin" /> Investigating the source…</p>
                    ) : (
                      <>
                        <div style={{ marginTop: '11px' }}>
                          <MarkdownText content={message.text} />
                        </div>
                        {message.action?.status === 'approved' && message.download_url && (
                          <div style={{ marginTop: '12px' }}>
                            <Button variant="outline" onClick={() => download(message.download_url)}>
                              <Download size={14} /> Download updated CSV
                            </Button>
                          </div>
                        )}
                        {message.action?.status === 'preview' && (
                          <div className="action-note" style={{ marginTop: '10px', fontSize: '11px', color: '#be653a' }}>
                            <WandSparkles size={14} style={{ inlineSize: 'auto', display: 'inline', marginRight: '4px' }} /> Preview ready in Cleaning for review.
                          </div>
                        )}
                        {message.insights?.length > 0 && (
                          <div className="analyst-insights" style={{ marginTop: '12px', background: '#f5faf5', padding: '10px', borderRadius: '6px', border: '1px solid #e0ede0' }}>
                            <b style={{ fontSize: '10px', color: '#153f36', textTransform: 'uppercase', display: 'block', marginBottom: '6px' }}>What stands out</b>
                            {message.insights.map((insight, insightIndex) => (
                              <span key={insightIndex} style={{ display: 'flex', gap: '6px', fontSize: '11px', color: '#3d6356', margin: '4px 0', alignItems: 'center' }}>
                                <CheckCircle2 size={13} style={{ color: '#138463' }} /> {insight}
                              </span>
                            ))}
                          </div>
                        )}
                        <AnalystVisualization visualization={message.visualization} />
                        {message.driver_rows?.length > 0 && (
                          <div style={{ marginTop: '12px' }}>
                            <div className="answer-label" style={{ fontSize: '9px', fontWeight: 'bold', color: '#789087', margin: '8px 0' }}>ASSOCIATED CHANGE BY GROUP</div>
                            <Grid columns={Object.keys(message.driver_rows[0])} rows={message.driver_rows} />
                          </div>
                        )}
                        {message.query_result?.rows?.length > 0 && (
                          <div style={{ marginTop: '12px' }}>
                            <div className="answer-label" style={{ fontSize: '9px', fontWeight: 'bold', color: '#789087', margin: '8px 0' }}>SUPPORTING DATA</div>
                            <SupportingDataTable columns={message.query_result.columns || Object.keys(message.query_result.rows[0])} rows={message.query_result.rows} />
                          </div>
                        )}
                        {message.sql && (
                          <details className="evidence-details" style={{ marginTop: '12px' }}>
                            <summary style={{ fontSize: '11px', cursor: 'pointer', color: '#138463', outline: 'none' }}>Show calculation query</summary>
                            <pre style={{ background: '#102f29', color: '#d2e9dc', padding: '10px', borderRadius: '6px', fontSize: '10px', overflowX: 'auto', marginTop: '6px' }}>{message.sql}</pre>
                          </details>
                        )}
                        {message.role === 'assistant' && (
                          <small style={{ display: 'block', fontSize: '9px', color: '#88968f', marginTop: '10px' }}>
                            Based on: {(message.citations || []).map(source => source.source).join(', ') || data.file_name}
                          </small>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="ask-composer">
            <textarea 
              value={question} 
              onChange={event => setQuestion(event.target.value)} 
              onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); ask() } }} 
              placeholder="Ask anything about your data..." 
              rows="2" 
            />
            <div>
              <span><Sparkles size={14} /> Calculated from {data.file_name}</span>
              <button type="button" className="chat-attach" onClick={() => contextInput.current?.click()} disabled={busy} aria-label="Attach business context">
                <FileBarChart2 size={15} /> Context
              </button>
              <button type="button" onClick={ask} disabled={busy || !question.trim()}>
                {busy ? <RefreshCw size={14} className="spin" /> : <Send size={16} />}
              </button>
            </div>
          </div>
        </div>
        <aside className="analyst-aside">
          <div className="aside-card">
            <span className="panel-kicker">HOW IT WORKS</span>
            <div className="how-step">
              <span>1</span>
              <div>
                <b>Understand the schema</b>
                <small>Relevant dates, metrics, and grouping fields are detected.</small>
              </div>
            </div>
            <div className="how-step">
              <span>2</span>
              <div>
                <b>Calculate from the source</b>
                <small>Answers use the active dataframe, not invented sample numbers.</small>
              </div>
            </div>
            <div className="how-step">
              <span>3</span>
              <div>
                <b>Act on the result</b>
                <small>Cleaning requests create a new version and export it without changing the original.</small>
              </div>
            </div>
          </div>
          <div className="aside-card" style={{ marginTop: '12px' }}>
            <span className="panel-kicker">BUSINESS CONTEXT</span>
            <b style={{ display: 'block', margin: '7px 0' }}>Teach Pivot your definitions.</b>
            <small>Attach a glossary or data dictionary so answers use your business language.</small>
            <input ref={contextInput} hidden type="file" accept=".pdf,.txt,.md,.json" onChange={event => attachContext(event.target.files?.[0]).finally(() => { event.target.value = '' })} />
            <Button variant="outline" onClick={() => contextInput.current?.click()} disabled={busy}>
              <FileBarChart2 size={14} /> Attach context
            </Button>
          </div>
        </aside>
      </div>
    </div>
  )
}
function ProfilePageV2({ profile, save, user }) {
  const [draft, setDraft] = useState(profile)
  const fileInput = useRef(null)
  useEffect(() => setDraft(profile), [profile])
  const update = key => event => setDraft(current => ({ ...current, [key]: event.target.value }))
  const chooseImage = event => { const file = event.target.files?.[0]; if (!file?.type.startsWith('image/')) return; const reader = new FileReader(); reader.onload = () => setDraft(current => ({ ...current, avatar: reader.result })); reader.readAsDataURL(file) }
  return <div className="workspace-page"><Head eyebrow="ACCOUNT / PERSONAL PROFILE" title="Your profile." copy="Your Google account is the source of truth for identity and verified email." action={<Button onClick={() => save(draft)}><Check size={15}/> Save changes</Button>}/><section className="personal-profile-grid"><div className="profile-form-card"><div className="profile-cover"><div className="profile-avatar-large">{draft.avatar ? <img src={draft.avatar} alt="Profile" onError={event => { event.currentTarget.style.display = 'none' }}/> : initials(draft)}</div><div><h2>{draft.fullName || 'Workspace user'}</h2><p>{draft.role || 'Add your role'}{draft.company ? ` · ${draft.company}` : ''}</p></div></div><div className="form-section"><div className="profile-form-grid"><label>Full name<input value={draft.fullName || ''} onChange={update('fullName')}/></label><label>Email address<input type="email" value={draft.email || ''} readOnly/><small>Verified through Google</small></label><label>Role / title<input value={draft.role || ''} onChange={update('role')} placeholder="Data lead"/></label><label>Company<input value={draft.company || ''} onChange={update('company')} placeholder="Company"/></label><label>Profile image<button type="button" className="file-choose" onClick={() => fileInput.current?.click()}>Choose an image</button><input ref={fileInput} hidden type="file" accept="image/*" onChange={chooseImage}/></label><label>Timezone<select value={draft.timezone || 'Asia/Calcutta'} onChange={update('timezone')}><option>Asia/Calcutta</option><option>UTC</option><option>America/New_York</option><option>Europe/London</option></select></label><label className="full-field">Short bio<textarea value={draft.bio || ''} onChange={update('bio')} rows="4" placeholder="What do you work on?"/></label></div></div></div><aside className="profile-side-column"><div className="account-card"><span className="panel-kicker">ACCOUNT STATUS</span><div className="account-status"><i/> Google account connected</div><p>Your Google identity is used for secure workspace access.</p><div className="account-line"><span>Authentication</span><b>Google</b></div><div className="account-line"><span>Email</span><b>{user?.email || draft.email || 'Not set'}</b></div><div className="account-line"><span>Timezone</span><b>{draft.timezone || 'Asia/Calcutta'}</b></div></div></aside></section></div>
}

export default function AppPolished() {
  const { user, restoring: authRestoring, logout: authLogout } = useAuth()
  const input = useRef(); const [data, setData] = useState(null); const [overview, setOverview] = useState(null); const [analyses, setAnalyses] = useState([]); const [selected, setSelected] = useState(null); const [page, setPage] = useState('Home'); const [busy, setBusy] = useState(false); const [chatBusy, setChatBusy] = useState(false); const [message, setMessage] = useState(''); const [toast, setToast] = useState(''); const [profile, setProfile] = useState(() => readJson('pivot-personal-profile')); const [authMode, setAuthMode] = useState(null); const [transitioning, setTransitioning] = useState(false); const authenticated = Boolean(user); const [restoring, setRestoring] = useState(() => Boolean(localStorage.getItem('pivot-active-dataset'))); const [question, setQuestion] = useState(''); const [messages, setMessages] = useState([]); const [sql, setSql] = useState('SELECT * FROM dataset LIMIT 20'); const [result, setResult] = useState(null); const [preview, setPreview] = useState(null); const [autoPilot, setAutoPilot] = useState(null)
  useEffect(() => { if (user) setProfile(current => ({ ...current, fullName: user.full_name, name: user.full_name, email: user.email, avatar: user.avatar_url })) }, [user])
  useEffect(() => { const listener = event => { setToast(text(event.detail)); clearTimeout(window.__pivotToastTimer); window.__pivotToastTimer = setTimeout(() => setToast(''), 3000) }; window.addEventListener('pivot:notice', listener); return () => window.removeEventListener('pivot:notice', listener) }, [])
  async function refresh(id) { const [latest, nextOverview, nextAnalyses, nextAutoPilot] = await Promise.all([request(`/api/datasets/${id}`), request(`/api/datasets/${id}/overview`), request(`/api/datasets/${id}/analyses`), request(`/api/datasets/${id}/autopilot`)]); const normalized = normalizeDataset(latest); setData(normalized); setOverview(nextOverview); setAnalyses(nextAnalyses.analyses || []); setAutoPilot(nextAutoPilot.report ? null : nextAutoPilot); return normalized }
  useEffect(() => { const id = localStorage.getItem('pivot-active-dataset'); if (!authenticated || !id) { setRestoring(false); return } refresh(id).catch(() => { localStorage.removeItem('pivot-active-dataset'); setMessage('Your previous dataset session is unavailable. Please upload it again.') }).finally(() => setRestoring(false)) }, [authenticated])
  function openAuth(mode) { setTransitioning(true); setTimeout(() => { setAuthMode(mode); setTransitioning(false) }, 260) }
  async function upload(file) { if (!file) return; setBusy(true); setMessage('Reading your file and building its profile…'); try { const form = new FormData(); form.append('file', file); const uploaded = await request('/api/datasets', { method: 'POST', body: form }); localStorage.setItem('pivot-active-dataset', uploaded.dataset_id); await refresh(uploaded.dataset_id); setPage('Home'); setMessage('Your dataset is ready.') } catch (error) { setMessage(error.message) } finally { setBusy(false) } }
  function reset() { localStorage.removeItem('pivot-active-dataset'); setData(null); setOverview(null); setAnalyses([]); setPreview(null); setAutoPilot(null); setMessages([]); setResult(null); setPage('Home'); setMessage('') }
  async function logout() { await authLogout(); setAuthMode(null); reset() }
  function saveProfile(next) { setProfile(next); localStorage.setItem('pivot-personal-profile', JSON.stringify(next)); notify('Profile saved. Your avatar and identity are updated across the workspace.') }
  async function ask(prompt) { const asked = String(prompt ?? question).trim(); if (!data?.dataset_id || chatBusy) return; if (asked.length < 2 || !/[a-z0-9]/i.test(asked)) { notify('Ask Pivot a question with a little more detail.'); return } setQuestion(''); setChatBusy(true); setMessages(current => [...current, { role: 'user', text: asked }, { role: 'assistant', pending: true }]); try { const response = await request('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset_id: data.dataset_id, question: asked, context: { page, history: messages.slice(-6).map(item => ({ role: item.role, text: typeof item.text === 'string' ? item.text : '' })) } }) }); setMessages(current => [...current.slice(0, -1), { role: 'assistant', text: String(response.answer || 'Pivot could not produce an answer for that request.'), source: response.source, sql: response.sql, query_result: response.query_result, rows: response.rows, insights: response.insights, driver_rows: response.driver_rows, visualization: response.visualization, action: response.action, download_url: response.download_url, citations: response.citations }]); if (response.action?.status === 'approved') { await refresh(data.dataset_id); notify('A new cleaned dataset version is ready to download.') } } catch (error) { setMessages(current => [...current.slice(0, -1), { role: 'assistant', text: error.message || 'Pivot could not complete that request. Please try again.', source: 'error' }]) } finally { setChatBusy(false) } }
  async function runSql() { if (!data?.dataset_id) return; setBusy(true); try { setResult(await request('/api/sql/execute', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dataset_id: data.dataset_id, query: sql }) })) } catch (error) { notify(error.message) } finally { setBusy(false) } }
  async function previewOp(operation) { setBusy(true); try { setPreview(await request(`/api/datasets/${data.dataset_id}/transformations/${operation}/preview`, { method: 'POST' })) } catch (error) { notify(error.message) } finally { setBusy(false) } }
  async function approve() { setBusy(true); try { await request(`/api/datasets/${data.dataset_id}/transformations/${preview.id}/approve`, { method: 'POST' }); setPreview(null); await refresh(data.dataset_id); notify('Version approved and lineage updated.') } catch (error) { notify(error.message) } finally { setBusy(false) } }
  async function reject() { try { await request(`/api/datasets/${data.dataset_id}/transformations/${preview.id}/reject`, { method: 'POST' }); setPreview(null); notify('Preview rejected; source unchanged.') } catch (error) { notify(error.message) } }
  async function runAnalysis(item) { setBusy(true); try { const output = await request(`/api/datasets/${data.dataset_id}/analyses/run`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kind: item.kind, column: item.column || null }) }); setSelected({ id: item.id, result: output }) } catch (error) { notify(error.message) } finally { setBusy(false) } }
  async function runAutoPilot() { if (!data?.dataset_id) return; setBusy(true); try { const report = await request(`/api/datasets/${data.dataset_id}/autopilot`, { method: 'POST' }); setAutoPilot(report); await refresh(data.dataset_id); setPage('Auto Pilot'); notify('Auto Pilot completed. A cleaned version and briefing are ready.') } catch (error) { notify(error.message) } finally { setBusy(false) } }
  async function attachContext(file) { if (!file || !data?.dataset_id) return; setChatBusy(true); try { const form = new FormData(); form.append('file', file); const result = await request(`/api/datasets/${data.dataset_id}/context`, { method: 'POST', body: form }); await refresh(data.dataset_id); notify(`${result.source} added to the analyst context.`) } catch (error) { notify(error.message) } finally { setChatBusy(false) } }
  async function activateVersion(version) { try { await request(`/api/datasets/${data.dataset_id}/versions/${version}/activate`, { method: 'POST' }); await refresh(data.dataset_id); notify(`Version ${version} is now active.`) } catch (error) { notify(error.message) } }
  if (!data && authRestoring) return <div className="route-transition"><div className="route-loader" /><b>Restoring your secure session</b><span>One moment…</span></div>
  if (transitioning) return <div className="route-transition"><div className="route-loader" /><b>Preparing your secure workspace</b><span>One moment…</span></div>
  if (!data && restoring) return <div className="route-transition"><div className="route-loader" /><b>Restoring your dataset</b><span>Reconnecting to its profile and lineage…</span></div>
  if (!data && authMode) return <Auth back={() => setAuthMode(null)} />
  if (!data && authenticated) return <Upload input={input} busy={busy} message={message} upload={upload} logout={logout} user={user} />
  if (!data) return <LandingV2 start={() => openAuth('signup')} signIn={() => openAuth('login')} />
  const go = next => setPage(next); let content
  if (page === 'Home') content = <Overview data={data} overview={overview} go={go} />
  else if (page === 'Generate Brief') content = <AutoPilot data={data} busy={busy} report={autoPilot} run={runAutoPilot} />
  else if (page === 'Data') content = <DataWorkspace data={data} busy={busy} preview={preview} previewOp={previewOp} approve={approve} reject={reject} />
  else if (page === 'Analyze') content = <Analysis analyses={analyses} busy={busy} selected={selected} run={runAnalysis} />
  else if (page === 'Ask Pivot') content = <AnalystV3 data={data} question={question} setQuestion={setQuestion} messages={messages} ask={ask} busy={chatBusy} attachContext={attachContext} profile={profile} />
  else if (page === 'SQL') content = <SQL data={data} sql={sql} setSql={setSql} result={result} run={runSql} busy={busy} />
  else if (page === 'Reports') content = <Reports data={data} refresh={refresh} />
  else if (page === 'History') content = <Lineage data={data} page="History" activate={activateVersion} />
  else if (page === 'My Profile') content = <ProfilePageV2 profile={profile} save={saveProfile} user={user} />
  else content = <SettingsPage data={data} profile={profile} onReset={reset} />
  return <><Shell data={data} profile={profile} page={page} setPage={setPage} reset={reset}>{content}</Shell>{toast && <div className="app-toast"><CheckCircle2 size={15} />{toast}</div>}</>
}
