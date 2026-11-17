import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, Download, FileText, LoaderCircle, RefreshCw, Sparkles } from 'lucide-react'
import { generateReport, getReportHistory, getReportOverview, downloadReport } from '../services/api'
import './Reports.css'

const number = (value, decimals = 2) => value == null ? '—' : Number(value).toLocaleString(undefined, { maximumFractionDigits: decimals })
const formats = ['pdf', 'csv', 'json']

export default function Reports() {
  const [overview, setOverview] = useState(null)
  const [insights, setInsights] = useState([])
  const [recommendations, setRecommendations] = useState([])
  const [sustainability, setSustainability] = useState(null)
  const [history, setHistory] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [location, setLocation] = useState('')
  const [reportType, setReportType] = useState('comprehensive')
  const [generated, setGenerated] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [downloading, setDownloading] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const filters = useMemo(() => ({
    dataset_ids: selectedIds.join(','), start_date: startDate || undefined,
    end_date: endDate || undefined, location: location.trim() || undefined,
  }), [selectedIds, startDate, endDate, location])

  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    const [overviewResult, historyResult] = await Promise.allSettled([getReportOverview(filters), getReportHistory()])
    if (overviewResult.status === 'fulfilled') setOverview(overviewResult.value)
    else setError(overviewResult.reason.response?.data?.message || 'Could not load report overview.')
    if (overviewResult.status === 'fulfilled') {
      setInsights(overviewResult.value.findings || [])
      setRecommendations(overviewResult.value.recommendations || [])
      setSustainability(overviewResult.value.sustainability || null)
    }
    if (historyResult.status === 'fulfilled') setHistory(historyResult.value || [])
    setLoading(false)
  }, [filters])
  useEffect(() => { refresh() }, [refresh])

  const toggleDataset = (id) => setSelectedIds((current) => current.includes(id) ? current.filter((value) => value !== id) : [...current, id])

  const createReport = async (event) => {
    event.preventDefault(); setGenerating(true); setError(''); setNotice(''); setGenerated(null)
    try {
      const response = await generateReport({ dataset_ids: selectedIds, start_date: startDate || null,
        end_date: endDate || null, location: location.trim() || null, report_type: reportType })
      setGenerated(response.report); setNotice(response.message); await refresh()
    } catch (err) { setError(err.response?.data?.message || 'Report generation failed.') }
    finally { setGenerating(false) }
  }

  const saveDownload = async (reportId, format) => {
    setDownloading(`${reportId}:${format}`); setError('')
    try {
      const blob = await downloadReport(reportId, format)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = `pureflow_report_${reportId}.${format}`
      document.body.appendChild(link); link.click(); link.remove(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (err) { setError(err.response?.data?.message || `Could not download ${format.toUpperCase()} report.`) }
    finally { setDownloading('') }
  }

  const datasets = overview?.available_datasets || []
  const water = overview?.water_consumption || {}
  const wue = overview?.wue || {}

  return <div className="page-content reports-page">
    <div className="reports-heading"><div><div className="live-tag"><span/> EVIDENCE-BASED REPORTING</div><h1>Reporting Centre</h1><p className="lead">Build downloadable sustainability reports from stored PureFlow observations, with evidence, methods, and limitations included.</p></div><button className="reports-refresh" onClick={refresh} disabled={loading}><RefreshCw size={15}/> Refresh</button></div>
    {error && <div className="reports-alert error" role="alert"><AlertCircle size={17}/>{error}</div>}
    {notice && <div className="reports-alert success" role="status"><CheckCircle2 size={17}/>{notice}</div>}

    <section className="reports-panel report-overview"><div className="reports-section-title"><div><span className="eyebrow">REPORT OVERVIEW</span><h2>Current evidence</h2></div><span className="reports-badge">{overview?.selected_datasets?.length ?? '—'} selected dataset(s)</span></div>
      <div className="reports-kpis"><article><small>Selected observations</small><b>{number(water.records ?? 0, 0)}</b><span>After dataset, date, and location filters</span></article><article><small>Consumption · million gallons</small><b>{number(water.million_gallons)}</b><span>{number(water.gallon_observations, 0)} source observations</span></article><article><small>Consumption · million litres</small><b>{number(water.million_litres)}</b><span>{number(water.litre_observations, 0)} source observations</span></article><article><small>WUE · L/kWh</small><b>{number(wue.average_l_per_kwh, 3)}</b><span>{number(wue.observations, 0)} source observations</span></article></div>
    </section>

    <div className="reports-main-grid"><section className="reports-panel"><div className="reports-section-title"><div><span className="eyebrow">REPORT CONFIGURATION</span><h2>Choose report scope</h2></div><FileText size={18}/></div>
      <form onSubmit={createReport}>
        <div className="reports-filter-grid"><label>Report type<select value={reportType} onChange={(event) => setReportType(event.target.value)}><option value="comprehensive">Comprehensive sustainability report</option><option value="water">Water and WUE report</option><option value="sustainability">Sustainability data readiness</option></select></label><label>From date<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)}/></label><label>To date<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)}/></label><label>Location or country<input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="Filter by label or country code" maxLength="120"/></label></div>
        <div className="reports-dataset-select"><div className="reports-dataset-title"><b>Datasets</b><small>Leave all unchecked to include every loaded dataset.</small></div>{datasets.length ? <div className="reports-dataset-list">{datasets.map((dataset) => <label key={dataset.dataset_id}><input type="checkbox" checked={selectedIds.includes(dataset.dataset_id)} onChange={() => toggleDataset(dataset.dataset_id)}/><span><b>{dataset.source_filename}</b><small>{number(dataset.record_count, 0)} stored records · {dataset.source_type}</small></span></label>)}</div> : <div className="reports-empty-small">No datasets are currently loaded in SQLite.</div>}</div>
        <div className="reports-filter-note">Date filters use the source period's year where a year can be identified. Location filters search stored place labels and country codes; missing values are not inferred.</div>
        <button className="reports-primary" type="submit" disabled={generating || loading}>{generating ? <><LoaderCircle className="reports-spin" size={16}/>Generating…</> : <><Sparkles size={16}/>Generate report</>}</button>
      </form>
      {generated && <div className="generated-report"><div><b>Report ready</b><small>{generated.report_type} · {new Date(generated.generated_at).toLocaleString()}</small></div><div className="report-downloads">{formats.map((format) => <button key={format} onClick={() => saveDownload(generated.report_id, format)} disabled={Boolean(downloading)}><Download size={14}/>{downloading === `${generated.report_id}:${format}` ? 'Preparing…' : format.toUpperCase()}</button>)}</div></div>}
    </section>

    <section className="reports-panel readiness-panel"><div className="reports-section-title"><div><span className="eyebrow">SUSTAINABILITY</span><h2>Data readiness</h2></div><span className="reports-badge">No composite score</span></div><p>{sustainability?.message || 'Loading data-readiness assessment…'}</p><ul>{(sustainability?.variables_assessed || []).map((item) => <li key={item.metric}><span className={item.available ? 'readiness-yes' : 'readiness-no'}>{item.available ? 'Available' : 'Missing'}</span><b>{item.metric}</b><small>{item.coverage}</small></li>)}</ul><details><summary>Method and scoring decision</summary><p>Water consumption is retained in its reported units, and WUE remains L/kWh. The current data has no compatible linked climate or water-stress records and no external benchmark or certification target. Locations also contain varying scopes and periods. PureFlow therefore reports readiness gaps and does not calculate or weight an internal sustainability score.</p></details></section></div>

    <div className="reports-main-grid reports-lower-grid"><section className="reports-panel"><div className="reports-section-title"><div><span className="eyebrow">ANALYTICAL FINDINGS</span><h2>What the selected records show</h2></div></div>{insights.length ? <div className="reports-insights">{insights.map((item, index) => <article key={`${item.title}-${index}`}><b>{item.title}</b><p>{item.text}</p>{item.value != null && <small>Value: {number(item.value)} {item.unit || ''} · {number(item.observations, 0)} observations</small>}</article>)}</div> : <div className="reports-empty-small">{loading ? 'Loading findings…' : 'No analytical findings are available for this filter.'}</div>}</section>
      <section className="reports-panel"><div className="reports-section-title"><div><span className="eyebrow">RULE-BASED GUIDANCE</span><h2>Recommendations</h2></div></div>{recommendations.length ? <div className="recommendation-list">{recommendations.map((item) => <article key={item.id}><div className="recommendation-top"><span>{item.category}</span><small>{item.evidence_level}</small></div><h3>{item.title}</h3><p>{item.explanation}</p><div className="recommendation-evidence"><b>Evidence</b><pre>{JSON.stringify(item.supporting_evidence, null, 2)}</pre></div>{item.location && <p><b>Location:</b> {item.location}</p>}<p><b>Reason:</b> {item.reason}</p><small className="recommendation-limit">Limitations: {item.limitations}</small></article>)}</div> : <div className="reports-empty-small">No recommendations can be made from the available filtered measurements.</div>}</section></div>

    <section className="reports-panel report-history"><div className="reports-section-title"><div><span className="eyebrow">REPORT LIBRARY</span><h2>Generated report history</h2></div><span className="reports-badge">{history.length} saved</span></div>{history.length ? <div className="reports-history-list">{history.map((item) => <article key={item.report_id}><div><b>{item.report_type} report</b><small>{new Date(item.generated_at).toLocaleString()} · {item.selected_datasets?.length || 0} dataset(s)</small></div><div className="report-downloads">{item.formats.map((format) => <button key={format} onClick={() => saveDownload(item.report_id, format)} disabled={Boolean(downloading)}><Download size={13}/>{format.toUpperCase()}</button>)}</div></article>)}</div> : <div className="reports-empty-small">No reports have been generated yet.</div>}</section>
    <footer className="reports-footer">Recommendations are screening guidance, not certifications or guaranteed savings. Every report includes its evidence and data limitations.</footer>
  </div>
}
