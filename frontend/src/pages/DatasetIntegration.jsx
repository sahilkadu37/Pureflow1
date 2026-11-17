import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { AlertCircle, ArrowRight, CheckCircle2, ChevronRight, Database, FileOutput, GitMerge, LoaderCircle, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react'
import { motion } from 'framer-motion'
import { getTransformCompatibility, getTransformHistory, getTransformReport, integrateDatasets, notifyDataChanged, standardiseDatasets } from '../services/api'
import './DatasetIntegration.css'

const number = (value) => value == null ? '—' : Number(value).toLocaleString()

export default function DatasetIntegration() {
  const [compatibility, setCompatibility] = useState(null)
  const [history, setHistory] = useState([])
  const [latestReport, setLatestReport] = useState(null)
  const [selected, setSelected] = useState([])
  const [selectedKeys, setSelectedKeys] = useState([])
  const [joinType, setJoinType] = useState('inner')
  const [loading, setLoading] = useState(true)
  const [working, setWorking] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [result, setResult] = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    const [compatibilityResult, historyResult, reportResult] = await Promise.allSettled([
      getTransformCompatibility(), getTransformHistory(), getTransformReport(),
    ])
    if (compatibilityResult.status === 'fulfilled') {
      const next = compatibilityResult.value
      setCompatibility(next)
      const ids = (next.datasets || []).map((dataset) => dataset.dataset_id)
      setSelected((current) => current.filter((id) => ids.includes(id)).length ? current.filter((id) => ids.includes(id)) : ids.slice(0, 1))
    } else setError(compatibilityResult.reason.response?.data?.message || 'Could not inspect curated datasets.')
    if (historyResult.status === 'fulfilled') setHistory(historyResult.value || [])
    if (reportResult.status === 'fulfilled') setLatestReport(reportResult.value)
    setLoading(false)
  }, [])
  useEffect(() => { refresh() }, [refresh])

  const selectedPair = useMemo(() => {
    if (selected.length !== 2) return null
    return compatibility?.pairs?.find((pair) => pair.left_dataset_id === selected[0] && pair.right_dataset_id === selected[1])
      || compatibility?.pairs?.find((pair) => pair.left_dataset_id === selected[1] && pair.right_dataset_id === selected[0])
  }, [compatibility, selected])
  const pairReversed = Boolean(selectedPair && selectedPair.left_dataset_id !== selected[0])
  const candidates = selectedPair?.candidate_join_keys || []

  const toggleDataset = (id) => {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
    setSelectedKeys([]); setResult(null)
  }
  const toggleKey = (index) => setSelectedKeys((current) => current.includes(index) ? current.filter((item) => item !== index) : [...current, index])

  const standardise = async () => {
    if (!selected.length) return
    setWorking('standardise'); setError(''); setNotice(''); setResult(null)
    try {
      const response = await standardiseDatasets(selected)
      setResult(response.result)
      setNotice(response.message)
      await refresh()
      notifyDataChanged()
    } catch (err) { setError(err.response?.data?.message || 'Standardisation failed. Curated sources were not modified.') }
    finally { setWorking('') }
  }

  const integrate = async () => {
    if (selected.length !== 2 || !selectedPair || !selectedKeys.length) return
    setWorking('integrate'); setError(''); setNotice(''); setResult(null)
    const leftId = selectedPair.left_dataset_id
    const rightId = selectedPair.right_dataset_id
    const chosen = selectedKeys.map((index) => candidates[index])
    const payload = {
      dataset_ids: [leftId, rightId], join_type: joinType,
      join_keys: {
        [leftId]: chosen.map((item) => pairReversed ? item.right_column : item.left_column),
        [rightId]: chosen.map((item) => pairReversed ? item.left_column : item.right_column),
      },
    }
    try {
      const response = await integrateDatasets(payload)
      setResult(response.result)
      setNotice(response.message)
      await refresh()
      notifyDataChanged()
    } catch (err) { setError(err.response?.data?.message || 'Integration failed. Source datasets were not modified.') }
    finally { setWorking('') }
  }

  const currentResult = result || latestReport
  const preview = currentResult?.preview
  const validationChecks = currentResult?.validation?.checks || (currentResult?.validation?.datasets || []).flatMap((dataset) => (dataset.checks || []).map((check) => ({ ...check, dataset_id: dataset.dataset_id })))
  const hasCuratedSources = (compatibility?.datasets?.length || 0) > 0
  const hasStandardised = history.some((item) => item.operation === 'standardise')
  const hasIntegrated = history.some((item) => item.operation === 'integrate')
  const workflowSteps = [
    ['Curated sources', hasCuratedSources], ['Cleaning', hasCuratedSources],
    ['Standardisation', hasStandardised], ['Integration', hasIntegrated],
    ['Output', Boolean(currentResult)],
  ]

  return <motion.div className="page-content integration-page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
    <div className="integration-heading"><div><div className="live-tag"><span/> TRANSFORM &amp; INTEGRATE</div><h1>Dataset Integration</h1><p className="lead">Standardise curated sources and combine records only when verified keys and time periods align.</p></div><button className="integration-refresh" onClick={refresh} disabled={loading}><RefreshCw size={14}/> Refresh</button></div>
    <ol className="workflow-stepper" aria-label="Dataset preparation stages">{workflowSteps.map(([label, complete], index) => <li key={label} className={complete ? 'complete' : ''}><span>{complete ? <CheckCircle2 size={15}/> : index + 1}</span><b>{label}</b>{index < workflowSteps.length - 1 && <i/>}</li>)}</ol>
    {error && <div className="integration-alert error" role="alert"><AlertCircle size={16}/><span>{error}</span><button onClick={() => setError('')}>Dismiss</button></div>}
    {notice && <div className="integration-alert success" role="status"><CheckCircle2 size={16}/><span>{notice}</span><button onClick={() => setNotice('')}>Dismiss</button></div>}
    {working && <div className="quality-progress"><span/></div>}
    {loading ? <div className="dataset-list-state"><LoaderCircle className="spinning" size={21}/><span>Inspecting curated datasets…</span></div> : !compatibility?.datasets?.length ? <div className="dataset-list-state integration-empty"><div className="dataset-empty-icon"><Database size={20}/></div><strong>No curated datasets available</strong><span>Run cleaning for an uploaded dataset first. Only real files in curated storage are considered here.</span></div> : <>
      <section className="integration-section"><div className="integration-section-title"><div><span className="eyebrow">AVAILABLE SOURCES</span><h2>Curated datasets</h2></div><span className="integration-count">{compatibility.dataset_count} available</span></div>
        <div className="source-grid">{compatibility.datasets.map((dataset) => <label key={dataset.dataset_id} className={`source-card ${selected.includes(dataset.dataset_id) ? 'selected' : ''}`}><input type="checkbox" checked={selected.includes(dataset.dataset_id)} onChange={() => toggleDataset(dataset.dataset_id)}/><span className="source-checkbox">{selected.includes(dataset.dataset_id) && <CheckCircle2 size={14}/>}</span><span className="source-file-icon"><Database size={17}/></span><span className="source-info"><b>{dataset.source_filename || dataset.filename}</b><small>{number(dataset.row_count)} rows · {dataset.column_count} columns · {dataset.file_format?.toUpperCase()}</small><small>{dataset.filename}</small></span><span className="source-status"><i/>Inspected</span></label>)}</div>
      </section>

      <section className="integration-section"><div className="integration-section-title"><div><span className="eyebrow">SCHEMA REVIEW</span><h2>Compatibility and possible join keys</h2></div><span className="compatibility-summary">{compatibility.message}</span></div>
        <div className="compatibility-grid">{compatibility.datasets.map((dataset) => <article className="panel schema-card" key={dataset.dataset_id}><div className="schema-card-heading"><div><b>{dataset.source_filename || dataset.filename}</b><small>{dataset.row_count} records inspected</small></div><ShieldCheck size={16}/></div><div className="schema-columns">{(dataset.columns || []).map((column) => <div key={column.original_name}><span>{column.standardised_name}</span><code>{column.data_type}</code><small>{column.key_role ? `Possible ${column.key_role} key` : column.unit ? `Unit indicated: ${column.unit}` : 'No join role inferred'}{column.date_granularity ? ` · ${column.date_granularity}` : ''}</small></div>)}</div></article>)}</div>
        {compatibility.pairs?.length > 0 ? compatibility.pairs.map((pair) => <div className="pair-report" key={`${pair.left_dataset_id}-${pair.right_dataset_id}`}><div><b>{pair.left_filename}</b><ArrowRight size={14}/><b>{pair.right_filename}</b></div>{pair.candidate_join_keys?.length > 0 ? <><div className="candidate-key-list">{pair.candidate_join_keys.map((key) => <span key={`${key.left_column}-${key.right_column}`}>{key.left_column} ↔ {key.right_column} <small>{key.role}{key.granularity ? ` · ${key.granularity}` : ''} · {key.distinct_value_overlap} shared values · {key.safe_join ? 'safe cardinality' : 'duplicate key values'}</small></span>)}</div>{pair.unit_mismatches?.length > 0 && <p>Explicit unit mismatches are retained separately: {pair.unit_mismatches.map((item) => `${item.column} (${item.left_unit} vs ${item.right_unit})`).join(', ')}.</p>}</> : <p>{pair.reason}</p>}</div>) : <div className="pair-report no-pairs"><GitMerge size={17}/><span>{compatibility.message}</span></div>}
      </section>

      <section className="integration-section"><div className="integration-section-title"><div><span className="eyebrow">TRANSFORMATION OPTIONS</span><h2>Prepare selected sources</h2></div></div><div className="integration-action-card panel"><div className="integration-action-icon"><Sparkles size={18}/></div><div><b>Standardise selected datasets</b><p>Normalize column names, trim text whitespace, and standardize only fully parseable recognized dates. Units and uncertain values are preserved.</p></div><button className="integration-standardise-btn" onClick={standardise} disabled={!selected.length || Boolean(working)}>{working === 'standardise' ? <LoaderCircle className="spinning" size={15}/> : <FileOutput size={15}/>}Standardise {selected.length || ''}</button></div>
      </section>

      <section className="integration-section"><div className="integration-section-title"><div><span className="eyebrow">DATASET JOIN</span><h2>Integrate compatible datasets</h2></div></div>{selected.length !== 2 ? <div className="panel integration-guidance"><GitMerge size={17}/><span>Select exactly two curated datasets to review a potential join. Current selection: {selected.length}.</span></div> : !selectedPair?.compatible ? <div className="panel integration-guidance"><AlertCircle size={17}/><span>{selectedPair?.reason || 'No compatibility evidence is available for this dataset pair. Standardise/inspect sources first; joins are not inferred from similar labels.'}</span></div> : <div className="panel join-config"><div className="join-config-row"><label>Join type<select value={joinType} onChange={(event) => setJoinType(event.target.value)}><option value="inner">Inner join</option><option value="left">Left join</option></select></label><span>Dates must have matching granularity. Many-to-many joins are blocked unless a composite key makes the selected combination unique.</span></div><h3>Select verified join key(s)</h3><div className="join-key-options">{candidates.map((key, index) => <label key={`${key.left_column}-${key.right_column}`}><input type="checkbox" checked={selectedKeys.includes(index)} onChange={() => toggleKey(index)}/><span><b>{pairReversed ? key.right_column : key.left_column}</b><ArrowRight size={13}/><b>{pairReversed ? key.left_column : key.right_column}</b><small>{key.role}{key.granularity ? ` · ${key.granularity}` : ''} · {key.distinct_value_overlap} shared values · {key.left_value_coverage}% / {key.right_value_coverage}% distinct coverage{key.safe_join ? '' : ' · duplicate key values: select a composite key or the join may be rejected'}</small></span></label>)}</div><button className="integrate-button" onClick={integrate} disabled={!selectedKeys.length || Boolean(working)}>{working === 'integrate' ? <LoaderCircle className="spinning" size={15}/> : <GitMerge size={15}/>}Integrate selected datasets <ChevronRight size={14}/></button></div>}</section>

      {currentResult && <section className="integration-section"><div className="integration-section-title"><div><span className="eyebrow">PROCESSING RESULT</span><h2>{currentResult.operation === 'integrate' ? 'Integration report' : 'Standardisation report'}</h2></div><span className={currentResult.validation?.passed === false ? 'flagged-status' : 'passed-status'}>{currentResult.validation?.passed === false ? 'Review required' : 'Completed'}</span></div>
        <div className="integration-result-grid"><article className="panel integration-result-metric"><span>Output rows</span><b>{number(currentResult.output_rows)}</b></article><article className="panel integration-result-metric"><span>Output columns</span><b>{number(Array.isArray(currentResult.output_columns) ? currentResult.output_columns.length : currentResult.output_columns ?? currentResult.outputs?.[0]?.output_columns?.length)}</b></article>{(currentResult.join_results || []).map((join, index) => <Fragment key={index}><article className="panel integration-result-metric"><span>Matched rows</span><b>{number(join.matched_rows)}</b></article><article className="panel integration-result-metric"><span>Left / right unmatched</span><b>{number(join.left_unmatched_records)} / {number(join.right_unmatched_records)}</b></article><article className="panel integration-result-metric"><span>Join coverage</span><b>{join.match_percentage == null ? '—' : `${join.match_percentage}%`}</b></article></Fragment>)}</div>
        <div className="panel lineage-panel"><b>Output file</b><span>{currentResult.output_filename || currentResult.outputs?.map((item) => item.output_filename).join(', ')}</span><b>Lineage</b><span>{(currentResult.sources || []).map((item) => item.filename).join(' + ') || currentResult.outputs?.map((item) => item.source_filename).join(' · ')}</span>{currentResult.lineage_columns?.length > 0 && <><b>Source row columns</b><span>{currentResult.lineage_columns.join(', ')}</span></>}</div>
        {(currentResult.steps || currentResult.outputs?.flatMap((item) => item.steps || []) || []).length > 0 && <div className="panel transform-steps"><b>Documented transformation steps</b>{(currentResult.steps || currentResult.outputs?.flatMap((item) => item.steps || []) || []).map((step, index) => <div key={index}><CheckCircle2 size={13}/><span>{typeof step === 'string' ? step : `${step.step}: ${step.action || JSON.stringify(step.columns_renamed || step.columns || {})}`}</span></div>)}</div>}
        {currentResult.unit_mismatches?.length > 0 && <div className="integration-guidance unit-warning"><AlertCircle size={15}/><span>Unit mismatches were preserved without conversion: {currentResult.unit_mismatches.map((item) => `${item.column} (${item.left_unit} vs ${item.right_unit})`).join(', ')}.</span></div>}
        {validationChecks.length > 0 && <div className="panel transform-steps"><b>Validation checks</b>{validationChecks.map((check, index) => <div key={`${check.dataset_id || ''}-${check.check}-${index}`}>{check.passed ? <CheckCircle2 size={13}/> : <AlertCircle size={13}/>}<span>{check.dataset_id ? `${check.dataset_id}: ` : ''}{check.check}{check.details ? ` · ${JSON.stringify(check.details)}` : ''}</span></div>)}</div>}
        {preview?.columns?.length > 0 && <div className="dataset-table-wrap transform-preview"><table className="dataset-table"><thead><tr>{preview.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{preview.records.map((record, index) => <tr key={index}>{preview.columns.map((column) => <td key={column}>{record[column] == null ? '—' : String(record[column])}</td>)}</tr>)}</tbody></table></div>}
      </section>}

      <section className="integration-section"><div className="integration-section-title"><div><span className="eyebrow">AUDIT TRAIL</span><h2>Transformation history</h2></div></div>{history.length ? <div className="panel transform-history">{history.map((entry) => <div key={entry.job_id}><span className="history-icon">{entry.operation === 'integrate' ? <GitMerge size={14}/> : <Sparkles size={14}/>}</span><span><b>{entry.operation === 'integrate' ? 'Datasets integrated' : 'Dataset standardised'}</b><small>{new Date(entry.generated_at).toLocaleString()}</small></span><span>{entry.output_filename || 'Multiple standardised outputs'} · {number(entry.output_rows)} rows</span></div>)}</div> : <div className="panel integration-guidance">No transformations have been run yet.</div>}</section>
    </>}
  </motion.div>
}
