import { Upload } from 'lucide-react'

export default function EmptyState({ open }) {
  return <section className="empty-state"><span className="orb"/><p className="eyebrow">PIVOT DATA INTELLIGENCE</p><h1>Turn raw data into<br/><em>real decisions.</em></h1><p>Upload a dataset and Pivot will profile it, identify quality issues, and build the context needed for reliable analysis.</p><button className="primary" onClick={open}><Upload size={16}/>Upload dataset</button><small>CSV · Excel · JSON · Parquet</small></section>
}
