import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, ChevronRight, Database, Eye, FileSpreadsheet, FileUp, Info, LoaderCircle, Trash2, UploadCloud, X } from 'lucide-react'
import { motion } from 'framer-motion'
import { deleteDataset, getDataset, getDatasetPreview, getDatasets, notifyDataChanged, uploadDataset } from '../services/api'

const ACCEPTED = ['csv', 'xlsx', 'xls', 'parquet']
const MAX_BYTES = 100 * 1024 * 1024
const formatBytes = (bytes) => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`
const formatDate = (value) => value ? new Date(value).toLocaleString() : '—'

export default function DatasetExplorer() {
  const inputRef = useRef(null)
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [listError, setListError] = useState('')
  const [file, setFile] = useState(null)
  const [progress, setProgress] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const [message, setMessage] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState('')
  const [details, setDetails] = useState(null)
  const [detailsError, setDetailsError] = useState('')
  const [detailsLoading, setDetailsLoading] = useState(false)

  const refreshDatasets = useCallback(async () => {
    setLoading(true)
    setListError('')
    try { const result = await getDatasets(); setDatasets(result.datasets || []) }
    catch (error) { setListError(error.response?.data?.message || 'Could not load datasets from the backend.') }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { refreshDatasets() }, [refreshDatasets])

  const receiveFile = async (selected) => {
    if (!selected) return
    setMessage(null)
    const extension = selected.name.split('.').pop()?.toLowerCase()
    if (!ACCEPTED.includes(extension)) {
      setFile(null); setMessage({ type: 'error', text: 'Unsupported file type. Choose CSV, XLSX, XLS, or Parquet.' }); return
    }
    if (selected.size === 0) {
      setFile(null); setMessage({ type: 'error', text: 'This file is empty. Choose a non-empty dataset.' }); return
    }
    if (selected.size > MAX_BYTES) {
      setFile(null); setMessage({ type: 'error', text: 'File exceeds the 100 MB limit.' }); return
    }
    setFile(selected); setProgress(0); setUploading(true)
    try {
      const result = await uploadDataset(selected, setProgress)
      setProgress(100)
      setMessage({ type: 'success', text: `${result.dataset.original_filename} uploaded successfully.` })
      await refreshDatasets()
      notifyDataChanged()
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.message || 'Upload failed. Check the backend connection and try again.' })
    } finally { setUploading(false) }
  }

  const onInputChange = (event) => { receiveFile(event.target.files?.[0]); event.target.value = '' }
  const onDrop = (event) => { event.preventDefault(); setDragging(false); receiveFile(event.dataTransfer.files?.[0]) }

  const openPreview = async (dataset) => {
    setPreview({ dataset, records: [] }); setPreviewError(''); setPreviewLoading(true)
    try { setPreview({ dataset, ...(await getDatasetPreview(dataset.dataset_id)) }) }
    catch (error) { setPreviewError(error.response?.data?.message || 'Could not load this dataset preview.') }
    finally { setPreviewLoading(false) }
  }

  const openDetails = async (dataset) => {
    setDetails({ ...dataset }); setDetailsError(''); setDetailsLoading(true)
    try { const result = await getDataset(dataset.dataset_id); setDetails(result.dataset) }
    catch (error) { setDetailsError(error.response?.data?.message || 'Could not load dataset details.') }
    finally { setDetailsLoading(false) }
  }

  const removeDataset = async (dataset) => {
    if (!window.confirm(`Delete “${dataset.original_filename}” and its uploaded file? This cannot be undone.`)) return
    setDeletingId(dataset.dataset_id)
    try {
      const deletion = await deleteDataset(dataset.dataset_id)
      setMessage({ type: deletion.cleanup_warnings?.length ? 'error' : 'success', text: deletion.cleanup_warnings?.length
        ? `${dataset.original_filename} was removed from analytics, but some owned files could not be removed.`
        : `${dataset.original_filename} was deleted.` })
      if (preview?.dataset.dataset_id === dataset.dataset_id) setPreview(null)
      if (details?.dataset_id === dataset.dataset_id) setDetails(null)
      await refreshDatasets()
      notifyDataChanged()
    } catch (error) { setMessage({ type: 'error', text: error.response?.data?.message || 'Could not delete this dataset.' }) }
    finally { setDeletingId(null) }
  }

  return <motion.div className="page-content dataset-page" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .25 }}>
    <div className="dataset-heading"><div><div className="live-tag"><span/> DATA MANAGEMENT</div><h1>Dataset Explorer</h1><p className="lead">Upload and inspect source files for your water intelligence workspace.</p></div><button className="dataset-upload-top" onClick={() => inputRef.current?.click()} disabled={uploading}><FileUp size={16}/> Upload Dataset</button><input ref={inputRef} className="visually-hidden" type="file" accept=".csv,.xlsx,.xls,.parquet" onChange={onInputChange}/></div>

    <section id="upload" className={`upload-dropzone ${dragging ? 'is-dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false) }} onDrop={onDrop}>
      <div className="upload-symbol"><UploadCloud size={23}/></div><h2>Drag and drop your dataset here</h2><p>Upload a file to start exploring your data.</p><button className="browse-button" onClick={() => inputRef.current?.click()} disabled={uploading}><FileSpreadsheet size={15}/> Browse Files</button><span className="upload-constraints">CSV, XLSX, XLS or Parquet <i/> Maximum file size 100 MB</span>
      {file && <div className="selected-file"><div className="selected-file-icon"><FileSpreadsheet size={17}/></div><div className="selected-file-details"><strong>{file.name}</strong><span>{formatBytes(file.size)}{uploading ? ` · Uploading ${progress}%` : ''}</span></div>{uploading ? <LoaderCircle className="spinning" size={17}/> : <CheckCircle2 size={17}/>}</div>}
      {uploading && <div className="upload-progress"><span style={{ width: `${progress}%` }}/></div>}
    </section>
    {message && <div className={`dataset-message ${message.type}`} role="status">{message.type === 'success' ? <CheckCircle2 size={16}/> : <AlertCircle size={16}/>}<span>{message.text}</span><button onClick={() => setMessage(null)} aria-label="Dismiss message"><X size={15}/></button></div>}

    <section className="dataset-list-section" aria-busy={Boolean(deletingId)}><div className="dataset-list-heading"><div><h2>Your datasets</h2><p>Original uploads are stored securely in the backend workspace.</p></div><button className="refresh-datasets" onClick={refreshDatasets} disabled={loading || Boolean(deletingId)}>{loading || deletingId ? <LoaderCircle className="spinning" size={15}/> : 'Refresh'}{!loading && !deletingId && <ChevronRight size={14}/>}</button></div>
      {listError ? <div className="dataset-list-state error-state"><AlertCircle size={19}/><strong>Dataset list unavailable</strong><span>{listError}</span><button onClick={refreshDatasets}>Retry</button></div> : loading ? <div className="dataset-list-state"><LoaderCircle className="spinning" size={21}/><span>Loading datasets…</span></div> : datasets.length === 0 ? <div className="dataset-list-state"><div className="dataset-empty-icon"><Database size={20}/></div><strong>No datasets uploaded yet</strong><span>Your uploaded datasets will appear here.</span></div> : <div className="dataset-table-wrap"><table className="dataset-table"><thead><tr><th>DATASET NAME</th><th>TYPE</th><th>FILE SIZE</th><th>ROWS</th><th>COLUMNS</th><th>UPLOADED</th><th>STATUS</th><th>ACTIONS</th></tr></thead><tbody>{datasets.map((item) => <tr key={item.dataset_id}><td><div className="dataset-name-cell"><span><FileSpreadsheet size={15}/></span><strong title={item.original_filename}>{item.original_filename}</strong></div></td><td><span className="format-chip">{item.file_format.toUpperCase()}</span></td><td>{formatBytes(item.file_size)}</td><td>{Number(item.row_count).toLocaleString()}</td><td>{item.column_count}</td><td>{formatDate(item.upload_timestamp)}</td><td><span className="ready-status"><i/>{item.status || 'ready'}</span></td><td><div className="dataset-actions"><button onClick={() => openDetails(item)} title="View dataset metadata" aria-label={`View ${item.original_filename}`}><Info size={15}/></button><button onClick={() => openPreview(item)} title="Preview dataset" aria-label={`Preview ${item.original_filename}`}><Eye size={15}/></button><button className="delete-action" onClick={() => removeDataset(item)} title="Delete dataset" aria-label={`Delete ${item.original_filename}`}><Trash2 size={15}/></button></div></td></tr>)}</tbody></table></div>}
    </section>

    {preview && <div className="preview-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null) }}><section className="preview-modal" role="dialog" aria-modal="true" aria-labelledby="preview-title"><div className="preview-header"><div><span className="eyebrow">DATASET PREVIEW</span><h2 id="preview-title">{preview.dataset.original_filename}</h2><p>{preview.dataset.row_count.toLocaleString()} rows · {preview.dataset.column_count} columns · First 10 records</p></div><button onClick={() => setPreview(null)} aria-label="Close preview"><X size={18}/></button></div>{previewLoading ? <div className="dataset-list-state"><LoaderCircle className="spinning" size={21}/><span>Loading preview…</span></div> : previewError ? <div className="dataset-message error"><AlertCircle size={16}/>{previewError}</div> : <><div className="preview-columns"><strong>Columns and data types</strong><div>{(preview.columns || []).map((column) => <span key={column}><b>{column}</b><small>{preview.data_types?.[column] || 'unknown'}</small></span>)}</div></div><div className="preview-table-wrap"><table className="dataset-table preview-table"><thead><tr>{(preview.columns || []).map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{(preview.records || []).map((record, rowIndex) => <tr key={rowIndex}>{(preview.columns || []).map((column) => <td key={column}>{record[column] == null ? '—' : String(record[column])}</td>)}</tr>)}</tbody></table></div>{preview.records?.length === 0 && <p className="preview-no-records">This dataset has column headers but no data records.</p>}</>}</section></div>}
    {details && <div className="preview-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDetails(null) }}><section className="preview-modal details-modal" role="dialog" aria-modal="true" aria-labelledby="details-title"><div className="preview-header"><div><span className="eyebrow">DATASET METADATA</span><h2 id="details-title">{details.original_filename}</h2></div><button onClick={() => setDetails(null)} aria-label="Close dataset details"><X size={18}/></button></div>{detailsLoading ? <div className="dataset-list-state"><LoaderCircle className="spinning" size={21}/><span>Loading metadata…</span></div> : detailsError ? <div className="dataset-message error"><AlertCircle size={16}/>{detailsError}</div> : <div className="metadata-grid">{[['Dataset ID',details.dataset_id],['File format',details.file_format?.toUpperCase()],['File size',formatBytes(details.file_size)],['Rows',Number(details.row_count).toLocaleString()],['Columns',details.column_count],['Uploaded',formatDate(details.upload_timestamp)],['Stored filename',details.stored_filename]].map(([label,value])=><div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div>}</section></div>}
  </motion.div>
}
