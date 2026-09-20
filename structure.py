from langgraph.graph import StateGraph , START , END
from state import State
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI as ChatGenAI
import os
import json
from langchain_chroma import Chroma
from langchain_core.messages import SystemMessage , HumanMessage , AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel , Field
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from flashrank import Ranker, RerankRequest
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from schema import classify , query_rewrites , responcess , is_query_ok
from prompts import CLASSIFY_PROMPT , QUERY_REWRITE_PROMPT , GENERATION_PROMPT , SUMMARIZE_PROMPT , INPUT_SAFETY_CLASSIFIER_PROMPT
from report_receiver import analyze_visual , extract_images_from_page
import fitz

load_dotenv('.env')

llm_2 = ChatGenAI(model="gemini-3.5-flash-lite", google_api_key=os.getenv('GEMINI_API_KEY_2'))
llm_3 = ChatGenAI(model="gemini-3.5-flash-lite", google_api_key=os.getenv('GEMINI_API_KEY_3'))
llm_1 = ChatGenAI(model="gemini-3.5-flash-lite", google_api_key=os.getenv('GEMINI_API_KEY_1'))
_db_url = os.getenv("DATABASE_URL")

# PostgresSaver for short-term per-session checkpoint (thread memory)
_checkpointer_ctx = PostgresSaver.from_conn_string(_db_url)
checkpointer = _checkpointer_ctx.__enter__()
checkpointer.setup()

# PostgresStore for long-term cross-session memory (user-level facts)
_store_ctx = PostgresStore.from_conn_string(_db_url)
store = _store_ctx.__enter__()
store.setup()

ranker = Ranker()

emb = HuggingFaceEndpointEmbeddings(
    model="sentence-transformers/all-MiniLM-L6-v2",
    huggingfacehub_api_token=os.getenv("HUGGINGFACE")
)
def is_query_okk(state:State):
    llm_struct = llm_2.with_structured_output(is_query_ok)
    responce = llm_struct.invoke(INPUT_SAFETY_CLASSIFIER_PROMPT.format(
        chat_history=state["messages"],
        query=state["current_query"]
    ))

    return{
        "safe": responce.is_ok,
        "messages": [SystemMessage(content=responce.reason)]
    }

def classify_query(state:State):
    llm_struct = llm_1.with_structured_output(classify)
    result = llm_struct.invoke(CLASSIFY_PROMPT.format(
        chat_history=state["messages"],
        query=state["current_query"]
    ))
    return {"query_type": result.type}

def emergency_flag(state:State):
    return {
        "messages": [SystemMessage(content="Sorry, but I can't provide information for these aspects. You are suggested to have a proper check-up with a doctor because it seems to be an emergency.")]
    }

def out_of_scope(state:State):
    return {
        "messages": [SystemMessage(content="I can help you understand what's written in your report, but I can't "
        "recommend treatments, medications, or diagnoses — that needs to come "
        "from your doctor. Would you like me to explain a specific part of your "
        "report instead?")]
    }

def query_rewrite(state:State):
    llm_struct = llm_1.with_structured_output(query_rewrites)
    result = llm_struct.invoke(QUERY_REWRITE_PROMPT.format(
        query=state["current_query"],
        chat_history=state["messages"]
    ))
    return {"rewritten_query": result.query}

def visual_chunks(state:State):
    pdf_path = f"uploads/{state['user_id']}_{state['session_uuid']}.pdf"
    chunks = state["retrived_chunks"]
    visual_docs = [doc for doc in chunks if doc.metadata.get("has_visual")]
    vis_doc = []

    if visual_docs:
        pdf = fitz.open(pdf_path)
        for doc in visual_docs:
            images = extract_images_from_page(pdf, doc.metadata["page"])
            for image_bytes in images:
                visual_info = analyze_visual(image_bytes)
                vis_doc.append(Document(
                    page_content=visual_info,
                    metadata={"page": doc.metadata["page"], "source": doc.metadata["source"]}
                ))
    return {"visual_chunk": vis_doc}

def reranking_chunks(state:State):
    persist_dir = f"vectorstore/{state['user_id']}_{state['session_uuid']}"
    vectorstore = Chroma(
        collection_name="chunk_collection",
        persist_directory=persist_dir,
        embedding_function=emb
    )
    retriver = vectorstore.as_retriever(search_kwargs={"k": 5})
    chunks = retriver.invoke(state["rewritten_query"])
    passages = [{"id": str(i), "metadata": doc.metadata, "text": doc.page_content} for i, doc in enumerate(chunks)]
    request = RerankRequest(query=state["rewritten_query"], passages=passages)
    reranked = ranker.rerank(request)
    final_chunks = [Document(page_content=doc["text"], metadata=doc["metadata"]) for doc in reranked[:2]]
    return {"retrived_chunks": final_chunks}

class summ(BaseModel):
    summary: str

def responce(state: State):
    llm_struct_1 = llm_3.with_structured_output(responcess)
    llm_struct_2 = llm_3.with_structured_output(summ)

    state_messages = state["messages"].copy()
    limited_messages = state_messages[-10:]
    current_summary = state.get("message_summery", "")

    if len(state_messages) > 10:
        summary_result = llm_struct_2.invoke(SUMMARIZE_PROMPT.format(
            previous_summary=current_summary,
            full_conversation=state_messages
        ))
        current_summary = summary_result.summary

    result = llm_struct_1.invoke(GENERATION_PROMPT.format(
        summary=current_summary,
        chat_history=limited_messages,
        query=state["current_query"],
        rewritten_query=state["rewritten_query"],
        retrieved_chunks=state.get("retrived_chunks", []),
        visual_chunks=state.get("visual_chunk", [])
    ))

    return {
        "answer": result.answer,
        "message_summery": current_summary,
        "messages": [AIMessage(content=result.answer)]
    }

# Condition
def type_condition(state: State):
    typ = state["query_type"]
    if typ == "emergency_flag":
        return "emergency"
    elif typ == "out_of_scope":
        return "scope_out"
    else:
        return "continue"

def is_safe(state:State):
    if state["safe"]:
        return "safe"
    else:
        return "not_safe"

graph = StateGraph(State)
graph.add_node("is_query_okk", is_query_okk)
graph.add_node("classify_query", classify_query)
graph.add_node("emergency_flag", emergency_flag)
graph.add_node("out_of_scope", out_of_scope)
graph.add_node("query_rewrite", query_rewrite)
graph.add_node("reranking_chunks", reranking_chunks)
graph.add_node("visual_chunks", visual_chunks)
graph.add_node("responce", responce)


graph.add_edge(START, "is_query_okk")
graph.add_conditional_edges("is_query_okk", is_safe, {
    "safe": "classify_query",
    "not_safe": END
})
graph.add_conditional_edges("classify_query", type_condition, {
    "emergency": "emergency_flag",
    "scope_out": "out_of_scope",
    "continue": "query_rewrite"
})
graph.add_edge("query_rewrite", "reranking_chunks")
graph.add_edge("reranking_chunks", "visual_chunks")
graph.add_edge("visual_chunks", "responce")
graph.add_edge("responce", END)
graph.add_edge("emergency_flag", END)
graph.add_edge("out_of_scope", END)

graphh = graph.compile(checkpointer=checkpointer, store=store)