import { useCallback, useEffect, useState } from 'react'
import { Activity, AlertCircle, CheckCircle2, Database, Play, RefreshCw, Table2 } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getDatabaseLoadHistory, getDatabaseSchema, getDatabaseStatus, getDatabaseTables, getDatabaseValidation, getSqlAnalytics, getTransformedDatasets, loadDatabaseDataset, runCustomQuery } from '../services/api'
import './SQLAnalytics.css'

const fmt = (value) => value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 })
const initialQuery = 'SELECT l.country, COUNT(*) AS observations, AVG(w.wue_l_per_kwh) AS average_wue_l_per_kwh\nFROM water_metrics w\nJOIN locations l ON l.location_id = w.location_id\nWHERE w.wue_l_per_kwh IS NOT NULL\nGROUP BY l.country\nORDER BY average_wue_l_per_kwh DESC'

export default function SQLAnalytics() {
  const [status, setStatus] = useState(null)
  const [tables, setTables] = useState([])
  const [schema, setSchema] = useState({})
  const [datasets, setDatasets] = useState([])
  const [history, setHistory] = useState([])
  const [validation, setValidation] = useState(null)
  const [analytics, setAnalytics] = useState({})
  const [loading, setLoading] = useState(true)
  const [busyDataset, setBusyDataset] = useState('')
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [selectedTable, setSelectedTable] = useState('water_metrics')
  const [query, setQuery] = useState(initialQuery)
  const [queryResult, setQueryResult] = useState(null)
  const [queryBusy, setQueryBusy] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    const results = await Promise.allSettled([
      getDatabaseStatus(), getDatabaseTables(), getDatabaseSchema(), getTransformedDatasets(),
      getDatabaseLoadHistory(), getDatabaseValidation(),
      getSqlAnalytics('water-consumption'), getSqlAnalytics('wue'), getSqlAnalytics('monthly-trends'),
      getSqlAnalytics('country-comparison'), getSqlAnalytics('distribution'), getSqlAnalytics('annual-trends'), getSqlAnalytics('climate'), getSqlAnalytics('water-stress'),
      getSqlAnalytics('summary'),
    ])
    const [db, tbl, sch, ds, hist, valid, water, wue, monthly, country, distribution, annual, climate, stress, summary] = results
    if (db.status === 'fulfilled') setStatus(db.value); else setError(db.reason.response?.data?.message || 'Database API is unavailable.')
    if (tbl.status === 'fulfilled') setTables(tbl.value.tables || [])
    if (sch.status === 'fulfilled') setSchema(sch.value.schema || {})
    if (ds.status === 'fulfilled') setDatasets(ds.value.datasets || [])
    if (hist.status === 'fulfilled') setHistory(hist.value.history || [])
    if (valid.status === 'fulfilled') setValidation(valid.value.report)
    setAnalytics({ water: water.status === 'fulfilled' ? water.value : null,
      wue: wue.status === 'fulfilled' ? wue.value : null,
      monthly: monthly.status === 'fulfilled' ? monthly.value : null,
      country: country.status === 'fulfilled' ? country.value : null,
      distribution: distribution.status === 'fulfilled' ? distribution.value : null,
      annual: annual.status === 'fulfilled' ? annual.value : null,
      climate: climate.status === 'fulfilled' ? climate.value : null,
      stress: stress.status === 'fulfilled' ? stress.value : null,
      summary: summary.status === 'fulfilled' ? summary.value : null })
    setLoading(false)
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const load = async (dataset, reload = false) => {
    if (reload && !window.confirm(`Reload ${dataset.source_filename}? Existing database rows for this dataset will be replaced transactionally.`)) return
    setBusyDataset(dataset.dataset_id); setError(''); setNotice('')
    try { const response = await loadDatabaseDataset(dataset.dataset_id, reload ? { reload: true, confirm: true } : {}); setNotice(response.report?.message || response.message); await refresh() }
    catch (err) { setError(err.response?.data?.message || 'Dataset load failed. The transaction was rolled back.') }
    finally { setBusyDataset('') }
  }

  const execute = async () => {
    setQueryBusy(true); setQueryResult(null); setError('')
    try { setQueryResult(await runCustomQuery(query, 200)) }
    catch (err) { setError(err.response?.data?.message || 'Query failed.') }
    finally { setQueryBusy(false) }
  }

  const selectedSchema = schema[selectedTable]
  const water = analytics.water?.data || {}
  const message = (response) => response?.message
  const hasTables = tables.some((table) => table.name === 'water_metrics' && table.record_count > 0)

  return <div className="page-content sql-page">
    <div className="sql-heading"><div><div className="live-tag"><span/> SQLITE / LIVE DATA</div><h1>Database Management &amp; SQL Analytics</h1><p className="lead">Inspect transformed records, validate the SQLite store, and run read-only analysis against loaded data.</p></div><button className="sql-refresh" onClick={refresh} disabled={loading}><RefreshCw size={15}/> Refresh</button></div>
    {error && <div className="sql-alert error" role="alert"><AlertCircle size={17}/>{error}</div>}
    {notice && <div className="sql-alert success" role="status"><CheckCircle2 size={17}/>{notice}</div>}

    <section className="sql-panel sql-status"><div className="sql-panel-title"><div><span className="eyebrow">DATABASE MANAGEMENT</span><h2>SQLite connection</h2></div><span className={`sql-badge ${status?.connected ? 'good' : ''}`}><i/>{status?.connected ? 'Connected' : loading ? 'Checking' : 'Unavailable'}</span></div>
      <div className="sql-status-grid"><div><small>Database file</small><b title={status?.database}>{status?.database || '—'}</b></div><div><small>File size</small><b>{status?.size_bytes == null ? '—' : `${fmt(status.size_bytes)} bytes`}</b></div><div><small>Tables</small><b>{fmt(tables.length)}</b></div><div><small>Stored records</small><b>{fmt(analytics.summary?.total_stored_water_records || 0)}</b></div><div><small>Validation</small><b className={validation?.valid ? 'text-good' : 'text-warn'}>{validation ? (validation.valid ? 'Passed' : 'Issues found') : 'Checking'}</b></div></div>
    </section>

    <div className="sql-layout"><section className="sql-panel"><div className="sql-panel-title"><div><span className="eyebrow">TRANSFORMED SOURCES</span><h2>Dataset loading</h2></div><Database size={18}/></div><p className="sql-muted">Only standardised files in transformed storage are eligible. Existing datasets are skipped unless you explicitly reload.</p>
      {!datasets.length ? <div className="sql-empty">No transformed datasets are available. Standardise a curated dataset first.</div> : <div className="sql-dataset-list">{datasets.map((dataset) => {
        const loaded = history.some((entry) => entry.dataset_id === dataset.dataset_id && ['loaded', 'loaded_with_rejections'].includes(entry.load_status))
        return <article className="sql-dataset" key={dataset.dataset_id}><div className="sql-dataset-icon"><Database size={17}/></div><div className="sql-dataset-info"><b>{dataset.source_filename}</b><span>{dataset.transformed_filename}</span><small>{fmt(dataset.records_read)} source records · {dataset.columns?.length || 0} columns</small></div><div className="sql-dataset-actions"><button className="sql-button" disabled={Boolean(busyDataset) || loaded} onClick={() => load(dataset)}>{busyDataset === dataset.dataset_id ? 'Loading…' : loaded ? 'Already loaded' : 'Load dataset'}</button>{loaded && <button className="sql-button subtle" disabled={Boolean(busyDataset)} onClick={() => load(dataset, true)}>Reload</button>}</div></article>
      })}</div>}
    </section>
    <section className="sql-panel"><div className="sql-panel-title"><div><span className="eyebrow">SCHEMA</span><h2>Tables and columns</h2></div><Table2 size={18}/></div><label className="sql-select-label">Table<select value={selectedTable} onChange={(event) => setSelectedTable(event.target.value)}>{tables.map((table) => <option key={table.name} value={table.name}>{table.name} ({fmt(table.record_count)})</option>)}</select></label>
      <div className="sql-schema-table"><table><thead><tr><th>Column</th><th>Type</th><th>Key</th><th>Required</th></tr></thead><tbody>{(selectedSchema?.columns || []).map((column) => <tr key={column.name}><td>{column.name}</td><td>{column.type || '—'}</td><td>{column.pk ? 'Primary' : ''}</td><td>{column.notnull ? 'Yes' : 'No'}</td></tr>)}</tbody></table></div>
    </section></div>

    <section className="sql-panel sql-history"><div className="sql-panel-title"><div><span className="eyebrow">LOAD AUDIT</span><h2>Loading history &amp; validation</h2></div><span className={`sql-badge ${validation?.valid ? 'good' : ''}`}>{validation?.valid ? 'Integrity checks passed' : 'Validation pending / issues'}</span></div>
      <div className="sql-validation">{validation ? <><span>PRAGMA integrity_check: <b>{validation.integrity_check?.join(', ')}</b></span><span>Foreign key violations: <b>{validation.foreign_key_violations?.length ?? '—'}</b></span><span>Count mismatches: <b>{validation.count_mismatches?.length ?? '—'}</b></span></> : <span>Validation report unavailable.</span>}</div>
      <div className="sql-schema-table"><table><thead><tr><th>Source</th><th>Loaded at</th><th>Read</th><th>Inserted</th><th>Rejected</th><th>Duplicates</th><th>Status</th></tr></thead><tbody>{history.length ? history.map((item) => <tr key={item.load_id}><td>{item.source_filename}</td><td>{new Date(item.loaded_at).toLocaleString()}</td><td>{fmt(item.records_read)}</td><td>{fmt(item.records_inserted)}</td><td>{fmt(item.records_rejected)}</td><td>{fmt(item.duplicate_records)}</td><td>{item.load_status}</td></tr>) : <tr><td colSpan="7" className="sql-empty-cell">No load attempts yet.</td></tr>}</tbody></table></div>
    </section>

    <div className="sql-analytics-heading"><div><span className="eyebrow">SQL ANALYTICS</span><h2>Results from stored observations</h2></div></div>
    <div className="sql-kpis"><article><small>Consumption (million gallons)</small><b>{fmt(water.million_gallons)}</b><span>{fmt(water.gallon_observations)} reported observations</span></article><article><small>Consumption (million litres)</small><b>{fmt(water.million_litres)}</b><span>{fmt(water.litre_observations)} reported observations</span></article><article><small>Average WUE locations</small><b>{fmt(analytics.wue?.data?.length || 0)}</b><span>WUE measured in L/kWh</span></article><article><small>Stored source records</small><b>{fmt(analytics.summary?.total_stored_water_records || 0)}</b><span>Validated transformed rows</span></article></div>
    {!hasTables && <div className="sql-empty prominent">The database has no loaded observations yet. Load a transformed dataset to populate the live charts and query results.</div>}
    <div className="sql-chart-grid"><section className="sql-panel"><div className="sql-panel-title"><h2>Monthly consumption</h2></div>{analytics.monthly?.data?.length ? <div className="sql-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={analytics.monthly.data}><CartesianGrid stroke="#ffffff" strokeOpacity={0.08}/><XAxis dataKey="measurement_month" stroke="#9aabb4"/><YAxis stroke="#9aabb4"/><Tooltip/><Line dataKey="million_litres" name="Million litres" stroke="#52d6bf" connectNulls={false}/></LineChart></ResponsiveContainer></div> : <div className="sql-empty">{message(analytics.monthly) || 'No monthly rows available.'}</div>}</section>
      <section className="sql-panel"><div className="sql-panel-title"><h2>WUE by location</h2></div>{analytics.wue?.data?.length ? <div className="sql-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={analytics.wue.data}><CartesianGrid stroke="#ffffff" strokeOpacity={0.08}/><XAxis dataKey="place_name" stroke="#9aabb4" hide/><YAxis stroke="#9aabb4"/><Tooltip/><Bar dataKey="average_wue_l_per_kwh" name="Average WUE (L/kWh)" fill="#52d6bf"/></BarChart></ResponsiveContainer></div> : <div className="sql-empty">{message(analytics.wue) || 'No WUE rows available.'}</div>}</section>
      <section className="sql-panel"><div className="sql-panel-title"><h2>Consumption by country</h2></div>{analytics.country?.data?.length ? <div className="sql-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={analytics.country.data}><CartesianGrid stroke="#ffffff" strokeOpacity={0.08}/><XAxis dataKey="country" stroke="#9aabb4"/><YAxis stroke="#9aabb4"/><Tooltip/><Bar dataKey="million_litres" name="Million litres" fill="#68a5d8"/></BarChart></ResponsiveContainer></div> : <div className="sql-empty">{message(analytics.country) || 'No country comparisons available.'}</div>}</section>
      <section className="sql-panel"><div className="sql-panel-title"><h2>Country site labels</h2></div>{analytics.distribution?.data?.length ? <div className="sql-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={analytics.distribution.data}><CartesianGrid stroke="#ffffff" strokeOpacity={0.08}/><XAxis dataKey="country" stroke="#9aabb4"/><YAxis stroke="#9aabb4" allowDecimals={false}/><Tooltip/><Bar dataKey="site_labels" name="Source site labels" fill="#b28bd5"/></BarChart></ResponsiveContainer></div> : <div className="sql-empty">{message(analytics.distribution) || 'No site distribution available.'}</div>}</section>
      <section className="sql-panel"><div className="sql-panel-title"><h2>Annual consumption</h2></div>{analytics.annual?.data?.length ? <div className="sql-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={analytics.annual.data}><CartesianGrid stroke="#ffffff" strokeOpacity={0.08}/><XAxis dataKey="reporting_year" stroke="#9aabb4"/><YAxis stroke="#9aabb4"/><Tooltip/><Line dataKey="million_litres" name="Million litres" stroke="#e7b96c" connectNulls={false}/></LineChart></ResponsiveContainer></div> : <div className="sql-empty">{message(analytics.annual) || 'No annual rows available.'}</div>}</section>
    </div>
    <div className="sql-layout"><section className="sql-panel"><div className="sql-panel-title"><div><span className="eyebrow">SQL QUERY EXPLORER</span><h2>Read-only SELECT workspace</h2></div><Activity size={18}/></div><textarea className="sql-editor" aria-label="SQL SELECT query" spellCheck="false" value={query} onChange={(event) => setQuery(event.target.value)}/><div className="sql-query-footer"><span>Maximum 200 result rows · database writes are disabled</span><button className="sql-button" onClick={execute} disabled={queryBusy}><Play size={14}/>{queryBusy ? 'Running…' : 'Run query'}</button></div>{queryResult && <><div className="sql-query-status">Query completed · {queryResult.row_count} rows{queryResult.truncated ? ' · results capped at 200' : ''}</div><div className="sql-schema-table"><table><thead><tr>{queryResult.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{queryResult.rows.length ? queryResult.rows.map((row, index) => <tr key={index}>{queryResult.columns.map((column) => <td key={column}>{row[column] == null ? '—' : String(row[column])}</td>)}</tr>) : <tr><td colSpan={Math.max(1, queryResult.columns.length)} className="sql-empty-cell">Query returned no records.</td></tr>}</tbody></table></div></>}</section>
      <div className="sql-analysis-notes"><section className="sql-panel"><div className="sql-panel-title"><h2>Climate analysis</h2></div><div className="sql-empty">{message(analytics.climate) || 'No compatible climate rows.'}</div></section><section className="sql-panel"><div className="sql-panel-title"><h2>Water-stress analysis</h2></div><div className="sql-empty">{message(analytics.stress) || 'No compatible water-stress rows.'}</div></section></div>
    </div>
  </div>
}
