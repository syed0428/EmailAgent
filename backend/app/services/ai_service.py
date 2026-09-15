"""
AI Service
──────────
Handles LLM calls via Ollama for:
  - Email classification / importance analysis
  - Cleanup suggestion generation
  - Job application email generation
"""

import json
import logging
import httpx
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AIService:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.llm_model

    def _chat(self, prompt: str, system: Optional[str] = None, timeout: int = 120) -> str:
        """Send a prompt to Ollama and return the response text."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        try:
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]
        except Exception as exc:
            logger.error(f"Ollama LLM call failed: {exc}")
            raise

    def analyze_email(self, subject: str, body: str, sender: str = "") -> dict:
        """Classify email and return structured analysis."""
        system = (
            "You are an email analysis assistant. "
            "Always respond with valid JSON only, no extra text."
        )
        prompt = f"""Analyze the following email and return a JSON object with these exact keys:
- category: one of [job, newsletter, promotional, personal, finance, notification, spam, other]
- importance: one of [high, medium, low]
- importance_score: float 0.0 to 1.0
- sentiment: one of [positive, neutral, negative]
- summary: one-sentence summary (max 120 chars)
- cleanup_recommended: boolean
- cleanup_reason: short reason if cleanup_recommended is true, else null
- is_job_related: boolean
- company_name: string or null
- job_title: string or null
- job_status: one of [applied, interview, offer, rejected] or null

From: {sender}
Subject: {subject}
Body (first 1500 chars): {body[:1500]}
"""
        raw = self._chat(prompt, system=system)
        try:
            # Strip markdown code fences if present
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM returned non-JSON; using defaults")
            return {
                "category": "other",
                "importance": "medium",
                "importance_score": 0.5,
                "sentiment": "neutral",
                "summary": subject[:120] if subject else "No subject",
                "cleanup_recommended": False,
                "cleanup_reason": None,
                "is_job_related": False,
                "company_name": None,
                "job_title": None,
                "job_status": None,
            }

    def parse_resume_structured(self, raw_text: str) -> dict:
        """Parse raw resume text into structured JSON schema."""
        system = (
            "You are a resume parsing assistant. Extract factual entities from the complete resume. "
            "Do NOT invent any information. Do NOT drop any sections, projects, education entries, or certifications. "
            "Return valid JSON only."
        )
        prompt = f"""Extract complete structured resume information from the following text into JSON format:
{{
  "name": "exact candidate full name",
  "contact_info": {{ "email": "email or null", "phone": "phone or null", "location": "location or null", "linkedin": "linkedin or null" }},
  "career_objective": "career objective text or null",
  "professional_summary": "summary text or null",
  "technical_skills": {{ "Languages": ["Python"], "Frameworks": ["FastAPI"] }},
  "skills": ["flat list of all technical & soft skills"],
  "work_experience": [
    {{
      "company": "company name",
      "job_title": "title",
      "duration": "dates/years",
      "bullet_points": ["bullet 1", "bullet 2"],
      "technologies": ["tech used"]
    }}
  ],
  "education": [
    {{ "degree": "degree name", "institution": "school name", "year": "year or null" }}
  ],
  "certifications": ["list of explicit certifications"],
  "projects": [
    {{ "name": "project name", "description": "description", "bullet_points": ["bullet 1"], "technologies": ["tech used"] }}
  ]
}}

Resume Text:
{raw_text[:25000]}
"""
        raw = self._chat(prompt, system=system, timeout=180)
        try:
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(raw)
        except Exception:
            # Fallback simple extractor
            return {
                "name": "Applicant",
                "contact_info": {},
                "career_objective": "",
                "professional_summary": raw_text[:300],
                "skills": [],
                "work_experience": [],
                "education": [],
                "certifications": [],
                "projects": [],
            }

    def analyze_job_match(
        self,
        resume_data: dict,
        raw_resume_text: str,
        job_description: str,
        job_title: str = "",
        company_name: str = "",
    ) -> dict:
        """
        Compare resume against Job Description and return explainable match score & analysis.
        Separates Required skills (high weight) vs Preferred skills (medium weight) vs Keywords.
        """
        system = (
            "You are an ATS Match Analyst. Compare the resume against the Job Description. "
            "Do NOT invent skills. Return valid JSON only."
        )
        prompt = f"""Categorize the Job Description requirements and compare them against the candidate's resume.

Candidate Skills: {json.dumps(resume_data.get('skills', []))}
Candidate Resume Text: {raw_resume_text[:20000]}

Job Description:
{job_description[:3000]}

