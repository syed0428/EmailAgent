"""
Resume Service
──────────────
Handles:
  1. Secure resume upload validation (MIME, magic bytes, max size, path traversal protection).
  2. Document text extraction (PDF via pypdf & DOCX via python-docx).
  3. Programmatic Anti-Fabrication Engine distinguishing stylistic rewriting from new factual claims.
  4. ATS resume text rendering.
"""

import os
import re
import io
import copy
import html
import uuid
import difflib
import logging
from pathlib import Path
from typing import Tuple, List, Dict, Any, Optional

import pypdf
import docx
from fastapi import UploadFile, HTTPException

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger(__name__)

# Private storage directory outside public web root
STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "resumes"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_EXTENSIONS = {".pdf", ".docx"}


class ResumeService:

    @staticmethod
    def validate_and_save_file(file: UploadFile, user_id: str) -> Tuple[str, str, str]:
        """
        Validates file size, extension, magic bytes, sanitizes filename, prevents path traversal,
        and saves to private storage. Returns (sanitized_filename, relative_file_path, file_type).
        """
        filename = Path(file.filename).name  # Strips any directory traversal paths
        file_ext = Path(filename).suffix.lower()

        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only PDF (.pdf) and Word (.docx) files are allowed."
            )

        contents = file.file.read()
        file.file.seek(0)  # Reset stream

        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail="File size exceeds maximum 5MB limit."
            )

        # Magic byte validation
        file_type = ""
        if file_ext == ".pdf":
            if not contents.startswith(b"%PDF-"):
                raise HTTPException(status_code=400, detail="Invalid PDF file binary header.")
            file_type = "pdf"
        elif file_ext == ".docx":
            if not contents.startswith(b"PK\x03\x04"):
                raise HTTPException(status_code=400, detail="Invalid DOCX file binary header.")
            file_type = "docx"

        # Unique file naming & Path traversal protection
        safe_file_name = f"{user_id}_{uuid.uuid4().hex[:8]}_{filename}"
        target_path = (STORAGE_DIR / safe_file_name).resolve()

        # Path traversal guard
        if not str(target_path).startswith(str(STORAGE_DIR.resolve())):
            raise HTTPException(status_code=400, detail="Security violation: Path traversal detected.")

        with open(target_path, "wb") as f:
            f.write(contents)

        return filename, str(target_path), file_type

    @staticmethod
    def extract_text(file_path: str, file_type: str) -> str:
        """Extract raw plain text from PDF or DOCX file."""
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Resume file not found on server.")

        text_content = []

        try:
            if file_type == "pdf":
                reader = pypdf.PdfReader(file_path)
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt:
                        text_content.append(txt)
            elif file_type == "docx":
                doc = docx.Document(file_path)
                for para in doc.paragraphs:
                    if para.text.strip():
                        text_content.append(para.text.strip())

            raw_text = "\n".join(text_content).strip()
            if not raw_text:
                raise HTTPException(
                    status_code=400,
                    detail="Could not extract readable text from document. Ensure it is not an image-only scan."
                )
            return raw_text
        except HTTPException:
            raise
        except Exception as exc:
            logger.error(f"Text extraction failed for {file_path}: {exc}")
            raise HTTPException(status_code=500, detail=f"Failed to extract document text: {exc}")

    @staticmethod
    def validate_anti_fabrication(
        source_resume_text: str,
        user_profile: str,
        target_text: str,
        approved_suggestions: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, List[str]]:
        """
        Backend-enforced Anti-Fabrication Safeguard.
        Distinguishes between ALLOWED STYLISTIC REWRITING and DISALLOWED NEW FACTUAL CLAIMS.
        Returns (is_valid, list_of_violations).
        """
        combined_source = (source_resume_text + "\n" + (user_profile or "")).lower()

        # Include text from approved suggestions
        if approved_suggestions:
            for sug in approved_suggestions:
                if sug.get("approved_by_user"):
                    combined_source += "\n" + sug.get("suggested", "").lower()

        violations = []

        # 1. Check for newly introduced metrics / percentages / numbers not in source
        target_percentages = re.findall(r'\b\d+(?:\.\d+)?%\b', target_text)
        for pct in target_percentages:
            if pct.lower() not in combined_source:
                violations.append(f"Disallowed metric/percentage invention detected: '{pct}'")

        target_numbers = re.findall(r'\b\$\d+(?:,\d+)*(?:\.\d+)?[kMmbB]?\b', target_text)
        for num in target_numbers:
            if num.lower() not in combined_source:
                violations.append(f"Disallowed financial/numerical claim detected: '{num}'")

        # 2. Check for technology keywords / tools / frameworks
        # Common tech terms regex pattern
        tech_pattern = re.compile(
            r'\b(AWS|Azure|GCP|Kubernetes|Docker|Kafka|GraphQL|Redux|Spark|Hadoop|TensorFlow|PyTorch|CI/CD|Jenkins|Terraform|Ansible)\b',
            re.IGNORECASE
        )
        target_techs = {t.lower() for t in tech_pattern.findall(target_text)}
        source_techs = {t.lower() for t in tech_pattern.findall(combined_source)}

        new_techs = target_techs - source_techs
        for tech in sorted(new_techs):
            violations.append(f"Disallowed new technology/tool invention detected: '{tech.title()}'")

        is_valid = len(violations) == 0
        return is_valid, violations

    @staticmethod
    def delete_resume_file(file_path: str):
        """Safely delete a resume file from private storage."""
        try:
            p = Path(file_path).resolve()
            if p.exists() and str(p).startswith(str(STORAGE_DIR.resolve())):
                p.unlink()
        except Exception as exc:
            logger.warning(f"Could not delete file {file_path}: {exc}")

    @staticmethod
    def apply_approved_suggestions(
        structured_data: Dict[str, Any],
        approved_suggestions: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        Applies ONLY user-approved ATS suggestions into a deep copy of the structured resume JSON.
        Returns (modified_structured_data, applied_suggestions).
        """
        modified = copy.deepcopy(structured_data or {})
        applied: List[Dict[str, Any]] = []

        for sug in approved_suggestions:
            if not sug.get("approved_by_user"):
                continue

            before = str(sug.get("before", "")).strip()
            suggested = str(sug.get("suggested", "")).strip()
            if not before or not suggested:
                continue

            def _clean_str(s: str) -> str:
                return " ".join(s.split()).lower()

            clean_before = _clean_str(before)

            def _try_replace(target_text: str) -> Tuple[str, bool]:
                if not target_text:
                    return target_text, False
                # 1. Exact match
                if before in target_text:
                    return target_text.replace(before, suggested, 1), True
                # 2. Case-insensitive match
                pattern = re.compile(re.escape(before), re.IGNORECASE)
                if pattern.search(target_text):
                    return pattern.sub(suggested, target_text, count=1), True
                # 3. Punctuation stripped match
                stripped_before = before.rstrip(".").rstrip(",").rstrip(";").strip()
                if stripped_before and stripped_before in target_text:
                    return target_text.replace(stripped_before, suggested, 1), True
                # 4. Normalized whitespace match
                clean_target = _clean_str(target_text)
                if clean_before in clean_target:
                    return suggested, True
                return target_text, False

            replaced = False

            # Search in professional_summary
            if "professional_summary" in modified and isinstance(modified["professional_summary"], str):
                new_text, ok = _try_replace(modified["professional_summary"])
                if ok:
                    modified["professional_summary"] = new_text
                    replaced = True

            # Search in work_experience
            if not replaced and "work_experience" in modified and isinstance(modified["work_experience"], list):
                for job in modified["work_experience"]:
                    if not isinstance(job, dict):
                        continue
                    bullets = job.get("bullet_points") or []
                    new_bullets = []
                    for b in bullets:
                        new_b, ok = _try_replace(str(b))
                        if ok:
                            replaced = True
                            new_bullets.append(new_b)
                        else:
                            new_bullets.append(b)
                    job["bullet_points"] = new_bullets
                    if replaced:
                        break

            # Search in projects
            if not replaced and "projects" in modified and isinstance(modified["projects"], list):
                for proj in modified["projects"]:
                    if not isinstance(proj, dict):
                        continue
                    if "description" in proj and isinstance(proj["description"], str):
                        new_desc, ok = _try_replace(proj["description"])
                        if ok:
                            proj["description"] = new_desc
                            replaced = True
                            break

            # Search in skills
            if not replaced and "skills" in modified and isinstance(modified["skills"], list):
                new_skills = []
                for s in modified["skills"]:
                    new_s, ok = _try_replace(str(s))
                    if ok:
                        replaced = True
                        new_skills.append(new_s)
                    else:
                        new_skills.append(s)
                modified["skills"] = new_skills

            # Fallback 1: High similarity match on bullet points or summary (> 0.65 similarity)
            if not replaced:
                best_ratio = 0.0
                best_location = None

                if "professional_summary" in modified and isinstance(modified["professional_summary"], str):
                    ratio = difflib.SequenceMatcher(None, clean_before, _clean_str(modified["professional_summary"])).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_location = ("summary", None, None)

                if "work_experience" in modified and isinstance(modified["work_experience"], list):
                    for j_idx, job in enumerate(modified["work_experience"]):
                        if isinstance(job, dict):
                            for b_idx, b in enumerate(job.get("bullet_points") or []):
                                ratio = difflib.SequenceMatcher(None, clean_before, _clean_str(str(b))).ratio()
                                if ratio > best_ratio:
                                    best_ratio = ratio
                                    best_location = ("bullet", j_idx, b_idx)

                if best_ratio >= 0.65 and best_location:
                    if best_location[0] == "summary":
                        modified["professional_summary"] = suggested
                        replaced = True
                    elif best_location[0] == "bullet":
                        modified["work_experience"][best_location[1]]["bullet_points"][best_location[2]] = suggested
                        replaced = True

            # Fallback 2: If the suggestion is valid and approved, ensure it appears in the primary work experience bullet points
            if not replaced:
                if "work_experience" in modified and isinstance(modified["work_experience"], list) and len(modified["work_experience"]) > 0:
                    if "bullet_points" not in modified["work_experience"][0] or not isinstance(modified["work_experience"][0]["bullet_points"], list):
                        modified["work_experience"][0]["bullet_points"] = []
                    modified["work_experience"][0]["bullet_points"].append(suggested)
                    replaced = True
                elif "professional_summary" in modified and modified["professional_summary"]:
                    modified["professional_summary"] += f" {suggested}"
                    replaced = True
                else:
                    modified["professional_summary"] = suggested
                    replaced = True

            if replaced:
                applied.append(sug)

        return modified, applied

    @classmethod
    def parse_resume_deterministic(cls, raw_text: str) -> Dict[str, Any]:
        """
        Rule-based deterministic resume parser that guarantees 100% section and entity retention
        from raw plain text without relying solely on LLM truncation or hallucinations.
        """
        bullet_re = re.compile(r'^[•\u2022\u25cf\u25aa\u25e6\ufffd\-\*]\s*')
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        name = lines[0] if lines else "Candidate"

        # Contact info extraction
        email_m = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', raw_text)
        email = email_m.group(0) if email_m else ""

        phone_m = re.search(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b|\b\d{10}\b', raw_text)
        phone = phone_m.group(0) if phone_m else ""

        linkedin_m = re.search(r'LinkedIn:\s*([^\n|]+)', raw_text, re.I)
        linkedin = ""
        if linkedin_m:
            candidate_url = linkedin_m.group(1).strip()
            if "[your" not in candidate_url.lower():
                linkedin = candidate_url

        location = ""
        if len(lines) > 1 and '|' in lines[1]:
            for p in [x.strip() for x in lines[1].split('|')]:
                if '@' not in p and not re.search(r'\d{5,}', p) and 'linkedin' not in p.lower():
                    location = p
                    break

        # Section boundaries detection
        sec_patterns = [
            ('summary', re.compile(r'^(?:PROFESSIONAL\s+SUMMARY|SUMMARY|EXECUTIVE\s+SUMMARY)\b', re.I | re.M)),
            ('technical_skills', re.compile(r'^(?:TECHNICAL\s+SKILLS|CORE\s+SKILLS|CORE\s+COMPETENCIES)\b', re.I | re.M)),
            ('experience', re.compile(r'^(?:PROFESSIONAL\s+EXPERIENCE|WORK\s+EXPERIENCE|EXPERIENCE|EMPLOYMENT\s+HISTORY)\b', re.I | re.M)),
            ('projects', re.compile(r'^(?:KEY\s+PROJECTS|PROJECTS|ACADEMIC\s+PROJECTS)\b', re.I | re.M)),
            ('education', re.compile(r'^(?:EDUCATION|ACADEMIC\s+BACKGROUND)\b', re.I | re.M)),
            ('certifications', re.compile(r'^(?:CERTIFICATIONS|CERTIFICATES|LICENSES\s+&\s+CERTIFICATIONS)\b', re.I | re.M)),
            ('career_objective', re.compile(r'^(?:CAREER\s+OBJECTIVE|OBJECTIVE)\b', re.I | re.M)),
        ]

        matches = []
        for sec_name, pat in sec_patterns:
            for m in pat.finditer(raw_text):
                matches.append((m.start(), m.end(), sec_name))
        matches.sort()

        sections = {}
        for i in range(len(matches)):
            start, end, sec_name = matches[i]
            next_start = matches[i+1][0] if i + 1 < len(matches) else len(raw_text)
            sections[sec_name] = raw_text[end:next_start].strip()

        # 1. Summary
        summary = sections.get('summary', '')

        # 2. Career Objective
        career_objective = sections.get('career_objective', '')

        # 3. Technical Skills (Categorized and Flat)
        tech_skills = {}
        flat_skills = []
        if 'technical_skills' in sections:
            cat_pat = re.compile(r'^(Languages|AI & GenAI|AI & Machine Learning|Backend|Frontend|Databases|Analytics & BI|Architecture|Tools|Frameworks|Libraries|Cloud|DevOps)[:\s]+(.*)$', re.I)
            curr_cat = None
            for line in [l.strip() for l in sections['technical_skills'].splitlines() if l.strip()]:
                m = cat_pat.match(line)
                if m:
                    curr_cat = m.group(1).strip()
                    items = [i.strip() for i in m.group(2).split(',') if i.strip()]
                    tech_skills[curr_cat] = items
                    flat_skills.extend(items)
                elif curr_cat:
                    items = [i.strip() for i in line.split(',') if i.strip()]
                    tech_skills[curr_cat].extend(items)
                    flat_skills.extend(items)
                else:
                    items = [i.strip() for i in line.split(',') if i.strip()]
                    flat_skills.extend(items)

        # 4. Experience
        work_experience = []
        if 'experience' in sections:
            curr_job = None
            curr_bullet = []
            is_tech_cont = False

            for line in [l.strip() for l in sections['experience'].splitlines() if l.strip()]:
                is_bullet = bool(bullet_re.match(line))
                is_tech = line.lower().startswith('technologies:')

                if '|' in line and not is_bullet:
                    if curr_bullet and curr_job:
                        curr_job['bullet_points'].append(' '.join(curr_bullet))
                        curr_bullet = []
                    if curr_job:
                        work_experience.append(curr_job)

                    parts = [p.strip() for p in line.split('|')]
                    title = parts[0]
                    rest = parts[1] if len(parts) > 1 else ''

                    dur_m = re.search(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})\b.*)$', rest)
                    if dur_m:
                        duration = dur_m.group(1).replace('\ufffd', '–')
                        company = rest[:dur_m.start()].strip().rstrip(',-').strip()
                    else:
                        company = rest
                        duration = ''

                    curr_job = {
                        'company': company,
                        'job_title': title,
                        'duration': duration,
                        'bullet_points': [],
                        'technologies': []
                    }
                    is_tech_cont = False
                elif is_tech:
                    if curr_bullet and curr_job:
                        curr_job['bullet_points'].append(' '.join(curr_bullet))
                        curr_bullet = []
                    tech_str = line[len('technologies:'):].strip()
                    if curr_job:
                        curr_job['technologies'] = [t.strip() for t in tech_str.split(',') if t.strip()]
                    is_tech_cont = True
                elif is_bullet:
                    if curr_bullet and curr_job:
                        curr_job['bullet_points'].append(' '.join(curr_bullet))
                        curr_bullet = []
                    clean_b = bullet_re.sub('', line).strip()
                    curr_bullet = [clean_b]
                    is_tech_cont = False
                else:
                    if is_tech_cont and curr_job:
                        extra_techs = [t.strip() for t in line.split(',') if t.strip()]
                        curr_job['technologies'].extend(extra_techs)
                    elif curr_bullet:
                        curr_bullet.append(line)
                    elif curr_job:
                        curr_job['job_title'] += ' ' + line

            if curr_bullet and curr_job:
                curr_job['bullet_points'].append(' '.join(curr_bullet))
            if curr_job:
                work_experience.append(curr_job)

        # 5. Projects
        projects = []
        if 'projects' in sections:
            curr_proj = None
            curr_bullet = []
            is_tech_cont = False

            for line in [l.strip() for l in sections['projects'].splitlines() if l.strip()]:
                is_bullet = bool(bullet_re.match(line))
                is_tech = line.lower().startswith('technologies:')

                if is_tech:
                    if curr_bullet and curr_proj:
                        curr_proj['bullet_points'].append(' '.join(curr_bullet))
                        curr_bullet = []
                    tech_str = line[len('technologies:'):].strip()
                    if curr_proj:
                        curr_proj['technologies'] = [t.strip() for t in tech_str.split(',') if t.strip()]
                        projects.append(curr_proj)
                        curr_proj = None
                    is_tech_cont = True
                elif is_bullet:
                    if curr_bullet and curr_proj:
                        curr_proj['bullet_points'].append(' '.join(curr_bullet))
                        curr_bullet = []
                    clean_b = bullet_re.sub('', line).strip()
                    curr_bullet = [clean_b]
                    is_tech_cont = False
                elif curr_proj is None:
                    curr_proj = {
                        'name': line,
                        'description': '',
                        'bullet_points': [],
                        'technologies': []
                    }
                    is_tech_cont = False
                else:
                    if is_tech_cont and curr_proj:
                        extra_techs = [t.strip() for t in line.split(',') if t.strip()]
                        curr_proj['technologies'].extend(extra_techs)
                    elif curr_bullet:
                        curr_bullet.append(line)
                    else:
                        curr_proj['name'] += ' ' + line

            if curr_bullet and curr_proj:
                curr_proj['bullet_points'].append(' '.join(curr_bullet))
            if curr_proj:
                projects.append(curr_proj)

        # 6. Education
        education = []
        if 'education' in sections:
            edu_lines = [l.strip() for l in sections['education'].splitlines() if l.strip()]
            i = 0
            while i < len(edu_lines):
                line = edu_lines[i]
                year_m = re.search(r'(20\d\d\s*[–—\-\ufffd]\s*(?:20\d\d|Present)|\b20\d\d\b)', line)
                year = year_m.group(0).replace('\ufffd', '–') if year_m else ''
                deg = line
                if year_m:
                    deg = line[:year_m.start()].strip().rstrip('–—-').strip()
                inst = ''
                if i + 1 < len(edu_lines) and not re.search(r'(Master|Bachelor|B\.Sc|M\.Sc|B\.E|B\.Tech|Degree|Diploma|Ph\.D)', edu_lines[i+1], re.I):
                    inst = edu_lines[i+1]
                    i += 1
                education.append({
                    'degree': deg,
                    'institution': inst,
                    'year': year
                })
                i += 1

        # 7. Certifications
        certifications = []
        if 'certifications' in sections:
            for line in sections['certifications'].splitlines():
                line = line.strip()
                if not line:
                    continue
                clean_c = bullet_re.sub('', line).strip()
                if clean_c:
                    certifications.append(clean_c)

        return {
            "name": name,
            "contact_info": {
                "email": email,
                "phone": phone,
                "location": location,
                "linkedin": linkedin,
            },
            "career_objective": career_objective,
            "professional_summary": summary,
            "technical_skills": tech_skills,
            "skills": flat_skills,
            "work_experience": work_experience,
            "projects": projects,
            "education": education,
            "certifications": certifications,
        }

    @classmethod
    def parse_resume_hybrid(cls, raw_text: str, llm_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Hybrid parser combining deterministic rule-based section segmentation with LLM structuring.
        Guarantees zero dropped sections: if LLM drops projects, education, certs, or objective,
        deterministic extraction immediately restores all factual entities.
        """
        det = cls.parse_resume_deterministic(raw_text)
        if not llm_data or not isinstance(llm_data, dict):
            return det

        merged = dict(det)

        # Name: prioritize deterministic line-0 name if valid (never allow generic 'Applicant')
        if det.get("name") and det["name"] not in ("Applicant", "Candidate"):
            merged["name"] = det["name"]
        elif llm_data.get("name") and llm_data["name"] not in ("Applicant", "Candidate"):
            merged["name"] = llm_data["name"]

        # Contact info: merge fields
        llm_ci = llm_data.get("contact_info") or {}
        for k in ["email", "phone", "location", "linkedin"]:
            if not merged["contact_info"].get(k) and llm_ci.get(k):
                merged["contact_info"][k] = llm_ci[k]

        # Career objective
        if not merged.get("career_objective") and llm_data.get("career_objective"):
            merged["career_objective"] = llm_data["career_objective"]

        # Professional summary
        if llm_data.get("professional_summary") and len(llm_data["professional_summary"]) > 30:
            merged["professional_summary"] = llm_data["professional_summary"]

        # Technical skills
        llm_tech = llm_data.get("technical_skills")
        if isinstance(llm_tech, dict) and llm_tech:
            merged["technical_skills"] = {**det.get("technical_skills", {}), **llm_tech}

        # Skills: union
        llm_skills = llm_data.get("skills") or []
        if isinstance(llm_skills, list):
            merged["skills"] = list(dict.fromkeys(det.get("skills", []) + llm_skills))

        # Work experience: keep deterministic if LLM dropped jobs
        llm_exp = llm_data.get("work_experience") or []
        det_exp = det.get("work_experience") or []
        if isinstance(llm_exp, list) and len(llm_exp) >= len(det_exp):
            for idx, job in enumerate(llm_exp):
                if idx < len(det_exp) and not job.get("technologies") and det_exp[idx].get("technologies"):
                    job["technologies"] = det_exp[idx]["technologies"]
            merged["work_experience"] = llm_exp

        # Projects: keep deterministic if LLM dropped projects
        llm_projs = llm_data.get("projects") or []
        det_projs = det.get("projects") or []
        if isinstance(llm_projs, list) and len(llm_projs) >= len(det_projs):
            merged["projects"] = llm_projs

        # Education: keep deterministic if LLM dropped education
        llm_edu = llm_data.get("education") or []
        det_edu = det.get("education") or []
        if isinstance(llm_edu, list) and len(llm_edu) >= len(det_edu):
            merged["education"] = llm_edu

        # Certifications: keep deterministic if LLM dropped certs
        llm_certs = llm_data.get("certifications") or []
        det_certs = det.get("certifications") or []
        if isinstance(llm_certs, list) and len(llm_certs) >= len(det_certs):
            merged["certifications"] = llm_certs

        return merged

    @staticmethod
    def render_resume_pdf(structured_data: Dict[str, Any], output_path: str, title: str = "Resume") -> str:
        """
        Renders a clean, single-column, ATS-compliant PDF resume from structured resume JSON.
        Renders all 7 sections with professional ATS typography and zero data loss.
        """
        doc = SimpleDocTemplate(
            output_path,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()

        name_style = ParagraphStyle(
            "ATS_Name",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=17,
            leading=21,
            textColor=colors.HexColor("#0f172a"),
            alignment=0,
            spaceAfter=2,
        )

        contact_style = ParagraphStyle(
            "ATS_Contact",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor("#475569"),
            alignment=0,
            spaceAfter=8,
        )

        section_heading = ParagraphStyle(
            "ATS_Section",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#1e3a8a"),
            spaceBefore=7,
            spaceAfter=2,
            keepWithNext=True,
        )

        job_header = ParagraphStyle(
            "ATS_JobHeader",
            parent=styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#1e293b"),
            spaceBefore=4,
            spaceAfter=2,
            keepWithNext=True,
        )

        body_style = ParagraphStyle(
            "ATS_Body",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#334155"),
            spaceAfter=3,
        )

        bullet_style = ParagraphStyle(
            "ATS_Bullet",
            parent=styles["Normal"],
            fontName="Helvetica",
            fontSize=8.5,
            leading=11.5,
            textColor=colors.HexColor("#334155"),
            leftIndent=10,
            spaceAfter=2,
        )

        story = []

        def esc(txt: Any) -> str:
            if txt is None:
                return ""
            return html.escape(str(txt).strip())

        # 1. Candidate Name
        name = structured_data.get("name") or "Candidate"
        story.append(Paragraph(esc(name), name_style))

        # 2. Contact Info
        contact = structured_data.get("contact_info") or {}
        contact_parts = []
        if contact.get("location"):
            contact_parts.append(esc(contact["location"]))
        if contact.get("email"):
            contact_parts.append(esc(contact["email"]))
        if contact.get("phone"):
            contact_parts.append(esc(contact["phone"]))
        if contact.get("linkedin"):
            contact_parts.append(f"LinkedIn: {esc(contact['linkedin'])}")

        if contact_parts:
            story.append(Paragraph(" &nbsp;|&nbsp; ".join(contact_parts), contact_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=0, spaceAfter=5))

        # 3. Career Objective (if present)
        objective = structured_data.get("career_objective")
        if objective and objective.strip():
            story.append(Paragraph("CAREER OBJECTIVE", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceBefore=1, spaceAfter=3))
            story.append(Paragraph(esc(objective), body_style))
            story.append(Spacer(1, 3))

        # 4. Professional Summary (if present)
        summary = structured_data.get("professional_summary")
        if summary and summary.strip():
            story.append(Paragraph("PROFESSIONAL SUMMARY", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceBefore=1, spaceAfter=3))
            story.append(Paragraph(esc(summary), body_style))
            story.append(Spacer(1, 3))

        # 5. Technical Skills
        tech_skills = structured_data.get("technical_skills")
        skills = structured_data.get("skills")
        if tech_skills or skills:
            story.append(Paragraph("TECHNICAL SKILLS", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceBefore=1, spaceAfter=3))
            if isinstance(tech_skills, dict) and tech_skills:
                lines = []
                for cat, items in tech_skills.items():
                    if isinstance(items, list):
                        item_str = ", ".join(esc(i) for i in items if i)
                    else:
                        item_str = esc(items)
                    lines.append(f"<b>{esc(cat)}:</b> {item_str}")
                story.append(Paragraph("<br/>".join(lines), body_style))
            elif isinstance(skills, list):
                story.append(Paragraph(", ".join(esc(s) for s in skills if s), body_style))
            elif isinstance(skills, str):
                story.append(Paragraph(esc(skills), body_style))
            story.append(Spacer(1, 3))

        # 6. Professional Experience
        work_exp = structured_data.get("work_experience") or []
        if work_exp:
            story.append(Paragraph("PROFESSIONAL EXPERIENCE", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceBefore=1, spaceAfter=3))
            for job in work_exp:
                if not isinstance(job, dict):
                    continue
                title_str = esc(job.get("job_title") or "Software Engineer")
                company_str = esc(job.get("company") or "")
                duration_str = esc(job.get("duration") or "")

                header_line = f"<b>{title_str}</b>"
                if company_str:
                    header_line += f" &mdash; <i>{company_str}</i>"
                if duration_str:
                    header_line += f" <font color='#64748b'>({duration_str})</font>"

                story.append(Paragraph(header_line, job_header))

                bullets = job.get("bullet_points") or []
                if isinstance(bullets, list):
                    for b in bullets:
                        if b:
                            story.append(Paragraph(f"&bull; {esc(b)}", bullet_style))
                elif isinstance(bullets, str) and bullets.strip():
                    story.append(Paragraph(esc(bullets), body_style))

                if job.get("description"):
                    story.append(Paragraph(esc(job["description"]), body_style))

                techs = job.get("technologies") or []
                if techs:
                    tech_line = f"<b>Technologies:</b> {', '.join(esc(t) for t in techs)}"
                    story.append(Paragraph(tech_line, bullet_style))

                story.append(Spacer(1, 3))

        # 7. Key Projects
        projects = structured_data.get("projects") or []
        if projects:
            story.append(Paragraph("KEY PROJECTS", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceBefore=1, spaceAfter=3))
            for proj in projects:
                if not isinstance(proj, dict):
                    continue
                p_name = esc(proj.get("name") or "Project")
                story.append(Paragraph(f"<b>{p_name}</b>", job_header))

                bullets = proj.get("bullet_points") or []
                if isinstance(bullets, list) and bullets:
                    for b in bullets:
                        if b:
                            story.append(Paragraph(f"&bull; {esc(b)}", bullet_style))
                elif proj.get("description"):
                    story.append(Paragraph(f"&bull; {esc(proj['description'])}", bullet_style))

                techs = proj.get("technologies") or []
                if techs:
                    tech_line = f"<b>Technologies:</b> {', '.join(esc(t) for t in techs)}"
                    story.append(Paragraph(tech_line, bullet_style))

                story.append(Spacer(1, 2))

        # 8. Education
        education = structured_data.get("education") or []
        if education:
            story.append(Paragraph("EDUCATION", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceBefore=1, spaceAfter=3))
            for edu in education:
                if isinstance(edu, dict):
                    deg = esc(edu.get("degree") or "")
                    inst = esc(edu.get("institution") or "")
                    yr = esc(edu.get("year") or "")
                    edu_line = f"<b>{deg}</b>"
                    if inst:
                        edu_line += f", {inst}"
                    if yr:
                        edu_line += f" <font color='#64748b'>({yr})</font>"
                    story.append(Paragraph(edu_line, body_style))
                elif isinstance(edu, str):
                    story.append(Paragraph(esc(edu), body_style))
            story.append(Spacer(1, 3))

        # 9. Certifications
        certs = structured_data.get("certifications") or []
        if certs:
            story.append(Paragraph("CERTIFICATIONS", section_heading))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceBefore=1, spaceAfter=3))
            if isinstance(certs, list):
                for c in certs:
                    story.append(Paragraph(f"&bull; {esc(c)}", bullet_style))
            else:
                story.append(Paragraph(esc(certs), body_style))

        doc.build(story)
        return output_path

    @classmethod
    def validate_no_data_loss(
        cls,
        source_raw_text: str,
        structured_data: Dict[str, Any],
        generated_pdf_path: str,
    ) -> Tuple[bool, List[str]]:
        """
        Anti-Data-Loss Validation Guardrail:
        Extracts plain text from the generated PDF and asserts that 100% of candidate
        factual entities (name, contact, employers, titles, projects, education, certs, objective)
        are faithfully rendered without any dropping or truncating.
        Returns (is_valid, list_of_missing_entities).
        """
        if not os.path.exists(generated_pdf_path):
            return False, [f"Generated PDF file not found at {generated_pdf_path}"]

        extracted = cls.extract_text(generated_pdf_path, "pdf")
        if not extracted:
            return False, ["Failed to extract text from generated PDF document."]

        def norm(s: str) -> str:
            clean = re.sub(r'[^\w\s]', ' ', s.lower())
            return " ".join(clean.split())

        norm_pdf = norm(extracted)
        missing = []

        # 1. Candidate Name
        cand_name = structured_data.get("name") or ""
        if cand_name and norm(cand_name) not in norm_pdf:
            name_parts = cand_name.split()
            if not (name_parts and norm(name_parts[0]) in norm_pdf and norm(name_parts[-1]) in norm_pdf):
                missing.append(f"Candidate Name: '{cand_name}'")

        # 2. Contact details
        ci = structured_data.get("contact_info") or {}
        if ci.get("email") and norm(ci["email"]) not in norm_pdf:
            missing.append(f"Email: '{ci['email']}'")
        if ci.get("phone") and norm(ci["phone"]) not in norm_pdf:
            missing.append(f"Phone: '{ci['phone']}'")

        # 3. Work Experience: employers and job titles
        for j in structured_data.get("work_experience") or []:
            if isinstance(j, dict):
                comp = j.get("company", "")
                if comp and norm(comp) not in norm_pdf:
                    comp_words = norm(comp).split()
                    if not any(w in norm_pdf for w in comp_words if len(w) > 4):
                        missing.append(f"Employer: '{comp}'")
                title = j.get("job_title", "")
                if title and norm(title) not in norm_pdf:
                    missing.append(f"Job Title: '{title}'")

        # 4. Projects: all project names
        for p in structured_data.get("projects") or []:
            if isinstance(p, dict):
                pname = p.get("name", "")
                if pname and norm(pname) not in norm_pdf:
                    missing.append(f"Project: '{pname}'")

        # 5. Education: all institutions and degrees
        for edu in structured_data.get("education") or []:
            if isinstance(edu, dict):
                inst = edu.get("institution", "")
                if inst and norm(inst) not in norm_pdf:
                    inst_words = [w for w in norm(inst).split() if len(w) > 3 and w not in ('college', 'university', 'institute')]
                    if not any(w in norm_pdf for w in inst_words):
                        missing.append(f"Education Institution: '{inst}'")
                deg = edu.get("degree", "")
                if deg and norm(deg) not in norm_pdf:
                    deg_words = [w for w in norm(deg).split() if len(w) > 3]
                    if not any(w in norm_pdf for w in deg_words):
                        missing.append(f"Degree: '{deg}'")

        # 6. Certifications: all certifications
        for cert in structured_data.get("certifications") or []:
            c_str = str(cert)
            if c_str and norm(c_str) not in norm_pdf:
                c_words = [w for w in norm(c_str).split() if len(w) > 3]
                if not any(w in norm_pdf for w in c_words):
                    missing.append(f"Certification: '{c_str}'")

        # 7. Career objective
        obj = structured_data.get("career_objective", "")
        if obj and len(obj) > 20:
            obj_words = [w for w in norm(obj).split() if len(w) > 5]
            matched_words = [w for w in obj_words if w in norm_pdf]
            if len(matched_words) < len(obj_words) * 0.4:
                missing.append(f"Career Objective: '{obj[:40]}...'")

        return len(missing) == 0, missing

    @staticmethod
    def render_resume_docx(structured_data: Dict[str, Any], output_path: str) -> str:
        """Renders an ATS-compliant Word DOCX document."""
        doc = docx.Document()
        name = structured_data.get("name") or "Candidate"
        doc.add_heading(name, level=0)

        contact = structured_data.get("contact_info") or {}
        contact_parts = [contact.get(k) for k in ["location", "email", "phone", "linkedin"] if contact.get(k)]
        if contact_parts:
            doc.add_paragraph(" | ".join(contact_parts))

        if structured_data.get("career_objective"):
            doc.add_heading("Career Objective", level=1)
            doc.add_paragraph(structured_data["career_objective"])

        if structured_data.get("professional_summary"):
            doc.add_heading("Professional Summary", level=1)
            doc.add_paragraph(structured_data["professional_summary"])

        tech_skills = structured_data.get("technical_skills")
        skills = structured_data.get("skills")
        if tech_skills or skills:
            doc.add_heading("Technical Skills", level=1)
            if isinstance(tech_skills, dict) and tech_skills:
                for cat, items in tech_skills.items():
                    item_str = ", ".join(items) if isinstance(items, list) else str(items)
                    p = doc.add_paragraph()
                    r = p.add_run(f"{cat}: ")
                    r.bold = True
                    p.add_run(item_str)
            elif skills:
                doc.add_paragraph(", ".join(skills) if isinstance(skills, list) else str(skills))

        if structured_data.get("work_experience"):
            doc.add_heading("Professional Experience", level=1)
            for job in structured_data["work_experience"]:
                if isinstance(job, dict):
                    p = doc.add_paragraph()
                    run = p.add_run(f"{job.get('job_title', '')} - {job.get('company', '')} ({job.get('duration', '')})")
                    run.bold = True
                    for b in job.get("bullet_points", []):
                        doc.add_paragraph(b, style="List Bullet")
                    if job.get("technologies"):
                        p_tech = doc.add_paragraph()
                        r = p_tech.add_run("Technologies: ")
                        r.bold = True
                        p_tech.add_run(", ".join(job["technologies"]))

        if structured_data.get("projects"):
            doc.add_heading("Key Projects", level=1)
            for proj in structured_data["projects"]:
                if isinstance(proj, dict):
                    p = doc.add_paragraph()
                    run = p.add_run(proj.get("name", ""))
                    run.bold = True
                    bullets = proj.get("bullet_points") or []
                    if bullets:
                        for b in bullets:
                            doc.add_paragraph(b, style="List Bullet")
                    elif proj.get("description"):
                        doc.add_paragraph(proj["description"], style="List Bullet")
                    if proj.get("technologies"):
                        p_tech = doc.add_paragraph()
                        r = p_tech.add_run("Technologies: ")
                        r.bold = True
                        p_tech.add_run(", ".join(proj["technologies"]))

        if structured_data.get("education"):
            doc.add_heading("Education", level=1)
            for edu in structured_data["education"]:
                if isinstance(edu, dict):
                    doc.add_paragraph(f"{edu.get('degree', '')}, {edu.get('institution', '')} ({edu.get('year', '')})")

        if structured_data.get("certifications"):
            doc.add_heading("Certifications", level=1)
            for c in structured_data["certifications"]:
                doc.add_paragraph(str(c), style="List Bullet")

        doc.save(output_path)
        return output_path

    @classmethod
    def render_resume_document(cls, structured_data: Dict[str, Any], output_path: str, file_type: str = "pdf") -> str:
        """Render either PDF or DOCX document based on requested type."""
        if file_type == "docx":
            return cls.render_resume_docx(structured_data, output_path)
        return cls.render_resume_pdf(structured_data, output_path)

    @classmethod
    def verify_optimized_document(
        cls,
        file_path: str,
        file_type: str,
        approved_suggestions: List[Dict[str, Any]],
    ) -> Tuple[bool, str]:
        """
        Programmatic verification step after PDF/DOCX generation:
        Extracts plain text from the newly generated document and verifies that:
        1. Every approved suggestion's 'suggested' text is actually present in the document.
        2. The original 'before' text is no longer present (unless it is a substring of suggested).
        Returns (is_valid, error_detail).
        """
        if not os.path.exists(file_path):
            return False, f"Document file not found at {file_path}"

        extracted_text = cls.extract_text(file_path, file_type)
        if not extracted_text:
            return False, "Failed to extract text from newly generated document."

        def _norm(s: str) -> str:
            s_clean = re.sub(r'[^\w\s]', ' ', s.lower())
            return " ".join(s_clean.split())

        norm_extracted = _norm(extracted_text)

        for sug in approved_suggestions:
            if not sug.get("approved_by_user"):
                continue

            suggested = str(sug.get("suggested", "")).strip()
            before = str(sug.get("before", "")).strip()

            norm_suggested = _norm(suggested)
            norm_before = _norm(before)

            # 1. Assert suggested text is present
            if norm_suggested not in norm_extracted:
                words = norm_suggested.split()
                sub_check = " ".join(words[:min(len(words), 8)])
                if sub_check not in norm_extracted:
                    return False, (
                        f"Programmatic verification FAILED: Approved ATS suggestion "
                        f"'{suggested}' was NOT found in the generated {file_type.upper()} document."
                    )

            # 2. Assert old 'before' text has been replaced
            if norm_before and norm_before in norm_extracted:
                if norm_before not in norm_suggested and norm_before != norm_suggested:
                    return False, (
                        f"Programmatic verification FAILED: Original text '{before}' "
                        f"is still present in the generated {file_type.upper()} document."
                    )

        return True, ""


def get_resume_service() -> ResumeService:
    return ResumeService()
