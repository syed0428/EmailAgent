import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

export default api

// ── Health ────────────────────────────────────────────────────────────────────
export const getHealthFull = () => api.get('/health/full')

// ── Auth / Gmail OAuth ────────────────────────────────────────────────────────
export const getGoogleLoginUrl = () => api.get('/auth/google/login')
export const getGoogleAuthStatus = () => api.get('/auth/google/status')

// ── Emails ────────────────────────────────────────────────────────────────────
export const listEmails = (params = {}) => api.get('/emails/', { params })
export const getEmail = (id) => api.get(`/emails/${id}`)
export const ingestEmail = (payload) => api.post('/emails/ingest', payload)
export const syncGmailEmails = (maxResults = 15) =>
  api.post('/emails/sync', null, { params: { max_results: maxResults } })
export const semanticSearch = (q, params = {}) =>
  api.get('/emails/search/semantic', { params: { q, ...params } })
export const getCleanupSuggestions = (accountId) =>
  api.get('/emails/cleanup/suggestions', { params: { account_id: accountId } })
export const approveCleanup = (emailIds) =>
  api.post('/emails/cleanup/approve', { email_ids: emailIds })

// ── Jobs & Resume ─────────────────────────────────────────────────────────────
export const uploadResume = (formData) =>
  api.post('/jobs/resume/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
export const deleteResume = (resumeId) =>
  api.delete(`/jobs/resume/${resumeId}`)
export const matchResumeAndJob = (payload) =>
  api.post('/jobs/match', payload)
export const optimizeResume = (payload) =>
  api.post('/jobs/optimize-resume', payload)
export const generateApplicationEmail = (payload) =>
  api.post('/jobs/generate-email', payload)
export const listApplications = (userId) =>
  api.get('/jobs/', { params: { user_id: userId } })
export const updateApplicationStatus = (id, status) =>
  api.patch(`/jobs/${id}/status`, { status })
export const sendApplicationEmail = (applicationId, payload) =>
  api.post(`/jobs/${applicationId}/send`, payload)
