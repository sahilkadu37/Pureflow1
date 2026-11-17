import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { AnimatePresence, motion, MotionConfig } from 'framer-motion'
import { Activity, CheckCircle2, ChevronRight, CloudSun, Database, Droplets, FileCheck2, FileText, Gauge, GitMerge, Globe2, LayoutDashboard, Menu, Search, ShieldCheck, Sparkles, Waves, X, Thermometer, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getDashboard } from './services/api'
import DatasetExplorer from './pages/DatasetExplorer'
import DataQuality from './pages/DataQuality'
import DatasetIntegration from './pages/DatasetIntegration'
import SQLAnalytics from './pages/SQLAnalytics'
import Reports from './pages/Reports'
import WaterAnalytics from './pages/WaterAnalytics'
import ClimateAnalysis from './pages/ClimateAnalysis'
import WaterStress from './pages/WaterStress'
import { GeometricBackground } from './components/GeometricDecorations'
import IntroScreen from './components/IntroScreen'
import './App.css'

const navSections = [
  ['OVERVIEW', [['Overview', '/', LayoutDashboard]]],
  ['WORKSPACE', [['Dataset Explorer', '/datasets', Database], ['Upload Dataset', '/datasets#upload', FileText], ['Data Quality', '/quality', ShieldCheck], ['Data Cleaning', '/quality', Sparkles], ['Data Integration', '/integration', GitMerge]]],
  ['ANALYTICS', [['Water Analytics', '/water', Droplets], ['WUE Analysis', '/water', Gauge], ['Climate Analysis', '/climate', CloudSun], ['Water Stress', '/stress', Globe2], ['Insights', '/reports', Sparkles]]],
  ['DATABASE', [['Database Management', '/sql', Database], ['SQL Query Explorer', '/sql', Activity]]],
  ['REPORTING', [['Reporting Centre', '/reports', FileText], ['Report History', '/reports', FileCheck2]]],
]
const pages = {
  '/': ['Water Intelligence Overview', 'Monitor data-centre water consumption, efficiency and environmental sustainability.'],
  '/datasets': ['Dataset Explorer', 'Review source files and prepare data for analysis.'],
  '/quality': ['Data Quality', 'Understand completeness, consistency and validation readiness.'],
  '/integration': ['Dataset Integration', 'Standardise curated datasets and integrate only verified compatible records.'],
  '/water': ['Water Analytics', 'Explore consumption patterns and water usage effectiveness.'],
  '/climate': ['Climate Analysis', 'Connect local climate conditions with data-centre water use.'],
  '/stress': ['Water Stress Map', 'Explore water stress exposure across facility locations.'],
  '/sql': ['SQL Analytics', 'Query the connected analytical data store.'],
  '/reports': ['Reports and Insights', 'Turn validated analysis into shareable sustainability reporting.'],
}

function Sidebar({ collapsed, setCollapsed, mobileOpen, closeMobile }) {
  const { pathname, hash } = useLocation()
  const primaryLabels = { '/datasets': 'Dataset Explorer', '/quality': 'Data Quality', '/integration': 'Data Integration', '/water': 'Water Analytics', '/sql': 'Database Management', '/reports': 'Reporting Centre' }
  return <>
    {mobileOpen && <button className="scrim" aria-label="Close navigation" onClick={closeMobile} />}
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
      <div className="brand"><div className="brand-mark"><span className="brand-mark-orbit"/><Droplets size={17} /></div><div className="brand-name">PURE<span>FLOW</span><small>WATER SUSTAINABILITY ANALYTICS</small></div><button className="mobile-close" onClick={closeMobile} aria-label="Close navigation"><X size={18}/></button></div>
      <nav className="nav-groups">{navSections.map(([section, entries]) => <div className="nav-group" key={section}><div className="workspace-label">{section}</div>{entries.map(([label, path, Icon]) => <NavLink key={`${section}-${label}`} to={path} end={path === '/'} onClick={closeMobile} className={({ isActive }) => {
        const selected = path === '/datasets#upload' ? pathname === '/datasets' && hash === '#upload' : isActive && (!primaryLabels[path] || primaryLabels[path] === label)
        return `nav-item ${selected ? 'active' : ''}`
      }} title={collapsed ? label : undefined}><Icon size={17}/><span>{label}</span></NavLink>)}</div>)}</nav>
      <div className="sidebar-bottom"><div className="sidebar-profile"><div className="sidebar-avatar">PF</div><span><b>PureFlow</b><small>Workspace</small></span></div><button className="collapse-btn" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{collapsed ? <PanelLeftOpen size={17}/> : <PanelLeftClose size={17}/>} {!collapsed && 'Collapse'}</button></div>
    </aside>
  </>
}

