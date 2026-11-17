import { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, ChevronDown, ClipboardCheck, Database, FileWarning, LoaderCircle, Play, RefreshCw, Sparkles } from 'lucide-react'
import { motion } from 'framer-motion'
import { cleanDataset, downloadCleanedCsv, getCleanedPreview, getCleaningHistory, getDatasets, getQualityReport, notifyDataChanged, runQualityCheck } from '../services/api'

const value = (input) => input == null ? '—' : Number(input).toLocaleString()

export default function DataQuality() {
  const [datasets, setDatasets] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [report, setReport] = useState(null)
  const [history, setHistory] = useState([])
  const [loadingDatasets, setLoadingDatasets] = useState(true)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [cleanedPreview, setCleanedPreview] = useState(null)
  const [downloading, setDownloading] = useState(false)

  const loadDatasets = useCallback(async () => {
    setLoadingDatasets(true)
    setError('')
    try {
      const result = await getDatasets()
      const list = result.datasets || []
      setDatasets(list)
      setSelectedId((current) => list.some((item) => item.dataset_id === current) ? current : list[0]?.dataset_id || '')
    } catch (err) { setError(err.response?.data?.message || 'Could not load datasets.') }
    finally { setLoadingDatasets(false) }
  }, [])
  useEffect(() => { loadDatasets() }, [loadDatasets])

  useEffect(() => {
    if (!selectedId) { setReport(null); setHistory([]); setCleanedPreview(null); return }
    let active = true
    setReport(null); setHistory([]); setCleanedPreview(null); setError('')
    Promise.allSettled([getQualityReport(selectedId), getCleaningHistory(selectedId)]).then(([reportResult, historyResult]) => {
      if (!active) return
      if (reportResult.status === 'fulfilled') setReport(reportResult.value.report)
      if (historyResult.status === 'fulfilled') setHistory(historyResult.value.history || [])
    })
    return () => { active = false }
  }, [selectedId])

  const selected = useMemo(() => datasets.find((item) => item.dataset_id === selectedId), [datasets, selectedId])
  const profile = report?.latest_quality_check?.profile || report?.before || null
  const comparison = report?.summary || null
  const runCheck = async () => {
    if (!selectedId) return
    setBusy('quality'); setError(''); setNotice(''); setCleanedPreview(null)
    try {
      const result = await runQualityCheck(selectedId)
      setReport((current) => ({ ...(current || {}), latest_quality_check: { checked_at: new Date().toISOString(), profile: result.profile } }))
      const latest = await getQualityReport(selectedId)
      setReport(latest.report)
      const historyResult = await getCleaningHistory(selectedId)
      setHistory(historyResult.history || [])
      setNotice('Quality assessment completed. No source files were changed.')
    } catch (err) { setError(err.response?.data?.message || 'Quality assessment failed.') }
    finally { setBusy('') }
  }
  const runClean = async () => {
    if (!selectedId) return
    setBusy('clean'); setError(''); setNotice(''); setCleanedPreview(null)
    try {
      const result = await cleanDataset(selectedId)
      setReport(result.report)
      const historyResult = await getCleaningHistory(selectedId)
      setHistory(historyResult.history || [])
      setNotice(result.message || 'Cleaning completed. The original upload was preserved.')
      notifyDataChanged()
    } catch (err) { setError(err.response?.data?.message || 'Cleaning failed. The original file was preserved.') }
    finally { setBusy('') }
  }
  const downloadCleaned = async () => {
    if (!selectedId || downloading) return
    setDownloading(true); setError('')
    try {
      const blob = await downloadCleanedCsv(selectedId)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = report?.cleaned_filename || `${selectedId}_cleaned.csv`
      document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url)
    } catch (err) { setError(err.response?.data?.message || 'The cleaned CSV is unavailable. Run cleaning again and retry.') }
    finally { setDownloading(false) }
  }
  const showCleanedPreview = async () => {
    if (!selectedId) return
    setBusy('preview'); setError('')
    try { setCleanedPreview(await getCleanedPreview(selectedId)) }
    catch (err) { setError(err.response?.data?.message || 'Cleaned preview is unavailable. Run cleaning first.') }
    finally { setBusy('') }
  }

  const missingValues = profile?.missing_values || {}
  const missingRows = Object.entries(missingValues).sort((a, b) => (b[1]?.count || 0) - (a[1]?.count || 0))
  const dataTypes = profile?.data_types?.summary || {}
  const maxMissing = missingRows.reduce((largest, [, entry]) => Math.max(largest, entry.count || 0), 1)
  const invalidValues = profile?.invalid_values || {}

  return <motion.div className="page-content quality-page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
    <div className="quality-heading"><div><div className="live-tag"><span/> DATA RELIABILITY</div><h1>Data Quality</h1><p className="lead">Assess source data and apply documented, conservative cleaning operations.</p></div><button className="quality-refresh" onClick={loadDatasets} disabled={loadingDatasets}><RefreshCw size={14}/> Refresh datasets</button></div>
    <section className="panel quality-toolbar"><div className="quality-dataset-select"><Database size={17}/><div><label htmlFor="quality-dataset">Selected dataset</label><select id="quality-dataset" value={selectedId} onChange={(event) => setSelectedId(event.target.value)} disabled={!datasets.length || loadingDatasets}><option value="">{loadingDatasets ? 'Loading datasets…' : 'Choose a dataset'}</option>{datasets.map((dataset) => <option key={dataset.dataset_id} value={dataset.dataset_id}>{dataset.original_filename}</option>)}</select><ChevronDown size={14}/></div></div><div className="quality-actions"><button className="quality-check-btn" onClick={runCheck} disabled={!selectedId || Boolean(busy)}><ClipboardCheck size={15}/>{busy === 'quality' ? 'Checking…' : 'Run Quality Check'}</button><button className="quality-clean-btn" onClick={runClean} disabled={!selectedId || Boolean(busy)}><Sparkles size={15}/>{busy === 'clean' ? 'Cleaning…' : 'Clean Dataset'}</button></div></section>
    {busy && <div className="quality-progress" aria-label="Operation in progress"><span/></div>}
    {error && <div className="quality-message error" role="alert"><AlertCircle size={16}/><span>{error}</span><button onClick={() => setError('')}>Dismiss</button></div>}
    {notice && <div className="quality-message success" role="status"><CheckCircle2 size={16}/><span>{notice}</span><button onClick={() => setNotice('')}>Dismiss</button></div>}
    {loadingDatasets ? <div className="dataset-list-state"><LoaderCircle className="spinning" size={21}/><span>Loading uploaded datasets…</span></div> : !datasets.length ? <div className="dataset-list-state quality-no-data"><div className="dataset-empty-icon"><Database size={20}/></div><strong>No uploaded datasets</strong><span>Upload a real dataset in Dataset Explorer before running quality checks.</span></div> : <>
      <section className="quality-section"><div className="quality-section-head"><div><span className="eyebrow">SOURCE PROFILE</span><h2>Dataset overview</h2></div>{selected && <span className="quality-file-chip">{selected.file_format.toUpperCase()} · {selected.original_filename}</span>}</div>
        <div className="quality-metrics"><article className="panel quality-metric"><span>Total rows</span><strong>{value(profile?.total_rows ?? selected?.row_count)}</strong><small>Original uploaded records</small></article><article className="panel quality-metric"><span>Total columns</span><strong>{value(profile?.total_columns ?? selected?.column_count)}</strong><small>Fields in the source dataset</small></article><article className="panel quality-metric"><span>Missing values</span><strong>{value(profile?.missing_value_count)}</strong><small>{profile ? `${profile.missing_value_percentage ?? '—'}% of values` : 'Run a quality check to assess'}</small></article><article className="panel quality-metric"><span>Duplicate records</span><strong>{value(profile?.duplicate_row_count)}</strong><small>{profile ? 'Exact duplicate rows' : 'Run a quality check to assess'}</small></article></div>
      </section>
      <section className="quality-section"><div className="quality-section-head"><div><span className="eyebrow">ASSESSMENT</span><h2>Data quality analysis</h2></div>{profile && <span className="quality-timestamp">Memory footprint {value(profile.memory_usage_bytes)} bytes</span>}</div>
        {!profile ? <div className="panel quality-empty-hint"><FileWarning size={18}/><span>Run a quality check to inspect missing values, duplicates, data types and invalid values.</span></div> : <div className="quality-analysis-grid"><section className="panel quality-analysis-card"><h3>Missing values by column</h3>{missingRows.length ? <div className="missing-bars">{missingRows.map(([column, detail]) => <div key={column} className="missing-bar-row"><div><span title={column}>{column}</span><b>{value(detail.count)} <small>({detail.percentage ?? '—'}%)</small></b></div><i><span style={{ width: `${Math.max(1, (detail.count / maxMissing) * 100)}%` }}/></i></div>)}</div> : <p className="quality-muted">No columns found.</p>}</section><section className="panel quality-analysis-card"><h3>Data type summary</h3><div className="dtype-list">{Object.entries(dataTypes).map(([type, count]) => <div key={type}><code>{type}</code><b>{count} {count === 1 ? 'column' : 'columns'}</b></div>)}</div><div className="duplicate-callout"><div><span>Exact duplicate rows</span><strong>{value(profile.duplicate_row_count)}</strong></div><span className={profile.duplicate_row_count ? 'flagged-status' : 'passed-status'}>{profile.duplicate_row_count ? 'Requires cleaning' : 'No duplicates found'}</span></div></section><section className="panel quality-analysis-card invalid-card"><h3>Invalid value summary</h3>{Object.keys(invalidValues).length ? <div className="invalid-list">{Object.entries(invalidValues).map(([column, detail]) => <div key={column}><span>{column}</span><b>{value(detail.count)} <small>{detail.kind.replaceAll('_', ' ')}</small></b></div>)}</div> : <div className="quality-clear"><CheckCircle2 size={17}/><span>No invalid values detected by established date and numeric rules.</span></div>}</section></div>}
      </section>
      <section className="quality-section"><div className="quality-section-head"><div><span className="eyebrow">CLEANING RESULTS</span><h2>Before and after comparison</h2></div>{comparison && <button className="preview-clean-btn" onClick={showCleanedPreview} disabled={Boolean(busy)}>{busy === 'preview' ? 'Loading…' : 'Preview cleaned data'}</button>}</div>
        {comparison ? <div className="comparison-grid"><article className="panel comparison-card"><span>Rows</span><div><b>{value(comparison.rows_before)}</b><i>Before</i><b>{value(comparison.rows_after)}</b><i>After</i></div></article><article className="panel comparison-card"><span>Columns</span><div><b>{value(comparison.columns_before)}</b><i>Before</i><b>{value(comparison.columns_after)}</b><i>After</i></div></article><article className="panel comparison-card"><span>Missing values</span><div><b>{value(comparison.missing_values_before)}</b><i>Before</i><b>{value(comparison.missing_values_after)}</b><i>After</i></div></article><article className="panel comparison-card"><span>Duplicate records</span><div><b>{value(comparison.duplicates_before)}</b><i>Before</i><b>{value(comparison.duplicates_after)}</b><i>After</i></div></article><article className="panel comparison-card"><span>Completeness</span><div><b>{comparison.completeness_before == null ? '—' : `${comparison.completeness_before}%`}</b><i>Before</i><b>{comparison.completeness_after == null ? '—' : `${comparison.completeness_after}%`}</b><i>After</i></div></article></div> : <div className="panel quality-empty-hint"><Play size={16}/><span>Cleaning comparison appears after you run Clean Dataset.</span></div>}
      </section>
      {report?.problems && <section className="quality-section"><div className="quality-section-head"><div><span className="eyebrow">AUDIT TRAIL</span><h2>Cleaning report</h2></div><span className={report.validation?.passed ? 'passed-status' : 'flagged-status'}>{report.validation?.passed ? 'Cleaning complete' : 'Review required'}</span></div><div className="panel operation-table-wrap"><p>{report.cleaned_filename} · {value(comparison?.rows_after)} rows · {value(comparison?.columns_after)} columns</p><button className="quality-clean-btn" onClick={downloadCleaned} disabled={downloading}>{downloading ? 'Preparing download…' : 'Download Cleaned CSV'}</button><table className="operation-table"><thead><tr><th>PROBLEM</th><th>ROWS AFFECTED</th><th>ACTION TAKEN</th></tr></thead><tbody>{report.problems.map((operation, index) => <tr key={`${operation.problem}-${index}`}><td>{operation.problem}</td><td>{value(operation.rows_affected)}</td><td>{operation.action_taken}{operation.values_affected != null ? ` (${value(operation.values_affected)} values)` : ''}</td></tr>)}</tbody></table><div className="validation-list">{(report.validation?.checks || []).map((check) => <div key={check.check} className={check.passed ? 'validation-ok' : 'validation-fail'}>{check.passed ? <CheckCircle2 size={14}/> : <AlertCircle size={14}/>}<span>{check.check}</span>{check.details && <small>{JSON.stringify(check.details)}</small>}</div>)}</div></div></section>}
      {cleanedPreview && <section className="quality-section"><div className="quality-section-head"><div><span className="eyebrow">CURATED OUTPUT</span><h2>Cleaned data preview</h2></div><span className="quality-file-chip">First 10 rows</span></div><div className="dataset-table-wrap"><table className="dataset-table"><thead><tr>{cleanedPreview.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{cleanedPreview.records.map((record, index) => <tr key={index}>{cleanedPreview.columns.map((column) => <td key={column}>{record[column] == null ? '—' : String(record[column])}</td>)}</tr>)}</tbody></table></div></section>}
      {history.length > 0 && <section className="quality-section"><div className="quality-section-head"><div><span className="eyebrow">ACTIVITY</span><h2>Cleaning history</h2></div></div><div className="panel history-list">{[...history].reverse().map((entry, index) => <div key={`${entry.timestamp}-${index}`}><span className="history-icon">{entry.operation === 'clean' ? <Sparkles size={14}/> : <ClipboardCheck size={14}/>}</span><span><b>{entry.operation === 'clean' ? 'Dataset cleaned' : 'Quality check completed'}</b><small>{new Date(entry.timestamp).toLocaleString()}</small></span><span className="history-summary">{entry.summary ? `${value(entry.summary.rows)} rows · ${value(entry.summary.missing_values)} missing · ${value(entry.summary.duplicates)} duplicates` : entry.validation?.passed ? 'Validation passed' : 'Review required'}</span></div>)}</div></section>}
    </>}
  </motion.div>
}
