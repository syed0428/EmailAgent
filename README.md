# EmailAgent 🚀

**EmailAgent** is an intelligent, full-stack job application assistant and automated recruiter outreach platform. It analyzes job descriptions against candidate resumes, calculates an explainable match score, suggests truthful ATS-optimized enhancements, generates ATS-compliant resumes with zero data loss, crafts personalized recruiter cover emails, and transmits applications directly via official Gmail OAuth 2.0.

---

## ✨ Key Features

- 📄 **Dual-Engine Resume Ingestion**: High-fidelity PDF & DOCX text extraction with a deterministic fallback engine that guarantees 100% preservation of original factual entities (employers, titles, projects, education, certifications, and career objective).
- 🎯 **Explainable Job Matching**: Multi-dimensional semantic alignment comparing required vs. preferred skills and keyword density, returning actionable gap analyses and match percentages.
- 🛡️ **Anti-Fabrication Safeguard Engine**: Enforces strict truthfulness—distinguishes valid stylistic rewriting from hallucinated metrics, unearned certifications, or fabricated technologies.
- 📝 **Zero-Data-Loss ATS Resume Generator**: Compiles approved suggestions into clean, single-column, ATS-friendly resumes rendered with ReportLab, verified by automated post-render entity assertions.
- ✉️ **Custom Recruiter Email Drafting**: Generates context-aware, tailored cover emails aligning candidate achievements directly with company needs.
- 📬 **Native Gmail OAuth 2.0 Transmission**: Direct sending via Gmail API with proper `multipart/alternative` body encapsulation and attachment integrity validation.
- 🖥️ **Modern Reactive Dashboard**: Sleek React + Vite frontend with multi-step interactive workflow, real-time feedback, and Gmail connection management.

---

## 🛠️ Architecture & Tech Stack

### Backend
- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.10+)
- **Database / ORM**: PostgreSQL with [SQLAlchemy](https://www.sqlalchemy.org/) & [Alembic](https://alembic.sqlalchemy.org/)
- **Document Processing**: [ReportLab](https://www.reportlab.com/), [pypdf](https://pypdf.readthedocs.io/), [python-docx](https://python-docx.readthedocs.io/)
- **AI & Embeddings**: [Ollama](https://ollama.com/) (Qwen 2.5 / DeepSeek) & [Sentence Transformers](https://www.sbert.net/)
- **Authentication / API**: Google OAuth 2.0 & Gmail REST API

### Frontend
- **Framework**: [React 18](https://react.dev/) + [Vite](https://vitejs.dev/)
- **Icons**: [Lucide React](https://lucide.dev/)
- **Styling**: Modern responsive design system with CSS custom properties

---

## 📁 Repository Structure

```
EmailAgent/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/          # FastAPI routers (jobs, gmail, auth, health)
│   │   ├── core/                # App configuration, security, CORS
│   │   ├── db/                  # Database session management
│   │   ├── models/              # SQLAlchemy database models
│   │   └── services/            # Core business logic (AI, Resume, Gmail)
│   ├── storage/                 # Local private resume storage
│   ├── requirements.txt         # Python dependencies
│   └── verify.py                # Environment and connectivity diagnostics
├── frontend/
│   ├── src/
│   │   ├── components/          # Reusable UI components
│   │   ├── pages/               # Application views (JobAssistant, Accounts, etc.)
│   │   ├── services/            # API client layer
│   │   └── App.jsx              # Main routing and navigation
│   ├── package.json             # Node dependencies
│   └── vite.config.js           # Vite configuration
├── scripts/
│   ├── setup_db.bat             # PostgreSQL database initializer
│   ├── start_backend.bat        # Backend launch script
│   └── start_frontend.bat       # Frontend launch script
├── .env.example                 # Environment variables template
├── .gitignore                   # Version control ignore rules
└── README.md                    # Project documentation
```

---

## 🚀 Getting Started

### 1. Prerequisites
- **Python** 3.10+
- **Node.js** 18+ and npm
- **PostgreSQL** 14+
- **Ollama** (optional for local LLM inference) or API keys
- **Google Cloud Console** Project with Gmail API enabled (for OAuth 2.0)

### 2. Backend Setup
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables:
   Copy `.env.example` in the root directory to `.env`:
   ```bash
   cp ../.env.example .env
   ```
   Fill in your PostgreSQL credentials, Ollama configurations, and Google OAuth credentials.
5. Initialize the database:
   ```bash
   python verify.py
   ```
6. Start the backend server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

### 3. Frontend Setup
1. Navigate to the frontend directory:
   ```bash
   cd ../frontend
   ```
2. Install npm packages:
   ```bash
   npm install
   ```
3. Launch the development server:
   ```bash
   npm run dev
   ```
4. Access the application in your browser at `http://localhost:5173`.

---

## 🔒 Security & Data Integrity

- **Strict Path-Traversal Guards**: File operations are validated against designated storage directories.
- **Magic Byte Validation**: Uploaded documents are verified against binary headers before acceptance.
- **Credential Segregation**: OAuth tokens and environment secrets are excluded from version control.
- **Deterministic Verification**: Every generated resume is cross-checked against source entity facts to prevent unwanted data loss or truncation.

---

## 📄 License

This project is licensed under the MIT License.
