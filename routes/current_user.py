from fastapi import APIRouter , Depends , Request , File , UploadFile , HTTPException
from sqlalchemy.orm import Session
from database import get_db
from fastapi.templating import Jinja2Templates
from auth import current_user
import models
from schema import ChatRequest , CreateSession
import os
import uuid
from langchain_chroma import Chroma
from structure import graphh
from langchain_core.messages import HumanMessage
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from dotenv import load_dotenv
from report_receiver import extract_pdf , page_to_image , conv_to_doc , split_doc

load_dotenv('.env')
router = APIRouter(prefix="/current_user", tags=["Current User"])
template = Jinja2Templates(directory="templates")

emb = HuggingFaceEndpointEmbeddings(
    model="sentence-transformers/all-MiniLM-L6-v2",
    huggingfacehub_api_token=os.getenv("HUGGINGFACE")
)


@router.get('/dashboard')
def current(request: Request, db: Session = Depends(get_db)):
    return template.TemplateResponse(request=request, name="dashboard.html")


@router.get('/')
def con(db: Session = Depends(get_db), current_user=Depends(current_user)):
    return {"name": current_user.name, "email": current_user.email}


@router.get('/chat')
def chat_page(request: Request, db: Session = Depends(get_db)):
    return template.TemplateResponse(request=request, name="chat.html")


# ─── Session endpoints ──────────────────────────────────────────────────────

@router.post("/sessions")
def create_session(body: CreateSession, db: Session = Depends(get_db), current_user=Depends(current_user)):
    """Create a new chat session and return its session_id."""
    new_session = models.ChatSession(
        session_id=str(uuid.uuid4()),
        name=body.name or "New Chat",
        user_id=current_user.id
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return {
        "session_id": new_session.session_id,
        "name": new_session.name,
        "created_at": new_session.created_at
    }


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), current_user=Depends(current_user)):
    """Return all sessions for the current user, newest first."""
    sessions = (
        db.query(models.ChatSession)
        .filter(models.ChatSession.user_id == current_user.id)
        .order_by(models.ChatSession.created_at.desc())
        .all()
    )
    return [
        {"session_id": s.session_id, "name": s.name, "created_at": s.created_at}
        for s in sessions
    ]


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: CreateSession, db: Session = Depends(get_db), current_user=Depends(current_user)):
    """Rename a session."""
    session = db.query(models.ChatSession).filter(
        models.ChatSession.session_id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.name = body.name
    db.commit()
    return {"session_id": session.session_id, "name": session.name}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db), current_user=Depends(current_user)):
    """Delete a session and all its messages."""
    session = db.query(models.ChatSession).filter(
        models.ChatSession.session_id == session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.delete(session)
    db.commit()
    return {"detail": "Session deleted"}


@router.get("/sessions/{session_id}/messages")
def session_messages(session_id: str, db: Session = Depends(get_db), current_user=Depends(current_user)):
    """Return all messages for a specific session."""
    msgs = (
        db.query(models.messages)
        .filter(
            models.messages.session_id == session_id,
            models.messages.user_id == current_user.id
        )
        .order_by(models.messages.id)
        .all()
    )
    return [{"role": m.role, "content": m.content} for m in msgs]


# ─── Chat ───────────────────────────────────────────────────────────────────

@router.post("/chat")
def chat(message: ChatRequest, db: Session = Depends(get_db), current_user=Depends(current_user)):
    # Validate session belongs to user
    session = db.query(models.ChatSession).filter(
        models.ChatSession.session_id == message.session_id,
        models.ChatSession.user_id == current_user.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = graphh.invoke(
        {
            "messages": [HumanMessage(content=message.question)],
            "current_query": message.question,
            "user_id": current_user.id,
            "session_uuid": message.uuid_name,
        },
        config={
            "configurable": {
                # Each session gets its own isolated LangGraph thread
                "thread_id": message.session_id,
                # User-level namespace for long-term memory store
                "user_id": str(current_user.id),
            }
        }
    )

    answer = result["messages"][-1].content

    db.add(models.messages(role="user", content=message.question, user_id=current_user.id, session_id=message.session_id))
    db.add(models.messages(role="assistant", content=answer, user_id=current_user.id, session_id=message.session_id))
    db.commit()

    return {"answer": answer}


# ─── Legacy messages (all messages for user) ────────────────────────────────

@router.get("/messages")
def messages(db: Session = Depends(get_db), current_user=Depends(current_user)):
    msgs = db.query(models.messages).filter(models.messages.user_id == current_user.id).all()
    return msgs


# ─── Upload PDF ─────────────────────────────────────────────────────────────

@router.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(current_user)
):
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("vectorstore", exist_ok=True)
    os.makedirs("temp_images", exist_ok=True)

    uuid_name = str(uuid.uuid4())
    pdf_path = f"uploads/{current_user.id}_{uuid_name}.pdf"
    persist_dir = f"vectorstore/{current_user.id}_{uuid_name}"

    with open(pdf_path, "wb") as f:
        f.write(await file.read())

    documents = conv_to_doc(pdf_path)
    splited_doc = split_doc(documents)

    vectorstore = Chroma(
        collection_name="chunk_collection",
        persist_directory=persist_dir,
        embedding_function=emb
    )
    vectorstore.add_documents(splited_doc)

    return {"message": "PDF Uploaded Successfully", "chunks": len(documents), "uuid": uuid_name}