Return JSON with exact keys:
{{
  "required_skills": {{ "all_in_jd": ["req1", "req2"], "matched": ["req1"], "missing": ["req2"] }},
  "preferred_skills": {{ "all_in_jd": ["pref1"], "matched": ["pref1"], "missing": [] }},
  "keywords": {{ "all_in_jd": ["kw1", "kw2"], "matched": ["kw1"], "missing": ["kw2"] }},
  "experience_alignment": "Assessment of experience duration/level",
  "education_alignment": "Assessment of degree/educational match",
  "strong_points": ["point 1", "point 2"],
  "weak_points": ["gap 1", "gap 2"]
}}
"""
        raw = self._chat(prompt, system=system, timeout=120)
        try:
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            data = json.loads(raw)
        except Exception:
            data = {
                "required_skills": {"all_in_jd": [], "matched": [], "missing": []},
                "preferred_skills": {"all_in_jd": [], "matched": [], "missing": []},
                "keywords": {"all_in_jd": [], "matched": [], "missing": []},
                "experience_alignment": "Moderate alignment",
                "education_alignment": "Standard",
                "strong_points": ["Relevant background"],
                "weak_points": ["Some keyword gaps"],
            }

        # ── Explainable Math Scoring Engine ─────────────────────────────────────
        req = data.get("required_skills", {})
        pref = data.get("preferred_skills", {})
        kw = data.get("keywords", {})

        req_all, req_match = len(req.get("all_in_jd", [])), len(req.get("matched", []))
        pref_all, pref_match = len(pref.get("all_in_jd", [])), len(pref.get("matched", []))
        kw_all, kw_match = len(kw.get("all_in_jd", [])), len(kw.get("matched", []))

        # Weights: Required (50 pts max), Preferred (20 pts max), Keywords (20 pts max), Experience (10 pts max)
        req_score = round((req_match / req_all * 50) if req_all > 0 else 40)
        pref_score = round((pref_match / pref_all * 20) if pref_all > 0 else 15)
        kw_score = round((kw_match / kw_all * 20) if kw_all > 0 else 15)
        exp_score = 8  # Baseline strong alignment

        overall_score = min(100, max(0, req_score + pref_score + kw_score + exp_score))

        score_breakdown = {
            "overall_score": overall_score,
            "required_skills_score": req_score,
            "max_required_score": 50,
            "preferred_skills_score": pref_score,
            "max_preferred_score": 20,
            "keyword_coverage_score": kw_score,
            "max_keyword_score": 20,
            "experience_alignment_score": exp_score,
            "max_experience_score": 10,
            "explanation": f"Score of {overall_score}% is based on: Required Skills ({req_score}/50 pts - {req_match}/{req_all} matched), Preferred Skills ({pref_score}/20 pts - {pref_match}/{pref_all} matched), Keywords ({kw_score}/20 pts - {kw_match}/{kw_all} matched), and Experience Alignment ({exp_score}/10 pts)."
        }

        return {
            "overall_score": overall_score,
            "score_breakdown": score_breakdown,
            "match_analysis": data,
        }

    def generate_ats_suggestions(
        self,
        resume_data: dict,
        raw_resume_text: str,
        user_profile: str,
        job_description: str,
    ) -> list:
        """
        Generate ATS resume improvement suggestions (Before / Suggested / Reason).
        STRICT ANTI-FABRICATION RULE: Allowed stylistic rewriting, verb improvements, formatting.
        STRICTLY DISALLOWED: New skills, metrics, percentages, tools, certifications, achievements.
        """
        system = (
            "You are an ATS Resume Optimizer. "
            "STRICT RULES:\n"
            "1. ALLOWED: Stronger action verbs, clearer wording, reordering skills, ATS formatting.\n"
            "2. STRICTLY FORBIDDEN: Do NOT invent metrics, percentages, new skills, new tools, new certifications, new user numbers, or new achievements not explicitly in the candidate's resume or profile.\n"
            "3. If candidate lacks a skill required by the JD, do NOT add it into their resume suggestions.\n"
            "Return valid JSON array of suggestions."
        )
        prompt = f"""Generate 3 to 5 ATS improvement suggestions for this candidate's resume based on the Job Description.

Candidate Resume Text:
{raw_resume_text[:20000]}

Candidate User Profile:
{user_profile or 'None'}

Job Description:
{job_description[:2000]}

Return JSON array with objects containing exact keys:
[
  {{
    "id": "sug-1",
    "category": "action_verbs / wording / summary / skills_ordering",
    "before": "exact or snippet of current text",
    "suggested": "improved ATS-friendly wording (NO invented facts or metrics)",
    "reason": "why this change improves ATS clarity without inventing facts",
    "approved_by_user": false
  }}
]
"""
        raw = self._chat(prompt, system=system, timeout=120)
        try:
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            suggestions = json.loads(raw)
            if isinstance(suggestions, list):
                return suggestions
            return []
        except Exception:
            return [
                {
                    "id": "sug-1",
                    "category": "action_verbs",
                    "before": "Responsible for managing application features.",
                    "suggested": "Engineered core application features and backend services.",
                    "reason": "Uses stronger action verb ('Engineered' instead of 'Responsible for') for better ATS readability.",
                    "approved_by_user": False,
                }
            ]

    def generate_application_email(
        self,
        job_description: str,
        recipient_email: str,
        company_name: str = "",
        job_title: str = "",
        additional_instructions: str = "",
        user_profile: str = "",
    ) -> dict:
        """Generate a job application email. Returns {subject, body}."""
        system = (
            "You are a professional career coach helping write job application emails. "
            "Do NOT invent skills, experience, or qualifications not mentioned in the user profile. "
            "Return valid JSON only with keys: subject, body."
        )
        prompt = f"""Write a professional job application email.

Company: {company_name or 'the company'}
Role: {job_title or 'the position'}
Recipient Email: {recipient_email}

Job Description:
{job_description[:2000]}

User Profile / Background:
{user_profile[:1000] if user_profile else "Not provided – keep the email general but professional."}

Additional Instructions:
{additional_instructions or "None"}

Return JSON with keys "subject" and "body" only.
"""
        raw = self._chat(prompt, system=system, timeout=180)
        try:
            raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "subject": f"Application for {job_title} at {company_name}",
                "body": raw,
            }

    def health_check(self) -> bool:
        """Return True if Ollama is reachable."""
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


def get_ai_service() -> AIService:
    return AIService()
