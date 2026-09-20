from pydantic import BaseModel
from typing import Optional , Literal , Annotated

class CreateUser(BaseModel):
    name: str
    email: str
    password: str

class login_user(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    question: str
    uuid_name: str
    session_id: str  # chat session UUID (used as thread_id for LangGraph)

class CreateSession(BaseModel):
    name: Optional[str] = "New Chat"

class classify(BaseModel):
    type: Literal["factual_lookup", "explanation", "emergency_flag"]

class query_rewrites(BaseModel):
    query : str

class responcess(BaseModel):
    answer : str

class is_query_ok(BaseModel):
    is_ok : bool
    reason : str