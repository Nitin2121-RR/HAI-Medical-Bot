# MedReport AI

An intelligent medical report assistant that lets patients upload their PDF reports and ask natural language questions about them. Powered by a multi-step LangGraph pipeline with hybrid retrieval, reranking, and visual analysis.

---

## Features

- **PDF ingestion** — extracts text and runs OCR on image-only pages via RapidOCR
- **Hybrid retrieval** — combines ChromaDB vector search with BM25, then reranks with FlashRank
- **Visual analysis** — detects charts/tables in PDFs and describes them using Gemini Vision
- **Agentic pipeline** — LangGraph graph with input safety check → query classification → rewriting → retrieval → generation
- **Session memory** — per-session short-term memory (PostgresSaver) and user-level long-term memory (PostgresStore)
- **Multi-session chat** — create, rename, and delete chat sessions per document
- **JWT auth** — token-based authentication with bcrypt password hashing

---

## Architecture

```
User Message
     │
     ▼
┌─────────────────┐
│  Input Safety   │  ← blocks off-topic / harmful queries
└────────┬────────┘
         │ safe
         ▼
┌─────────────────┐
│ Query Classify  │  ← emergency_flag / out_of_scope / factual / explanation
└────────┬────────┘
         │ factual or explanation
         ▼
┌─────────────────┐
│  Query Rewrite  │  ← resolves pronouns/references using chat history
└────────┬────────┘
         ▼
┌─────────────────┐
│  Hybrid Retrieval│  ← ChromaDB k=5 → FlashRank rerank → top 2
└────────┬────────┘
         ▼
┌─────────────────┐
│ Visual Analysis │  ← Gemini Vision on pages with images/charts
└────────┬────────┘
         ▼
┌─────────────────┐
│   Generation    │  ← Gemini with rolling summary + retrieved context
└─────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI |
| LLM | Gemini 3.5 Flash Lite (via `langchain-google-genai`) |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (HuggingFace) |
| Vector Store | ChromaDB (local per-user persist) |
| Reranker | FlashRank |
| Orchestration | LangGraph |
| Checkpointing | PostgresSaver / PostgresStore (Neon) |
| OCR | RapidOCR |
| PDF Parsing | PyMuPDF (fitz) |
| Database ORM | SQLAlchemy + Alembic |
| Auth | JWT (python-jose) + bcrypt |

---

## Project Structure

```
├── main.py                  # FastAPI app entry point
├── auth.py                  # JWT creation & verification, current_user dependency
├── database.py              # SQLAlchemy engine & session
├── models.py                # DB models: user, ChatSession, messages, Documents
├── schema.py                # Pydantic request/response schemas
├── state.py                 # LangGraph State TypedDict
├── structure.py             # Full LangGraph graph definition & nodes
├── prompts.py               # All LLM prompt templates
├── report_receiver.py       # PDF extraction, OCR, visual analysis
├── vectore_store.py         # Text splitter helper
├── routes/
│   ├── user.py              # Register & login endpoints
│   └── current_user.py      # Chat, sessions, PDF upload endpoints
├── templates/               # Jinja2 HTML templates
├── uploads/                 # Uploaded PDFs (user_id_uuid.pdf)
├── vectorstore/             # ChromaDB persist dirs (user_id_uuid/)
├── alembic/                 # DB migrations
└── requirements.txt
```

---

## Setup

### 1. Clone & create a virtual environment

```bash
git clone <repo-url>
cd <repo-dir>
python -m venv myenv
# Windows
myenv\Scripts\activate
# Mac/Linux
source myenv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file in the project root:

```env
SECRET_KEY=your_jwt_secret_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

GEMINI_API_KEY_1=your_gemini_api_key_1
GEMINI_API_KEY_2=your_gemini_api_key_2
GEMINI_API_KEY_3=your_gemini_api_key_3

GROQ_API_KEY_1=your_groq_api_key_1
GROQ_API_KEY_2=your_groq_api_key_2

HUGGINGFACE=your_huggingface_api_token

DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
```

> Multiple Gemini/Groq keys are used to distribute load across pipeline nodes.

### 4. Run database migrations

```bash
alembic upgrade head
```

### 5. Start the server

```bash
uvicorn main:app --reload
```

---

## API Overview

### Auth

| Method | Endpoint | Description |
|---|---|---|
| GET | `/user/login` | Login page |
| POST | `/user/login` | Authenticate, returns JWT |
| GET | `/user/create` | Register page |
| POST | `/user/create` | Create account |

### Sessions

| Method | Endpoint | Description |
|---|---|---|
| POST | `/current_user/sessions` | Create a new chat session |
| GET | `/current_user/sessions` | List all sessions for user |
| PATCH | `/current_user/sessions/{id}` | Rename a session |
| DELETE | `/current_user/sessions/{id}` | Delete session + messages |
| GET | `/current_user/sessions/{id}/messages` | Get messages for a session |

### Chat & Upload

| Method | Endpoint | Description |
|---|---|---|
| POST | `/current_user/chat` | Send a message, get AI answer |
| POST | `/current_user/upload-pdf` | Upload a PDF, returns `uuid` |

> All `/current_user/*` endpoints require `Authorization: Bearer <token>` header.

### Chat Request Body

```json
{
  "question": "What is my HbA1c level?",
  "uuid_name": "uuid-returned-from-upload",
  "session_id": "session-uuid"
}
```

---

## How It Works

1. User uploads a PDF → text is extracted (OCR fallback for image pages) → chunked → embedded → stored in a per-user ChromaDB collection.
2. User sends a question with a `session_id` and the document `uuid`.
3. LangGraph runs the pipeline: safety check → classification → query rewrite → hybrid retrieval + rerank → visual analysis (if needed) → generation.
4. The answer and conversation are persisted to Postgres. LangGraph checkpoints maintain thread-level memory per session.

---

## Notes

- Each uploaded PDF gets its own isolated vector store at `vectorstore/{user_id}_{uuid}/`.
- Long conversations are automatically summarized to stay within context limits.
- Emergency or out-of-scope queries are intercepted before retrieval and return a safe, pre-defined response.