function Header({ title, openMobile }) {
  return <header className="topbar"><div className="top-left"><button className="menu-btn" aria-label="Open navigation" onClick={openMobile}><Menu size={20}/></button><div className="crumb"><span>Workspace</span><b>/</b><strong>{title}</strong></div></div><div className="top-actions"><label className="search"><Search size={16}/><input placeholder="Search analytics..." aria-label="Search"/><kbd>⌘ K</kbd></label><div className="top-profile"><div className="avatar">PF</div><span><b>PureFlow</b><small>Workspace</small></span></div></div></header>
}

function PageFrame({ children }) { return <motion.div className="page-content" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>{children}</motion.div> }
function SectionTitle({ eyebrow, title, action }) { return <div className="section-title"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>{action}</div> }

function EmptyChart({ title, data = [], xKey = 'reporting_year', dataKey, kind = 'line', unit, description = 'No compatible uploaded data is available.', sourceLabel = 'Uploaded source data' }) {
  const hasData = Array.isArray(data) && data.length > 0 && dataKey
  const color = kind === 'bar' ? '#262626' : '#F58220'
  return <section className="panel chart-panel"><SectionTitle title={title}/>{hasData ? <div className="chart-real"><ResponsiveContainer width="100%" height="100%">{kind === 'bar' ? <BarChart data={data}><CartesianGrid stroke="#EBE7E1"/><XAxis dataKey={xKey}/><YAxis/><Tooltip/><Bar dataKey={dataKey} name={unit || dataKey} fill={color}/></BarChart> : kind === 'area' ? <AreaChart data={data}><CartesianGrid stroke="#EBE7E1"/><XAxis dataKey={xKey}/><YAxis/><Tooltip/><Area dataKey={dataKey} name={unit || dataKey} type="monotone" stroke={color} fill={color} fillOpacity={.12}/></AreaChart> : <LineChart data={data}><CartesianGrid stroke="#EBE7E1"/><XAxis dataKey={xKey}/><YAxis/><Tooltip/><Line dataKey={dataKey} name={unit || dataKey} type="monotone" stroke={color} strokeWidth={2} dot={false}/></LineChart>}</ResponsiveContainer></div> : <div className="chart-real-empty"><span className="chart-icon"><Activity size={20}/></span><strong>No data available</strong><p>{description}</p></div>}<div className="chart-foot"><span><i/>{hasData ? sourceLabel : 'Awaiting compatible uploaded records'}</span><span>{hasData ? `${data.length} groups` : '-'}</span></div></section>
}

function MetricCard({ icon: Icon, label, description, value }) { return <motion.article className="metric-card" whileHover={{ y: -2 }} transition={{ duration: .18 }}><div className="metric-top"><div className="metric-icon"><Icon size={16}/></div><span className="metric-dash">{value == null ? '—' : ''}</span></div><motion.div key={value ?? 'empty'} className="metric-value" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .2 }}>{value == null ? '—' : value}</motion.div><div className="metric-label">{label}</div><div className="metric-description">{description}</div></motion.article> }

