import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api',
  headers: { Accept: 'application/json' },
  timeout: 15000,
})

export const getHealth = () => api.get('/health').then(({ data }) => data)
export const getDashboard = (datasetId = 'all') => api.get('/dashboard', { params: datasetId && datasetId !== 'all' ? { dataset_id: datasetId } : {} }).then(({ data }) => data)
export const notifyDataChanged = () => window.dispatchEvent(new CustomEvent('pureflow:data-changed'))
export const getDatasets = () => api.get('/datasets').then(({ data }) => data)
export const getDataset = (datasetId) => api.get(`/datasets/${encodeURIComponent(datasetId)}`).then(({ data }) => data)
export const getDatasetPreview = (datasetId) => api.get(`/datasets/${encodeURIComponent(datasetId)}/preview`).then(({ data }) => data)
export const deleteDataset = (datasetId) => api.delete(`/datasets/${encodeURIComponent(datasetId)}`).then(({ data }) => data)
export const uploadDataset = (file, onProgress) => {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/datasets/upload', formData, {
    onUploadProgress: (event) => {
      if (onProgress && event.total) onProgress(Math.round((event.loaded * 100) / event.total))
    },
  }).then(({ data }) => data)
}
export const getWaterAnalytics = () => api.get('/analytics/water').then(({ data }) => data)
export const getClimateAnalytics = () => api.get('/analytics/climate').then(({ data }) => data)
export const getWaterStress = () => api.get('/analytics/water-stress').then(({ data }) => data)
export const getReports = () => api.get('/reports').then(({ data }) => data)
export const runQualityCheck = (datasetId) => api.post(`/datasets/${encodeURIComponent(datasetId)}/quality-check`).then(({ data }) => data)
export const getQualityReport = (datasetId) => api.get(`/datasets/${encodeURIComponent(datasetId)}/quality-report`).then(({ data }) => data)
export const cleanDataset = (datasetId) => api.post(`/datasets/${encodeURIComponent(datasetId)}/clean`).then(({ data }) => data)
export const getCleanedPreview = (datasetId) => api.get(`/datasets/${encodeURIComponent(datasetId)}/cleaned-preview`).then(({ data }) => data)
export const downloadCleanedCsv = (datasetId) => api.get(`/datasets/${encodeURIComponent(datasetId)}/download-cleaned`, { responseType: 'blob' }).then(({ data }) => data)
export const getCleaningHistory = (datasetId) => api.get(`/datasets/${encodeURIComponent(datasetId)}/cleaning-history`).then(({ data }) => data)
export const getTransformCompatibility = () => api.get('/transform/compatibility').then(({ data }) => data.compatibility)
export const standardiseDatasets = (datasetIds) => api.post('/transform/standardise', { dataset_ids: datasetIds }).then(({ data }) => data)
export const integrateDatasets = (payload) => api.post('/transform/integrate', payload).then(({ data }) => data)
export const getTransformHistory = () => api.get('/transform/history').then(({ data }) => data.history)
export const getTransformReport = () => api.get('/transform/report').then(({ data }) => data.report)
export const getDatabaseStatus = () => api.get('/database/status').then(({ data }) => data)
export const getDatabaseTables = () => api.get('/database/tables').then(({ data }) => data)
export const getDatabaseSchema = () => api.get('/database/schema').then(({ data }) => data)
export const getTransformedDatasets = () => api.get('/database/datasets').then(({ data }) => data)
export const loadDatabaseDataset = (datasetId, payload = {}) => api.post(`/database/load/${encodeURIComponent(datasetId)}`, payload).then(({ data }) => data)
export const getDatabaseLoadHistory = () => api.get('/database/load-history').then(({ data }) => data)
export const getDatabaseValidation = () => api.get('/database/validation').then(({ data }) => data)
export const getSqlAnalytics = (name) => api.get(`/analytics/${name}`).then(({ data }) => data)
export const runCustomQuery = (query, limit = 200) => api.post('/analytics/custom-query', { query, limit }).then(({ data }) => data)
export const getReportOverview = (filters = {}) => api.get('/reports/overview', { params: filters }).then(({ data }) => data.overview)
export const getReportInsights = (filters = {}) => api.get('/reports/insights', { params: filters }).then(({ data }) => data)
export const getReportRecommendations = (filters = {}) => api.get('/reports/recommendations', { params: filters }).then(({ data }) => data)
export const getReportSustainability = (filters = {}) => api.get('/reports/sustainability', { params: filters }).then(({ data }) => data)
export const generateReport = (payload) => api.post('/reports/generate', payload).then(({ data }) => data)
export const getReportHistory = () => api.get('/reports/history').then(({ data }) => data.history)
export const downloadReport = (reportId, format) => api.get(`/reports/download/${encodeURIComponent(reportId)}`, { params: { format }, responseType: 'blob' }).then(({ data }) => data)

export default api
