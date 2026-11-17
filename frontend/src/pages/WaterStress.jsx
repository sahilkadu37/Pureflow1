import { useEffect, useState } from 'react'
import { AlertCircle, Globe2, LoaderCircle, RefreshCw } from 'lucide-react'
import { getWaterStress } from '../services/api'
import './WaterAnalytics.css'

export default function WaterStress() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const refresh = async () => {
    setLoading(true); setError('')
    try { setResult(await getWaterStress()) }
    catch (err) { setError(err.response?.data?.message || 'Water-stress analysis could not be loaded.') }
    finally { setLoading(false) }
  }
  useEffect(() => { refresh() }, [])
  const rows = result?.data || result?.locations || []
  return <div className="page-content analysis-page">
    <div className="analysis-heading"><div><div className="live-tag"><span/> SQLITE / WATER RISK</div><h1>Water Stress Analysis</h1><p className="lead">Regional risk is shown only when source assessments are linked to PureFlow locations.</p></div><button className="analysis-refresh" onClick={refresh} disabled={loading}><RefreshCw size={15}/> Refresh</button></div>
    {error && <div className="analysis-error"><AlertCircle size={16}/>{error}</div>}
    <section className="analysis-panel"><h2><Globe2 size={17}/> Linked location assessments</h2>{loading ? <div className="analysis-empty"><LoaderCircle className="analysis-spin" size={17}/> Loading water-stress records…</div> : rows.length ? <div className="analysis-table-wrap"><table><thead><tr><th>LOCATION</th><th>COUNTRY</th><th>YEAR</th><th>STRESS LEVEL</th><th>RISK SCORE</th></tr></thead><tbody>{rows.map((row, index) => <tr key={`${row.place_name}-${row.assessment_year}-${index}`}><td>{row.place_name}</td><td>{row.country || '—'}</td><td>{row.assessment_year || '—'}</td><td>{row.water_stress_level || '—'}</td><td>{row.water_risk_score ?? '—'}</td></tr>)}</tbody></table></div> : <div className="analysis-empty">{result?.message || 'No linked water-stress assessments are stored. A water-stress map cannot be supported by the available records.'}</div>}</section>
  </div>
}