function WaterConsumptionTrend({ data, loading, selectedDatasetName }) {
  const [seriesKey, setSeriesKey] = useState('')
  const series = data?.series || []
  const activeSeriesKey = series.some((item) => `${item.unit}:${item.period_granularity}` === seriesKey) ? seriesKey : series[0] ? `${series[0].unit}:${series[0].period_granularity}` : ''
  const activeSeries = series.find((item) => `${item.unit}:${item.period_granularity}` === activeSeriesKey)
  const activeUnit = activeSeries?.unit || ''
  const unitLabels = { litres: 'Litres', gallons: 'Gallons', million_litres: 'Million litres', million_gallons: 'Million gallons', cubic_metres: 'Cubic metres' }
  const unitLabel = unitLabels[activeUnit] || activeUnit
  const activePeriod = activeSeries?.period_granularity
  const available = (data?.annual || []).filter((row) => row.unit === activeUnit && row.period_granularity === activePeriod)
  const sourceNames = [...new Set(available.flatMap((row) => row.dataset_names || []))]
  const emptyMessage = data?.annual_message || data?.message || 'No compatible water consumption data found in the selected dataset.'
  return <section className="panel trend-panel">
    <div className="trend-heading"><div><span className="eyebrow">UPLOADED DATA</span><h2>Water Consumption Trends</h2><p>{selectedDatasetName || 'Compatible uploaded datasets'}{sourceNames.length > 1 ? ` · ${sourceNames.length} contributing datasets` : ''}</p></div>{series.length > 1 && <label className="trend-unit"><span>Unit · time grain</span><select value={activeSeriesKey} onChange={(event) => setSeriesKey(event.target.value)}>{series.map((item) => <option key={`${item.unit}:${item.period_granularity}`} value={`${item.unit}:${item.period_granularity}`}>{unitLabels[item.unit] || item.unit} · {item.period_granularity}</option>)}</select></label>}{series.length === 1 && <span className="trend-unit-label">{unitLabel} · {activePeriod}</span>}</div>
    {available.length ? <div className="trend-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={available} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}><defs><linearGradient id="waterTrendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#F58220" stopOpacity={.24}/><stop offset="100%" stopColor="#F58220" stopOpacity={.015}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#EBE7E1" strokeDasharray="3 4"/><XAxis dataKey="year" tickLine={false} axisLine={false}/><YAxis tickLine={false} axisLine={false} width={72}/><Tooltip contentStyle={{ border: '1px solid #EBE7E1', borderRadius: 10, background: '#fff', boxShadow: '0 6px 22px #3b2b1514' }} formatter={(value) => [`${Number(value).toLocaleString()} ${unitLabel.toLowerCase()}`, unitLabel]}/><Area type="monotone" dataKey="value" name={unitLabel} stroke="#F58220" strokeWidth={2.5} fill="url(#waterTrendFill)" activeDot={{ r: 5, fill: '#F58220', stroke: '#fff', strokeWidth: 2 }}/></AreaChart></ResponsiveContainer></div> : <div className="trend-empty">{loading ? 'Loading uploaded water data…' : emptyMessage}</div>}
    <div className="trend-foot"><span><i/>{sourceNames.length ? `Source: ${sourceNames.join(', ')}` : 'No compatible uploaded records'}</span><span>{available.reduce((sum, row) => sum + row.observations, 0).toLocaleString()} observations</span></div>
  </section>
}

function ObservationMixCard({ data }) {
  const palette = ['#F58220', '#F4C928', '#E96A13', '#FBE7BE', '#B7B7B7']
  const locations = [...(data || [])].sort((left, right) => (right.observations || 0) - (left.observations || 0))
  const top = locations.slice(0, 4).map((row) => ({ key: `${row.location_type}:${row.name}`, name: row.name, observations: Number(row.observations || 0) }))
  const remaining = locations.slice(4).reduce((sum, row) => sum + Number(row.observations || 0), 0)
  if (remaining) top.push({ key: 'other', name: 'Other locations', location_type: 'grouped locations', observations: remaining })
  const total = top.reduce((sum, item) => sum + item.observations, 0)
  return <section className="panel wue-distribution-card"><SectionTitle eyebrow="SOURCE RECORDS" title="Observation Mix"/><p className="wue-card-subtitle">Uploaded rows grouped by detected location or category.</p>{total ? <div className="wue-donut-layout"><div className="wue-donut"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={top} dataKey="observations" nameKey="name" innerRadius="66%" outerRadius="92%" paddingAngle={2} stroke="#fff" strokeWidth={2}>{top.map((entry, index) => <Cell key={entry.key} fill={palette[index % palette.length]}/>)}</Pie><Tooltip formatter={(value, _name, item) => [`${Number(value).toLocaleString()} uploaded rows`, `${item.payload.name} · ${item.payload.location_type}`]} contentStyle={{ border: '1px solid #EBE7E1', borderRadius: 9, background: '#fff' }}/></PieChart></ResponsiveContainer><div className="wue-donut-center"><b>{total.toLocaleString()}</b><span>uploaded rows</span></div></div><div className="wue-legend">{top.map((item, index) => <div key={item.key}><i style={{ backgroundColor: palette[index % palette.length] }}/><span title={item.name}>{item.name}</span><b>{item.observations.toLocaleString()}</b></div>)}</div></div> : <div className="wue-empty">No supported location or category field was found in the selected upload.</div>}</section>
}

function UploadedLocationChart({ data = [], loading }) {
  const series = [...new Map(data.map((row) => [`${row.unit}:${row.period_granularity}`, { unit: row.unit, period_granularity: row.period_granularity }])).values()]
  const [seriesKey, setSeriesKey] = useState('')
  const activeSeriesKey = series.some((item) => `${item.unit}:${item.period_granularity}` === seriesKey) ? seriesKey : series[0] ? `${series[0].unit}:${series[0].period_granularity}` : ''
  const activeSeries = series.find((item) => `${item.unit}:${item.period_granularity}` === activeSeriesKey)
  const activeUnit = activeSeries?.unit || ''
  const activePeriod = activeSeries?.period_granularity
  const rows = data.filter((row) => row.unit === activeUnit && row.period_granularity === activePeriod)
  const types = [...new Set(rows.map((row) => row.location_type))]
  const title = types.length === 1 ? (types[0] === 'country' ? 'Water Consumption by Country' : types[0] === 'category' ? 'Water Consumption by Category' : 'Water Consumption by Location') : 'Water Consumption by Country or Location'
  const labels = { litres: 'Litres', gallons: 'Gallons', million_litres: 'Million litres', million_gallons: 'Million gallons', cubic_metres: 'Cubic metres' }
  const names = [...new Set(rows.flatMap((row) => row.dataset_names || []))]
  return <section className="panel chart-panel"><div className="section-title"><h2>{title}</h2>{series.length > 1 && <label className="trend-unit"><span>Unit · time grain</span><select value={activeSeriesKey} onChange={(event) => setSeriesKey(event.target.value)}>{series.map((item) => <option key={`${item.unit}:${item.period_granularity}`} value={`${item.unit}:${item.period_granularity}`}>{labels[item.unit] || item.unit} · {item.period_granularity}</option>)}</select></label>}</div>{rows.length ? <div className="chart-real"><ResponsiveContainer width="100%" height="100%"><BarChart data={rows}><CartesianGrid stroke="#EBE7E1"/><XAxis dataKey="name"/><YAxis/><Tooltip formatter={(value) => [`${Number(value).toLocaleString()} ${labels[activeUnit] || activeUnit}`, 'Consumption']}/><Bar dataKey="value" name={labels[activeUnit] || activeUnit} fill="#F58220"/></BarChart></ResponsiveContainer></div> : <div className="chart-real-empty"><span className="chart-icon"><Activity size={20}/></span><strong>{loading ? 'Loading uploaded records…' : 'No compatible water consumption data found in the selected dataset.'}</strong></div>}<div className="chart-foot"><span><i/>{names.length ? `Source: ${names.join(', ')}` : 'No compatible uploaded records'}</span><span>{rows.length} groups</span></div></section>
}

export function Overview() {
  const [selectedDatasetId, setSelectedDatasetId] = useState('all')
  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const loadDashboard = useCallback(async () => {
    setLoading(true)
    setError('')
    try { setDashboard(await getDashboard(selectedDatasetId)) }
    catch (err) {
      setDashboard(null)
      if (err.response?.status === 404 && selectedDatasetId !== 'all') { setSelectedDatasetId('all'); return }
      setError(err.response?.data?.message || 'Unable to connect to the PureFlow API.')
    }
    finally { setLoading(false) }
  }, [selectedDatasetId])
  useEffect(() => {
    loadDashboard()
    window.addEventListener('pureflow:data-changed', loadDashboard)
    return () => window.removeEventListener('pureflow:data-changed', loadDashboard)
  }, [loadDashboard])
  const availableDatasets = dashboard?.dashboard_analytics?.datasets || []
  const selectedDataset = availableDatasets.find((item) => item.dataset_id === selectedDatasetId)
  const currentDashboard = !loading && dashboard?.dashboard_analytics?.selection === selectedDatasetId ? dashboard : null
  const connectionLabel = loading ? 'Connecting to APIâ€¦' : error ? 'Backend unavailable' : 'Backend connected'
  return <PageFrame><section className="overview-page-heading"><div className="overview-heading-art"><GeometricBackground/></div><div className="overview-heading-copy"><div className="live-tag"><span/> PUREFLOW / WATER SUSTAINABILITY ANALYTICS</div><h1>Analytics Overview</h1><p className="lead">Your water sustainability performance at a glance.</p></div><div className="overview-heading-status"><label className="dashboard-dataset-select"><span>Dataset</span><select value={selectedDatasetId} onChange={(event) => setSelectedDatasetId(event.target.value)}><option value="all">All uploads · compatible charts only</option>{availableDatasets.map((item) => <option key={item.dataset_id} value={item.dataset_id}>{item.dataset_name}{item.compatible ? '' : ' · no compatible water field'}</option>)}</select></label><span className={`connection-pill ${error ? 'connection-error' : loading ? 'connection-loading' : ''}`}><span className="status-dot"/>{connectionLabel}</span><NavLink className="primary-btn" to="/datasets#upload"><Droplets size={15}/> Add dataset</NavLink></div></section>
    {error && <div className="api-error" role="alert"><div><strong>Dashboard data could not be loaded</strong><span>{error}</span></div><button onClick={loadDashboard} disabled={loading}>{loading ? 'Retrying…' : 'Retry connection'}</button></div>}
    <section className="overview-dashboard-grid" aria-busy={loading}><WaterConsumptionTrend data={currentDashboard?.dashboard_analytics} loading={loading} selectedDatasetName={selectedDataset?.dataset_name}/><aside className={`overview-kpis ${loading ? 'metrics-loading' : ''}`}>{[[Database,'Uploaded Datasets','Current source uploads',currentDashboard?.upload_summary?.dataset_count],[Database,'Total Records','Rows in selected uploads',currentDashboard?.upload_summary?.total_records],[CheckCircle2,'Successfully Cleaned','Datasets with cleaned CSVs',currentDashboard?.upload_summary?.cleaned_datasets],[ShieldCheck,'Requiring Attention','Datasets with missing or duplicate rows',currentDashboard?.upload_summary?.attention_datasets],[Activity,'Missing Values','Calculated from selected raw uploads',currentDashboard?.upload_summary?.missing_values],[Activity,'Duplicate Records','Exact duplicates in selected raw uploads',currentDashboard?.upload_summary?.duplicate_records]].map(([icon,label,description,value],index)=><motion.div key={label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .06, duration: .22 }}><MetricCard icon={icon} label={label} description={loading ? 'Loading data…' : description} value={value == null ? null : Number(value).toLocaleString()}/></motion.div>)}</aside></section>
    <div className="overview-lower-grid"><ObservationMixCard data={currentDashboard?.observation_mix}/><UploadedLocationChart data={currentDashboard?.dashboard_analytics?.by_location} loading={loading}/><section className="panel overview-context-card"><SectionTitle eyebrow="ENVIRONMENTAL CONTEXT" title="Climate & Water Stress"/><div className="context-readout"><div><span className="context-icon"><Thermometer size={17}/></span><div><strong>Climate overview</strong><p>{currentDashboard?.climate_summary?.message || 'No linked uploaded climate measurements are available.'}</p></div></div><div><span className="context-icon"><Globe2 size={17}/></span><div><strong>Water stress</strong><p>{currentDashboard?.regional_water_stress?.length ? `${currentDashboard.regional_water_stress.length} linked location assessments` : 'No linked uploaded water-stress assessments are available.'}</p></div></div></div></section></div>
    <section className="overview-insights-grid" aria-busy={loading}>
      <article className="panel overview-processing"><SectionTitle eyebrow="PIPELINE ACTIVITY" title="Dataset processing" action={<NavLink className="activity-link" to="/integration">Transform <ChevronRight size={14}/></NavLink>}/><p className="overview-card-description">Current selection counts and saved processing history.</p><div className="processing-metrics">{[["Uploaded source rows", currentDashboard?.upload_summary?.total_records], ["Compatible datasets", currentDashboard?.upload_summary?.compatible_dataset_count], ["Cleaned datasets", currentDashboard?.upload_summary?.cleaned_datasets], ["Datasets requiring attention", currentDashboard?.upload_summary?.attention_datasets], ["Standardisation runs", currentDashboard?.transformation_summary?.standardisation_runs], ["Integration runs", currentDashboard?.transformation_summary?.integration_runs]].map(([label, value]) => <div key={label}><span>{label}</span><b>{value == null ? '—' : Number(value).toLocaleString()}</b></div>)}</div></article>
      <article className="panel overview-quality"><SectionTitle eyebrow="DATA RELIABILITY" title="Source quality" action={<NavLink className="activity-link" to="/quality">Review <ChevronRight size={14}/></NavLink>}/><p className="overview-card-description">Values inspected directly from the selected original uploads.</p><div className="quality-summary-grid"><div><b>{currentDashboard ? Number(currentDashboard.upload_summary.missing_values).toLocaleString() : '—'}</b><span>Missing values</span></div><div><b>{currentDashboard ? Number(currentDashboard.upload_summary.duplicate_records).toLocaleString() : '—'}</b><span>Duplicate rows</span></div><div><b>{currentDashboard ? Number(currentDashboard.upload_summary.attention_datasets).toLocaleString() : '—'}</b><span>Datasets needing attention</span></div></div>{currentDashboard && !currentDashboard.upload_summary.missing_values && !currentDashboard.upload_summary.duplicate_records && <div className="quality-summary-note"><CheckCircle2 size={14}/> No missing or exact duplicate source rows detected.</div>}</article>
      <article className="panel overview-sdg"><SectionTitle eyebrow="SUSTAINABILITY CONTEXT" title="Uploaded data evidence"/><p className="overview-card-description">Counts below come from the selected raw upload files.</p><div className="sdg-evidence-list">{(currentDashboard?.sdg_context || []).map((item) => <div key={item.goal}><span className="sdg-goal">{item.goal}</span><div><b>{item.label}</b><small>{item.measure}</small></div><strong>{Number(item.value || 0).toLocaleString()}<small>{item.unit}</small></strong></div>)}</div>{currentDashboard && !currentDashboard.sdg_context.length && <div className="quality-summary-note">No supported water or efficiency measurements found in this selection.</div>}</article>
    </section>
    <section className="panel overview-activity"><div className="activity-heading"><div><span className="eyebrow">DATASET ACTIVITY</span><h2>Recent datasets</h2><p>Uploaded source files and their latest cleaning and quality status.</p></div><NavLink className="activity-link" to="/datasets">Manage datasets <ChevronRight size={15}/></NavLink></div><div className="table-wrap"><table><thead><tr><th>DATASET</th><th>UPLOADED</th><th>RECORDS</th><th>COLUMNS</th><th>CLEANING</th><th>QUALITY</th></tr></thead><tbody>{dashboard?.uploaded_datasets?.length ? dashboard.uploaded_datasets.map((item) => <tr key={item.dataset_id}><td>{item.original_filename}</td><td>{item.upload_timestamp ? new Date(item.upload_timestamp).toLocaleDateString() : '—'}</td><td>{Number(item.row_count || 0).toLocaleString()}</td><td>{item.column_count}</td><td><span className="dataset-status-chip">{item.cleaning_status}</span></td><td><span className="dataset-status-chip">{item.quality_status}</span></td></tr>) : <tr><td colSpan="6"><div className="table-empty"><div className="empty-file"><Database size={19}/></div><strong>No datasets uploaded yet</strong><span>Upload your first dataset to see its quality, cleaning status and analytics here.</span><NavLink className="small-btn" to="/datasets#upload">Upload Dataset</NavLink></div></td></tr>}</tbody></table></div>{currentDashboard?.recent_activity?.length > 0 && <div className="recent-event-list">{currentDashboard.recent_activity.slice(0, 5).map((event, index) => <div key={`${event.dataset_id}-${event.type}-${event.timestamp}-${index}`}><span>{{clean:'Dataset cleaned',quality_check:'Quality assessment completed',standardise:'Dataset transformed',integrate:'Datasets integrated',uploaded:'Dataset uploaded'}[event.type] || 'Dataset activity'}</span><b>{event.dataset_name}</b><small>{event.timestamp ? new Date(event.timestamp).toLocaleString() : ''}</small></div>)}</div>}</section>
    <footer className="footer"><span>PureFlow <i>·</i> Smarter Water Insights. Sustainable Tomorrow.</span><span>Evidence-led environmental analytics <Droplets size={13}/></span></footer>
  </PageFrame>
}

