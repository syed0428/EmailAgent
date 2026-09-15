import { useState, useEffect } from 'react'
import {
  uploadResume,
  deleteResume,
  matchResumeAndJob,
  optimizeResume,
  generateApplicationEmail,
  sendApplicationEmail,
  getGoogleAuthStatus,
  getGoogleLoginUrl,
} from '../api'

const DEMO_USER_ID = '00000000-0000-0000-0000-000000000001'

export default function JobAssistant() {
  const [step, setStep] = useState(1)

  // Gmail OAuth Connection State
  const [gmailStatus, setGmailStatus] = useState({ connected: false, email: '' })
  const [checkingAuth, setCheckingAuth] = useState(false)

  // Step 1 State: Resume & Job Details
  const [resumeFile, setResumeFile] = useState(null)
  const [uploadedResume, setUploadedResume] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [form, setForm] = useState({
    company_name: '',
    job_title: '',
    recipient_email: '',
    job_description: '',
    user_profile: '',
    additional_instructions: '',
  })

  // Step 2 & 3 State: Match Analysis & ATS Suggestions
  const [loadingMatch, setLoadingMatch] = useState(false)
  const [matchData, setMatchData] = useState(null)
  const [suggestions, setSuggestions] = useState([])

  // Step 4 State: Optimized Resume & Email Draft
  const [optimizing, setOptimizing] = useState(false)
  const [optimizedResume, setOptimizedResume] = useState('')
  const [optimizedResumeFilename, setOptimizedResumeFilename] = useState('')
  const [antiFabricationInfo, setAntiFabricationInfo] = useState(null)
  const [emailDraft, setEmailDraft] = useState(null)

  // Step 5 State: Final Review, Modal & Gmail Sending
  const [finalRecipient, setFinalRecipient] = useState('')
  const [finalSubject, setFinalSubject] = useState('')
  const [finalBody, setFinalBody] = useState('')
  const [showConfirmModal, setShowConfirmModal] = useState(false)
  const [sending, setSending] = useState(false)
  const [sendResult, setSendResult] = useState(null)

  const [error, setError] = useState(null)

  // Check Gmail OAuth connection on mount
  useEffect(() => {
    fetchGmailAuthStatus()
  }, [])

  const fetchGmailAuthStatus = async () => {
    setCheckingAuth(true)
    try {
      const res = await getGoogleAuthStatus()
      setGmailStatus({
        connected: res.data.connected,
        email: res.data.email || '',
      })
    } catch (err) {
      setGmailStatus({ connected: false, email: '' })
    } finally {
      setCheckingAuth(false)
    }
  }

  const handleConnectGmail = async () => {
    try {
      const res = await getGoogleLoginUrl()
      if (res.data.url) {
        window.location.href = res.data.url
      }
    } catch (err) {
      setError('Could not initialize Google OAuth login.')
    }
  }

  const handleFormChange = (key) => (e) =>
    setForm((f) => ({ ...f, [key]: e.target.value }))

  // 1. Upload Resume
  const handleFileUpload = async (e) => {
    const file = e.target.files[0]
    if (!file) return

    setUploading(true)
    setError(null)
    const formData = new FormData()
    formData.append('file', file)
    formData.append('user_id', DEMO_USER_ID)

    try {
      const res = await uploadResume(formData)
      setUploadedResume(res.data)
      setResumeFile(file)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setUploading(false)
    }
  }

  const handleDeleteResume = async () => {
    if (!uploadedResume) return
    try {
      await deleteResume(uploadedResume.resume_id)
      setUploadedResume(null)
      setResumeFile(null)
    } catch (err) {
      setError('Could not delete resume file.')
    }
  }

  // 2. Match Resume & Job Description
  const handleAnalyzeMatch = async () => {
    if (!uploadedResume || !form.job_description) {
      setError('Please upload a resume and provide a Job Description.')
      return
    }

    setLoadingMatch(true)
    setError(null)

    try {
      const res = await matchResumeAndJob({
        user_id: DEMO_USER_ID,
        resume_id: uploadedResume.resume_id,
        job_description: form.job_description,
        company_name: form.company_name,
        job_title: form.job_title,
        user_profile: form.user_profile,
      })

      setMatchData(res.data)
      setSuggestions(res.data.ats_suggestions || [])
      setStep(2)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setLoadingMatch(false)
    }
  }

  // Toggle Suggestion Approval
  const toggleSuggestion = (id) => {
    setSuggestions((prev) =>
      prev.map((s) =>
        s.id === id ? { ...s, approved_by_user: !s.approved_by_user } : s
      )
    )
  }

  // 3. Optimize Resume & Generate Email
  const handleOptimizeAndGenerate = async () => {
    if (!matchData?.job_application_id) return

    setOptimizing(true)
    setError(null)

    try {
      // Step A: Optimize Resume
      const optRes = await optimizeResume({
        job_application_id: matchData.job_application_id,
        approved_suggestions: suggestions,
      })

      setOptimizedResume(optRes.data.optimized_resume_text)
      setOptimizedResumeFilename(optRes.data.optimized_resume_filename || '')
      setAntiFabricationInfo({
        valid: optRes.data.anti_fabrication_valid,
        violations: optRes.data.anti_fabrication_violations,
      })

      // Step B: Generate Recruiter Cover Email
      const emailRes = await generateApplicationEmail({
        user_id: DEMO_USER_ID,
        job_application_id: matchData.job_application_id,
        job_description: form.job_description,
        recipient_email: form.recipient_email || 'recruiter@company.com',
        company_name: form.company_name,
        job_title: form.job_title,
        additional_instructions: form.additional_instructions,
        user_profile: form.user_profile,
      })

      setEmailDraft(emailRes.data)
      setFinalRecipient(emailRes.data.recipient || form.recipient_email || '')
      setFinalSubject(emailRes.data.subject || `Application for ${form.job_title || 'Position'}`)
      setFinalBody(emailRes.data.body || '')
      setStep(4)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setOptimizing(false)
    }
  }

  // Move from Step 4 to Step 5 (Final Review)
  const handleProceedToFinalReview = () => {
    fetchGmailAuthStatus()
    setStep(5)
  }

  // 4. Confirm & Send via Gmail API (Phase 9)
  const handleExecuteSend = async () => {
    if (!matchData?.job_application_id) return

    setShowConfirmModal(false)
    setSending(true)
    setError(null)

    try {
      const res = await sendApplicationEmail(matchData.job_application_id, {
        user_id: DEMO_USER_ID,
        recipient_email: finalRecipient,
        subject: finalSubject,
        body: finalBody,
      })

      setSendResult(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || err.message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header */}
      <div>
        <h1 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '4px' }}>
          Job Application Assistant & Gmail Pipeline
        </h1>
        <p style={{ color: 'var(--text-muted)', fontSize: '13px' }}>
          Phase 9: Upload resume ➔ Truthful match analysis ➔ ATS optimization ➔ Recruiter email ➔ Live Gmail API transmission.
        </p>
      </div>

      {/* Step Indicator Wizard */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
        {[
          { num: 1, label: '1. Resume & JD' },
          { num: 2, label: '2. Match Analysis' },
          { num: 3, label: '3. ATS Optimization' },
          { num: 4, label: '4. Resume & Email' },
          { num: 5, label: '5. Final Review & Send' },
        ].map((s) => (
          <button
            key={s.num}
            onClick={() => s.num < step && setStep(s.num)}
            disabled={s.num > step || sendResult !== null}
            className="btn"
            style={{
              padding: '6px 14px',
              fontSize: '12px',
              fontWeight: step === s.num ? 700 : 500,
              background:
                step === s.num
                  ? 'var(--accent)'
                  : step > s.num
                  ? 'rgba(16, 185, 129, 0.15)'
                  : 'var(--bg-card)',
              color:
                step === s.num
                  ? '#fff'
                  : step > s.num
                  ? 'var(--success)'
                  : 'var(--text-muted)',
              border: '1px solid var(--border-color)',
            }}
          >
            {s.label}
          </button>
        ))}
      </div>

      {error && (
        <div
          style={{
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.3)',
            borderRadius: 'var(--radius-sm)',
            padding: '12px 16px',
            color: 'var(--danger)',
            fontSize: '13px',
          }}
        >
          ❌ {error}
        </div>
      )}

      {/* ── STEP 1: Upload Resume & Input Job Description ───────────────────── */}
      {step === 1 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          {/* Left Column: Upload Resume */}
          <div className="card">
            <div className="card-title">📄 1. Upload Resume (PDF / DOCX)</div>
            <p style={{ color: 'var(--text-muted)', fontSize: '12.5px', marginBottom: '16px' }}>
              Upload your resume for structured entity extraction and anti-fabrication verification. Max 5MB.
            </p>

            {!uploadedResume ? (
              <div
                style={{
                  border: '2px dashed var(--border-color)',
                  borderRadius: 'var(--radius-md)',
                  padding: '36px',
                  textAlign: 'center',
                  background: 'rgba(255,255,255,0.02)',
                }}
              >
                <div style={{ fontSize: '32px', marginBottom: '8px' }}>📤</div>
                <div style={{ fontSize: '14px', fontWeight: 600, marginBottom: '4px' }}>
                  {uploading ? 'Processing Resume…' : 'Drop your resume file here'}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: '12px', marginBottom: '16px' }}>
                  Supports PDF (.pdf) and Word (.docx)
                </div>
                <input
                  type="file"
                  id="resume-input"
                  accept=".pdf,.docx"
                  onChange={handleFileUpload}
                  style={{ display: 'none' }}
                  disabled={uploading}
                />
                <label htmlFor="resume-input" className="btn btn-primary" style={{ cursor: 'pointer' }}>
                  {uploading ? 'Parsing File…' : 'Choose File'}
                </label>
              </div>
            ) : (
              <div
                style={{
                  background: 'rgba(16,185,129,0.08)',
                  border: '1px solid rgba(16,185,129,0.3)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '16px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--success)' }}>
                      ✓ {uploadedResume.filename}
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Format: {uploadedResume.file_type.toUpperCase()} | Extracted successfully
                    </div>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={handleDeleteResume} style={{ color: 'var(--danger)' }}>
                    🗑 Remove
                  </button>
                </div>

                {uploadedResume.structured_data?.skills?.length > 0 && (
                  <div style={{ marginTop: '12px' }}>
                    <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '6px', color: 'var(--text-muted)' }}>
                      Extracted Technical Skills:
                    </div>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {uploadedResume.structured_data.skills.slice(0, 10).map((sk, idx) => (
                        <span
                          key={idx}
                          style={{
                            background: 'var(--bg-muted)',
                            fontSize: '11px',
                            padding: '3px 8px',
                            borderRadius: '12px',
                          }}
                        >
                          {sk}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Right Column: Job Description & Profile */}
          <div className="card">
            <div className="card-title">📝 2. Job Description & Context</div>

            <div className="form-group">
              <label className="form-label">Job Description *</label>
              <textarea
                className="textarea"
                rows={5}
                placeholder="Paste the full job description text here…"
                value={form.job_description}
                onChange={handleFormChange('job_description')}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div className="form-group">
                <label className="form-label">Company Name</label>
                <input
                  className="input"
                  placeholder="e.g. Acme Inc"
                  value={form.company_name}
                  onChange={handleFormChange('company_name')}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Job Title</label>
                <input
                  className="input"
                  placeholder="e.g. Senior AI Engineer"
                  value={form.job_title}
                  onChange={handleFormChange('job_title')}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Recipient Email</label>
              <input
                className="input"
                type="email"
                placeholder="recruiter@company.com"
                value={form.recipient_email}
                onChange={handleFormChange('recipient_email')}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Your Background / Additional Profile (Optional)</label>
              <textarea
                className="textarea"
                rows={2}
                placeholder="Additional experience, preferred roles… (Strictly verified against anti-fabrication rules)"
                value={form.user_profile}
                onChange={handleFormChange('user_profile')}
              />
            </div>

            <button
              className="btn btn-primary"
              onClick={handleAnalyzeMatch}
              disabled={loadingMatch || !uploadedResume || !form.job_description}
              style={{ width: '100%', marginTop: '8px' }}
            >
              {loadingMatch ? '⟳ Analyzing Match…' : '🔍 Analyze Resume ↔ Job Match'}
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 2: Explainable Match Analysis ─────────────────────────────── */}
      {step === 2 && matchData && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div
            className="card"
            style={{
              display: 'flex',
              alignItems: 'center',
              justify: 'space-between',
              background: 'linear-gradient(135deg, rgba(99,102,241,0.1) 0%, rgba(16,185,129,0.1) 100%)',
              border: '1px solid rgba(99,102,241,0.3)',
            }}
          >
            <div>
              <div style={{ fontSize: '13px', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-muted)' }}>
                Overall Match Score
              </div>
              <div style={{ fontSize: '42px', fontWeight: 800, color: 'var(--accent)' }}>
                {matchData.overall_score}%
              </div>
              <p style={{ color: 'var(--text-muted)', fontSize: '12.5px', maxWidth: '600px', marginTop: '4px' }}>
                {matchData.score_breakdown?.explanation}
              </p>
            </div>
            <button className="btn btn-primary" onClick={() => setStep(3)}>
              Proceed to ATS Optimization ➔
            </button>
          </div>

          <div className="card">
            <div className="card-title">📊 Explainable Score Factor Breakdown</div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginTop: '12px' }}>
              <div style={{ padding: '12px', background: 'var(--bg-muted)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Required Skills (50%)</div>
                <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '2px' }}>
                  {matchData.score_breakdown?.required_skills_score} / 50 pts
                </div>
              </div>
              <div style={{ padding: '12px', background: 'var(--bg-muted)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Preferred Skills (20%)</div>
                <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '2px' }}>
                  {matchData.score_breakdown?.preferred_skills_score} / 20 pts
                </div>
              </div>
              <div style={{ padding: '12px', background: 'var(--bg-muted)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Keyword Coverage (20%)</div>
                <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '2px' }}>
                  {matchData.score_breakdown?.keyword_coverage_score} / 20 pts
                </div>
              </div>
              <div style={{ padding: '12px', background: 'var(--bg-muted)', borderRadius: 'var(--radius-sm)' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Experience Alignment (10%)</div>
                <div style={{ fontSize: '20px', fontWeight: 700, marginTop: '2px' }}>
                  {matchData.score_breakdown?.experience_alignment_score} / 10 pts
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            <div className="card">
              <div className="card-title" style={{ color: 'var(--success)' }}>
                ✓ Matched Qualifications & Skills
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '8px' }}>
                <div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                    Required Skills Matched:
                  </div>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {matchData.match_analysis?.required_skills?.matched?.map((s, idx) => (
                      <span key={idx} style={{ background: 'rgba(16,185,129,0.15)', color: 'var(--success)', fontSize: '12px', padding: '4px 10px', borderRadius: '14px', fontWeight: 600 }}>
                        {s}
                      </span>
                    )) || <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>None</span>}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                    Preferred Skills Matched:
                  </div>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {matchData.match_analysis?.preferred_skills?.matched?.map((s, idx) => (
                      <span key={idx} style={{ background: 'rgba(59,130,246,0.15)', color: '#3b82f6', fontSize: '12px', padding: '4px 10px', borderRadius: '14px' }}>
                        {s}
                      </span>
                    )) || <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>None</span>}
                  </div>
                </div>
              </div>
            </div>

            <div className="card">
              <div className="card-title" style={{ color: 'var(--danger)' }}>
                ⚠ Missing Qualifications & Gaps
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginTop: '8px' }}>
                <div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                    Missing Required Skills (High Impact):
                  </div>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {matchData.match_analysis?.required_skills?.missing?.map((s, idx) => (
                      <span key={idx} style={{ background: 'rgba(239,68,68,0.15)', color: 'var(--danger)', fontSize: '12px', padding: '4px 10px', borderRadius: '14px', fontWeight: 600 }}>
                        {s}
                      </span>
                    )) || <span style={{ fontSize: '12px', color: 'var(--success)' }}>None — All required skills matched!</span>}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px' }}>
                    Missing Preferred Skills / Keywords:
                  </div>
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {matchData.match_analysis?.preferred_skills?.missing?.map((s, idx) => (
                      <span key={idx} style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)', fontSize: '12px', padding: '4px 10px', borderRadius: '14px' }}>
                        {s}
                      </span>
                    )) || <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>None</span>}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── STEP 3: ATS Optimization Review (Truthful Anti-Fabrication) ───────── */}
      {step === 3 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div
            className="card"
            style={{
              background: 'rgba(59,130,246,0.08)',
              border: '1px solid rgba(59,130,246,0.3)',
              padding: '16px 20px',
            }}
          >
            <div style={{ fontWeight: 600, fontSize: '14px', color: '#3b82f6' }}>
              🛡 Backend-Enforced Anti-Fabrication Guardrail Active
            </div>
            <p style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginTop: '4px' }}>
              All suggestions below improve wording, action verbs, and formatting without inventing new metrics, percentages, skills, or technologies.
            </p>
          </div>

          <div className="card">
            <div className="card-title">✨ ATS Improvement Suggestions — Review & Approve</div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '12px' }}>
              {suggestions.map((sug) => (
                <div
                  key={sug.id}
                  style={{
                    border: sug.approved_by_user
                      ? '1px solid var(--success)'
                      : '1px solid var(--border-color)',
                    background: sug.approved_by_user
                      ? 'rgba(16,185,129,0.04)'
                      : 'var(--bg-card)',
                    borderRadius: 'var(--radius-md)',
                    padding: '16px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
                    <span
                      style={{
                        background: 'var(--bg-muted)',
                        fontSize: '11px',
                        textTransform: 'uppercase',
                        fontWeight: 700,
                        padding: '3px 8px',
                        borderRadius: '4px',
                        color: 'var(--text-muted)',
                      }}
                    >
                      {sug.category}
                    </span>

                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', fontWeight: 600, color: sug.approved_by_user ? 'var(--success)' : 'var(--text-primary)' }}>
                      <input
                        type="checkbox"
                        checked={!!sug.approved_by_user}
                        onChange={() => toggleSuggestion(sug.id)}
                      />
                      {sug.approved_by_user ? '✓ Approved' : 'Approve Suggestion'}
                    </label>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '13px' }}>
                    <div style={{ background: 'rgba(239,68,68,0.06)', padding: '10px 12px', borderRadius: 'var(--radius-sm)' }}>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--danger)', marginBottom: '4px' }}>
                        BEFORE (Current Wording)
                      </div>
                      <div style={{ color: 'var(--text-secondary)' }}>"{sug.before}"</div>
                    </div>

                    <div style={{ background: 'rgba(16,185,129,0.06)', padding: '10px 12px', borderRadius: 'var(--radius-sm)' }}>
                      <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--success)', marginBottom: '4px' }}>
                        SUGGESTED (ATS Improved Wording)
                      </div>
                      <div style={{ color: 'var(--text-primary)', fontWeight: 500 }}>"{sug.suggested}"</div>
                    </div>
                  </div>

                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px', fontStyle: 'italic' }}>
                    💡 Reason: {sug.reason}
                  </div>
                </div>
              ))}
            </div>

            <button
              className="btn btn-primary"
              onClick={handleOptimizeAndGenerate}
              disabled={optimizing}
              style={{ marginTop: '20px' }}
            >
              {optimizing ? '⟳ Generating Resume & Cover Email…' : 'Apply Approved Suggestions & Generate Documents ➔'}
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 4: Resume & Email Preview ───────────────────────────────────── */}
      {step === 4 && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          {/* Left Column: Optimized Resume Preview */}
          <div className="card">
            <div className="card-title">📄 Optimized ATS Resume Document</div>
            {antiFabricationInfo?.valid && (
              <div style={{ fontSize: '12px', color: 'var(--success)', marginBottom: '8px', fontWeight: 600 }}>
                ✓ Whole-Resume Anti-Fabrication Safeguard Passed
              </div>
            )}
            <textarea
              className="textarea"
              rows={18}
              readOnly
              value={optimizedResume}
              style={{ fontFamily: 'monospace', fontSize: '12.5px' }}
            />
            <div style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
              <button
                className="btn btn-ghost"
                onClick={() => navigator.clipboard.writeText(optimizedResume)}
              >
                📋 Copy Resume Text
              </button>
              {matchData?.job_application_id && (
                <a
                  href={`/api/jobs/${matchData.job_application_id}/resume/download`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary"
                  style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
                >
                  📄 Download / Preview Generated PDF
                </a>
              )}
            </div>
          </div>

          {/* Right Column: Recruiter Cover Email Draft */}
          <div className="card">
            <div className="card-title">📧 Recruiter Application Email Draft</div>

            {emailDraft && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div>
                  <div className="form-label">To:</div>
                  <input
                    className="input"
                    value={finalRecipient}
                    onChange={(e) => setFinalRecipient(e.target.value)}
                  />
                </div>
                <div>
                  <div className="form-label">Subject:</div>
                  <input
                    className="input"
                    value={finalSubject}
                    onChange={(e) => setFinalSubject(e.target.value)}
                  />
                </div>
                <div>
                  <div className="form-label">Email Body (Edit before sending):</div>
                  <textarea
                    className="textarea"
                    rows={8}
                    value={finalBody}
                    onChange={(e) => setFinalBody(e.target.value)}
                  />
                </div>

                <div
                  style={{
                    background: 'rgba(16,185,129,0.08)',
                    border: '1px solid rgba(16,185,129,0.3)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '10px 14px',
                    fontSize: '12.5px',
                    color: 'var(--success)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '8px',
                  }}
                >
                  <span>📎 Attached File: <strong>{optimizedResumeFilename || uploadedResume?.filename || 'Optimized_Resume.pdf'}</strong></span>
                  {matchData?.job_application_id && (
                    <a
                      href={`/api/jobs/${matchData.job_application_id}/resume/download`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-secondary btn-sm"
                      style={{ textDecoration: 'none', fontSize: '11.5px', padding: '4px 10px' }}
                    >
                      📥 View PDF
                    </a>
                  )}
                </div>

                <button className="btn btn-primary" onClick={handleProceedToFinalReview}>
                  Proceed to Final Review & Gmail Send ➔
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── STEP 5: Phase 9 Final Review & Gmail Transmission ───────────────── */}
      {step === 5 && (
        <div style={{ maxWidth: '800px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Post-Send Success Screen */}
          {sendResult ? (
            <div className="card" style={{ padding: '32px', textAlign: 'center' }}>
              <div style={{ fontSize: '48px', marginBottom: '12px' }}>🎉</div>
              <h2 style={{ fontSize: '22px', fontWeight: 800, marginBottom: '6px', color: 'var(--success)' }}>
                Application Sent Successfully!
              </h2>
              <p style={{ color: 'var(--text-muted)', fontSize: '13px', marginBottom: '24px' }}>
                Your application and ATS resume were delivered via the Gmail API.
              </p>

              <div
                style={{
                  background: 'var(--bg-muted)',
                  borderRadius: 'var(--radius-md)',
                  padding: '20px',
                  textAlign: 'left',
                  fontSize: '13px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '10px',
                  marginBottom: '24px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Status:</span>
                  <span style={{ fontWeight: 700, color: 'var(--success)' }}>SENT (Gmail API Confirmed)</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Recipient:</span>
                  <span style={{ fontWeight: 600 }}>{sendResult.recipient}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Subject:</span>
                  <span style={{ fontWeight: 600 }}>{sendResult.subject}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Sender Account:</span>
                  <span style={{ fontWeight: 600 }}>{sendResult.gmail_account}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Gmail Message ID:</span>
                  <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{sendResult.gmail_message_id}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Attachment Sent:</span>
                  <span style={{ fontWeight: 600, color: 'var(--success)' }}>📎 {sendResult.attachment_name || uploadedResume?.filename}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--text-muted)' }}>Sent At:</span>
                  <span>{new Date(sendResult.sent_at).toLocaleString()}</span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
                <button className="btn" disabled style={{ background: 'var(--bg-muted)', color: 'var(--text-muted)', cursor: 'not-allowed' }}>
                  ✓ Application Sent (Sending Disabled to Prevent Duplicates)
                </button>
                <button
                  className="btn btn-primary"
                  onClick={() => {
                    setSendResult(null)
                    setStep(1)
                  }}
                >
                  + Start Another Application
                </button>
              </div>
            </div>
          ) : (
            /* Pre-Send Final Review Screen */
            <div className="card" style={{ padding: '24px' }}>
              <div className="card-title" style={{ fontSize: '18px', marginBottom: '16px' }}>
                📧 Phase 9: Final Review & Gmail Transmission
              </div>

              {/* Gmail Account Status Banner */}
              {!gmailStatus.connected ? (
                <div
                  style={{
                    background: 'rgba(239,68,68,0.08)',
                    border: '1px solid rgba(239,68,68,0.3)',
                    borderRadius: 'var(--radius-md)',
                    padding: '16px',
                    marginBottom: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    justify: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, color: 'var(--danger)', fontSize: '14px' }}>
                      ⚠️ No Gmail Account Connected
                    </div>
                    <div style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      You must connect your Gmail account via OAuth before sending live applications.
                    </div>
                  </div>
                  <button className="btn btn-primary" onClick={handleConnectGmail}>
                    Connect Gmail Account ➔
                  </button>
                </div>
              ) : (
                <div
                  style={{
                    background: 'rgba(16,185,129,0.08)',
                    border: '1px solid rgba(16,185,129,0.3)',
                    borderRadius: 'var(--radius-md)',
                    padding: '12px 16px',
                    marginBottom: '20px',
                    display: 'flex',
                    alignItems: 'center',
                    justify: 'space-between',
                  }}
                >
                  <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--success)' }}>
                    ✓ Sending from connected Gmail: <strong>{gmailStatus.email}</strong>
                  </div>
                  <span style={{ fontSize: '11px', background: 'rgba(16,185,129,0.2)', padding: '2px 8px', borderRadius: '10px', color: 'var(--success)', fontWeight: 700 }}>
                    OAuth Active
                  </span>
                </div>
              )}

              {/* Review Details Form */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div className="form-group">
                  <label className="form-label">Recipient Email *</label>
                  <input
                    className="input"
                    type="email"
                    value={finalRecipient}
                    onChange={(e) => setFinalRecipient(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Subject Line *</label>
                  <input
                    className="input"
                    value={finalSubject}
                    onChange={(e) => setFinalSubject(e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Cover Email Body *</label>
                  <textarea
                    className="textarea"
                    rows={8}
                    value={finalBody}
                    onChange={(e) => setFinalBody(e.target.value)}
                  />
                </div>

                {/* Resume Attachment Badge */}
                <div
                  style={{
                    background: 'var(--bg-muted)',
                    border: '1px solid var(--border-color)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '12px 16px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 600 }}>
                      📎 Attachment: {optimizedResumeFilename || uploadedResume?.filename || 'Optimized_Resume.pdf'}
                    </div>
                    <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
                      Format: PDF | Status: Verified & Approved
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    {matchData?.job_application_id && (
                      <a
                        href={`/api/jobs/${matchData.job_application_id}/resume/download`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn-secondary btn-sm"
                        style={{ textDecoration: 'none', fontSize: '11.5px', padding: '4px 10px' }}
                      >
                        📥 View PDF
                      </a>
                    )}
                    <button className="btn btn-ghost btn-sm" onClick={() => setStep(1)}>
                      Change Resume
                    </button>
                  </div>
                </div>

                {/* Explicit Warning Banner */}
                <div
                  style={{
                    background: 'rgba(245,158,11,0.08)',
                    border: '1px solid rgba(245,158,11,0.3)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '12px 16px',
                    fontSize: '12.5px',
                    color: 'var(--warning)',
                  }}
                >
                  ⚠️ <strong>Live Delivery Warning:</strong> Clicking "Confirm & Send Application" will transmit this email and attachment directly from your Gmail account (<strong>{gmailStatus.email || 'Connected Account'}</strong>).
                </div>

                {/* Action Buttons */}
                <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '8px' }}>
                  <button className="btn btn-ghost" onClick={() => setStep(4)}>
                    ✏️ Edit Email
                  </button>
                  <button className="btn btn-ghost" onClick={() => setStep(1)}>
                    🔄 Change Resume
                  </button>
                  <button
                    className="btn btn-primary"
                    disabled={!gmailStatus.connected || sending || !finalRecipient || !finalBody}
                    onClick={() => setShowConfirmModal(true)}
                    style={{ marginLeft: 'auto', background: 'var(--accent)' }}
                  >
                    {sending ? '⟳ Transmitting via Gmail…' : '🚀 Confirm & Send Application'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── EXPLICIT USER CONFIRMATION MODAL ─────────────────────────────────── */}
      {showConfirmModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.7)',
            display: 'flex',
            alignItems: 'center',
            justify: 'center',
            zIndex: 1000,
            backdropFilter: 'blur(4px)',
          }}
        >
          <div
            className="card"
            style={{
              width: '90%',
              maxWidth: '520px',
              padding: '28px',
              border: '1px solid var(--accent)',
              boxShadow: '0 20px 40px rgba(0,0,0,0.5)',
            }}
          >
            <div style={{ fontSize: '18px', fontWeight: 800, marginBottom: '12px', color: 'var(--text-primary)' }}>
              🚀 Confirm Gmail Application Delivery
            </div>

            <p style={{ fontSize: '13.5px', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: '20px' }}>
              You are about to send this job application to <strong>{finalRecipient}</strong> from your connected Gmail account <strong>{gmailStatus.email}</strong> with <strong>{uploadedResume?.filename || 'Optimized_Resume.pdf'}</strong> attached.
            </p>

            <div style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', padding: '10px 14px', borderRadius: '6px', fontSize: '12px', color: 'var(--danger)', marginBottom: '20px' }}>
              This action triggers real live email delivery via Google Gmail API. Send now?
            </div>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button className="btn btn-ghost" onClick={() => setShowConfirmModal(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" onClick={handleExecuteSend} style={{ background: 'var(--success)' }}>
                Send Now 🚀
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
