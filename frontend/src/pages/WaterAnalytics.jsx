import { useEffect, useState } from 'react'
import { AlertCircle, Droplets, Gauge, LoaderCircle, RefreshCw } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { getSqlAnalytics } from '../services/api'
import './WaterAnalytics.css'

const fmt = (value, digits = 2) => value == null ? 'â€”' : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits })

export default function WaterAnalytics() {
  const [data, setData] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const refresh = async () => {
    setLoading(true); setError('')
    const names = ['water-consumption', 'annual-trends', 'monthly-trends', 'country-comparison', 'wue']
    const results = await Promise.allSettled(names.map((name) => getSqlAnalytics(name)))
    const next = Object.fromEntries(names.map((name, index) => [name, results[index].status === 'fulfilled' ? results[index].value : null]))
    if (results.some((result) => result.status === 'rejected')) setError('Some SQL-backed water analytics could not be loaded.')
    setData(next); setLoading(false)
  }
  useEffect(() => { refresh() }, [])
  const water = data['water-consumption']?.data || {}
  const annual = data['annual-trends']?.data || []
  const monthly = data['monthly-trends']?.data || []
  const countries = data['country-comparison']?.data || []
  const wue = data.wue?.data || []
  const Empty = ({ children }) => <div className="analysis-empty">{loading ? <><LoaderCircle className="analysis-spin" size={17}/> Loading stored observationsâ€¦</> : children}</div>

  return <div className="page-content analysis-page">
    <div className="analysis-heading"><div><div className="live-tag"><span/> SQLITE / WATER METRICS</div><h1>Water Analytics</h1><p className="lead">Source-reported consumption and WUE from transformed records in SQLite.</p></div><button className="analysis-refresh" onClick={refresh} disabled={loading}><RefreshCw size={15}/> Refresh</button></div>
    {error && <div className="analysis-error"><AlertCircle size={16}/>{error}</div>}
    <div className="analysis-kpis"><article><Droplets size={17}/><small>Consumption Â· million gallons</small><b>{fmt(water.million_gallons)}</b><span>{fmt(water.gallon_observations, 0)} observations</span></article><article><Droplets size={17}/><small>Consumption Â· million litres</small><b>{fmt(water.million_litres)}</b><span>{fmt(water.litre_observations, 0)} observations</span></article><article><Gauge size={17}/><small>WUE Â· L/kWh</small><b>{fmt(wue.length ? wue.reduce((sum, row) => sum + row.average_wue_l_per_kwh * row.observations, 0) / wue.reduce((sum, row) => sum + row.observations, 0) : null, 3)}</b><span>{wue.reduce((sum, row) => sum + row.observations, 0)} observations</span></article></div>
    <div className="analysis-grid"><section className="analysis-panel"><h2>Annual consumption Â· million litres</h2>{annual.length ? <div className="analysis-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={annual}><CartesianGrid stroke="#EEE8DF"/><XAxis dataKey="reporting_year"/><YAxis/><Tooltip/><Line type="monotone" dataKey="million_litres" stroke="#F58220" name="Million litres"/></LineChart></ResponsiveContainer></div> : <Empty>{data['annual-trends']?.message || 'No annual consumption periods are available.'}</Empty>}</section>
      <section className="analysis-panel"><h2>Annual consumption Â· million gallons</h2>{annual.some((row) => row.million_gallons != null) ? <div className="analysis-chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={annual}><CartesianGrid stroke="#EEE8DF"/><XAxis dataKey="reporting_year"/><YAxis/><Tooltip/><Line type="monotone" dataKey="million_gallons" stroke="#FDBA74" name="Million gallons"/></LineChart></ResponsiveContainer></div> : <Empty>No annual million-gallon consumption values are available.</Empty>}</section>
      <section className="analysis-panel"><h2>Monthly consumption Â· source units</h2>{monthly.length ? <div className="analysis-table-wrap"><table><thead><tr><th>MONTH</th><th>MILLION GALLONS</th><th>MILLION LITRES</th><th>ROWS</th></tr></thead><tbody>{monthly.map((row) => <tr key={row.measurement_month}><td>{row.measurement_month}</td><td>{fmt(row.million_gallons)}</td><td>{fmt(row.million_litres)}</td><td>{row.observations}</td></tr>)}</tbody></table></div> : <Empty>{data['monthly-trends']?.message || 'No monthly consumption periods are available.'}</Empty>}</section>
      <section className="analysis-panel"><h2>WUE by location Â· L/kWh</h2>{wue.length ? <div className="analysis-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={wue}><CartesianGrid stroke="#ffffff" strokeOpacity={.07}/><XAxis dataKey="place_name" hide/><YAxis stroke="#9aabb4"/><Tooltip/><Bar dataKey="average_wue_l_per_kwh" fill="#FF6B24" name="Average WUE (L/kWh)"/></BarChart></ResponsiveContainer></div> : <Empty>{data.wue?.message || 'No WUE observations are available.'}</Empty>}</section>
      <section className="analysis-panel analysis-wide"><h2>Country consumption comparison Â· units kept separate</h2>{countries.length ? <div className="analysis-table-wrap"><table><thead><tr><th>COUNTRY</th><th>MILLION GALLONS</th><th>MILLION LITRES</th><th>OBSERVATIONS</th></tr></thead><tbody>{countries.map((row) => <tr key={row.country}><td>{row.country}</td><td>{fmt(row.million_gallons)}</td><td>{fmt(row.million_litres)}</td><td>{row.observations}</td></tr>)}</tbody></table></div> : <Empty>{data['country-comparison']?.message || 'No country-linked consumption values are available.'}</Empty>}<p className="analysis-note">These totals are grouped by source country code. Missing country values are excluded; the two volume units are not combined.</p></section>
    </div>
  </div>
}