export function SecondaryPage({ path }) {
  const [title, description] = pages[path]
  const details = {
    '/datasets': ['Connect your first dataset', 'Bring in a CSV file to begin exploring your facility and water consumption data.', Database, 'Upload dataset'],
    '/quality': ['Quality checks are ready when you are', 'Validation results will appear here after a dataset has been ingested.', FileCheck2, 'Explore datasets'],
    '/water': ['Water analysis starts with your data', 'Consumption trends and WUE metrics will be calculated from connected records.', Waves, 'View overview'],
    '/climate': ['Climate context, connected to water', 'Climate comparisons will be available when location and time-series data are connected.', CloudSun, 'View overview'],
    '/stress': ['Location intelligence awaits', 'Water stress assessments will appear when facility locations are available.', Globe2, 'View overview'],
    '/sql': ['No analytical database connected', 'Connect a processed dataset before running queries against the SQLite store.', Activity, 'View datasets'],
    '/reports': ['Your reports will live here', 'Generate sustainability reports from validated water and climate analysis.', FileText, 'View overview'],
  }[path]
  const Icon = details[2]
  return <PageFrame><div className="welcome-row secondary-welcome"><div><div className="live-tag"><span/> PUREFLOW / WORKSPACE</div><h1>{title}</h1><p className="lead">{description}</p></div><button className="outline-btn"><span className="status-dot"/> Awaiting data</button></div>
    <div className={`secondary-layout ${path === '/water' || path === '/climate' ? 'analytics-layout' : ''}`}><section className="panel secondary-hero"><div className="secondary-illustration"><div className="orb orb-one"/><div className="orb orb-two"/><div className="secondary-icon"><Icon size={25}/></div><div className="orbit orbit-one"/><div className="orbit orbit-two"/></div><span className="eyebrow">READY WHEN YOU ARE</span><h2>{details[0]}</h2><p>{details[1]}</p><NavLink className="primary-btn" to={path === '/datasets' ? '/datasets' : '/'}>{details[3]} <ChevronRight size={16}/></NavLink></section>
      <div className="secondary-side"><section className="panel note-panel"><div className="note-icon"><ShieldCheck size={17}/></div><div><strong>Designed for trusted analysis</strong><p>Metrics remain empty until sourced from your connected dataset.</p></div></section><section className="panel note-panel"><div className="note-icon"><Database size={17}/></div><div><strong>Data pipeline</strong><p>Ingestion, validation and storage are currently pending.</p><span className="pending-pill">Not connected</span></div></section></div></div>
    {['/water','/climate'].includes(path) && <div className="chart-grid-two secondary-charts"><EmptyChart title={path === '/water' ? 'Water consumption trends' : 'Climate and water efficiency'}/><EmptyChart title={path === '/water' ? 'Water usage effectiveness' : 'Seasonal climate patterns'} kind="area"/></div>}
    {path === '/stress' && <section className="panel map-panel"><SectionTitle title="Regional water stress" action={<span className="pending-pill">No locations</span>}/><div className="map-empty"><div className="map-lines">{Array.from({length:7},(_,i)=><i key={i}/>)}</div><div className="map-placeholder"><Globe2 size={25}/><strong>Map data will appear here</strong><span>Facility locations are required to assess regional water stress.</span></div></div></section>}
    {path === '/sql' && <section className="panel sql-panel"><SectionTitle title="Query workspace" action={<span className="pending-pill">SQLite Â· pending</span>}/><div className="code-placeholder"><span>1</span><code>-- Connect a dataset to start querying</code></div><button className="small-btn" disabled>Run query <ChevronRight size={14}/></button></section>}
  </PageFrame>
}

