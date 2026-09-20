from typing import List, Optional, Union , TypedDict , Annotated , Literal
from pydantic import BaseModel , Field 
from langchain_core.messages import SystemMessage , HumanMessage , BaseMessage
import operator
from langchain_core.documents import Document
class RetrievedChunk(TypedDict):
    chunk_id: str
    text: str
    page: Optional[int]
    section: Optional[str]      # e.g. "Lab Results", "Impression"
    vector_score: float
    bm25_score: float
    rerank_score: float         # cross-encoder / reranker score
    final_score: float          # fused, post-ranking score

class State(TypedDict):
    # conversation
    messages: Annotated[List[BaseMessage], operator.add]
    message_summery: str
    user_id: int
    session_uuid: str
     
    # per-turn retrieval
    current_query: str
    rewritten_query: str         # after query rewriting/expansion using chat history


    # safety / routing
    query_type: Literal["factual_lookup", "explanation", "out_of_scope", "emergency_flag"]

    # output
    answer: str
    safe: bool

    visual_chunk: List[str]
    retrived_chunks: List[Document]