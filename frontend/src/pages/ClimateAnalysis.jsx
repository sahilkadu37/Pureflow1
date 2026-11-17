import { useEffect, useState } from 'react'
import { AlertCircle, CloudSun, LoaderCircle, RefreshCw } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getClimateAnalytics } from '../services/api'
import './WaterAnalytics.css'

export default function ClimateAnalysis() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const refresh = async () => {
    setLoading(true); setError('')
    try { setResult(await getClimateAnalytics()) }
    catch (err) { setError(err.response?.data?.message || 'Climate analytics could not be loaded.') }
    finally { setLoading(false) }
  }
  useEffect(() => { refresh() }, [])
  const records = result?.data || []
  return <div className="page-content analysis-page">
    <div className="analysis-heading"><div><div className="live-tag"><span/> SQLITE / CLIMATE</div><h1>Climate Analysis</h1><p className="lead">Climate metrics are shown only when transformed records include valid links to stored locations.</p></div><button className="analysis-refresh" onClick={refresh} disabled={loading}><RefreshCw size={15}/> Refresh</button></div>
    {error && <div className="analysis-error"><AlertCircle size={16}/>{error}</div>}
    <section className="analysis-panel"><h2><CloudSun size={17}/> Average temperature by location</h2>{loading ? <div className="analysis-empty"><LoaderCircle className="analysis-spin" size={17}/> Loading climate recordsâ€¦</div> : records.length ? <div className="analysis-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={records}><CartesianGrid stroke="#ffffff" strokeOpacity={.07}/><XAxis dataKey="place_name" stroke="#9aabb4"/><YAxis stroke="#9aabb4"/><Tooltip/><Bar dataKey="average_temperature" fill="#FF6B24" name="Average temperature"/></BarChart></ResponsiveContainer></div> : <div className="analysis-empty">{result?.message || 'No compatible climate measurements are stored. Climate and water comparisons are unavailable.'}</div>}</section>
  </div>
}