function AppShell() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const { pathname } = useLocation()
  const title = pages[pathname]?.[0] || 'Overview'
  return <div className="app-shell"><Sidebar collapsed={collapsed} setCollapsed={setCollapsed} mobileOpen={mobileOpen} closeMobile={() => setMobileOpen(false)}/><main className={`main-area ${collapsed ? 'sidebar-collapsed' : ''}`}><Header title={title} openMobile={() => setMobileOpen(true)}/><Routes><Route path="/" element={<Overview/>}/><Route path="/datasets" element={<DatasetExplorer/>}/><Route path="/quality" element={<DataQuality/>}/><Route path="/integration" element={<DatasetIntegration/>}/><Route path="/water" element={<WaterAnalytics/>}/><Route path="/climate" element={<ClimateAnalysis/>}/><Route path="/stress" element={<WaterStress/>}/><Route path="/sql" element={<SQLAnalytics/>}/><Route path="/reports" element={<Reports/>}/></Routes></main></div>
}
export default function App() {
  const [showIntro, setShowIntro] = useState(true)
  const completeIntro = useCallback(() => setShowIntro(false), [])

  return <MotionConfig reducedMotion="user"><AnimatePresence mode="wait">
    {showIntro
      ? <IntroScreen key="intro" onComplete={completeIntro} />
      : <BrowserRouter key="application"><AppShell /></BrowserRouter>}
  </AnimatePresence></MotionConfig>
}
