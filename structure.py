from langgraph.graph import StateGraph , START , END
from state import State
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI as ChatGenAI
import os
import json
from langchain_community.vectorstores import Chroma
from routes import current_user
from langchain_core.messages import SystemMessage , HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel , Field
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from flashrank import Ranker, RerankRequest
from langgraph.checkpoint.postgres import PostgresSaver

load_dotenv('.env')
llm_1 = ChatGroq(model="llama-3.1-8b-instant" , groq_api_key=os.getenv('GROQ_API_KEY_1')) 
llm_2 = ChatGroq(model="llama-3.1-8b-instant" , groq_api_key=os.getenv('GROQ_API_KEY_2'))
llm_3 = ChatGenAI(model="gemini-2.5-flash", google_api_key=os.getenv('GEMINI_API_KEY_1'))


ranker = Ranker()

_checkpointer_ctx = PostgresSaver.from_conn_string(os.getenv("DATABASE_URL"))
checkpointer = _checkpointer_ctx.__enter__()

checkpointer.setup()

emb = HuggingFaceEndpointEmbeddings(
    model="sentence-transformers/all-MiniLM-L6-v2",
    huggingfacehub_api_token=os.getenv("HUGGINGFACE")
)
class responce(BaseModel):
    ans:str
def retrived(state:State):
    vectorstore = Chroma(
        persist_directory=f'vectorstore/{state["user_id"]}_{state["uuid"]}' ,
        embedding_function = emb
    )
    chunk_path = f"chunks/{state['user_id']}_{state['uuid']}.json"
    with open(chunk_path , 'r' , encoding="utf-8") as f:
        data = json.load(f)

    cunk = [
        Document(
            page_content=doc["page_content"],
        )
        for doc in data
    ]

    bm25 = BM25Retriever.from_documents(cunk)
    bm25.k = 3
    
    llm_1_structured = llm_1.with_structured_output(responce)
    query = llm_1_structured.invoke(f'Create a new query from the users query:{state['messages'][-1].content} Make it more relevent towards getting retrived documents of Medical field')
    retirver = vectorstore.as_retriever(search_kwargs={"k": 3})
    docs = retirver.invoke(query.ans)
    chuks = bm25.invoke(query.ans)
    for i, doc in enumerate(docs):
        print("=" * 100)
        print(f"Page {i+1}")
        print(doc.page_content[:1000])

    chunks = []

    total_chunks = docs + chuks

    unique_docs = []
    seen = set()

    for doc in total_chunks:
        if doc.page_content not in seen:
            seen.add(doc.page_content)
            unique_docs.append(doc)


    passages = [
    {
        "id": i,
        "text": doc.page_content
    }
        for i, doc in enumerate(unique_docs)
    ]

    request = RerankRequest(
        query=query.ans,
        passages=passages
    )

    results = ranker.rerank(request)

    chunks = []

    for item in results:
        chunks.append(
            unique_docs[item["id"]].page_content
        )
    return {
        "chunks":chunks 
    }

def final_responce(state:State):
    full_text = '\n'.join(state['chunks'])
    print(full_text)
    responce = llm_2.invoke([
        SystemMessage(content="""You are an experienced medical assistant that helps users understand their medical reports. Your role is to explain medical information in a clear, accurate, and easy-to-understand manner. You are not a substitute for a licensed physician and should not provide a definitive diagnosis.

You will receive:
1. The user's current question.
2. Extracted text from the uploaded medical report (Medical_text).
3. Previous chat history.

Instructions:

1. Always understand the user's current question before generating a response.

2. Use the Medical_text as the primary source of information whenever it contains relevant details.

3. Use the chat history only to maintain context and continuity. Give more importance to recent messages than older ones.

4. If the user's question is general (for example, "What is diabetes?" or "What is HbA1c?"), answer using your medical knowledge while relating it to the uploaded report whenever possible.

5. If the Medical_text does not contain the information needed to answer the question, say so clearly instead of making up information.

6. Never fabricate laboratory values, diagnoses, medications, or report findings.

7. Explain medical terms in simple language so that a non-medical user can understand them.

8. If the report contains abnormal values, explain:
   - what the value means,
   - whether it is low, normal, or high,
   - possible medical significance,
   - common next steps (without making a diagnosis).

9. If the user asks a follow-up question, answer using both the previous conversation and the uploaded report.

10. Keep answers concise but complete. Use bullet points when they improve readability.

11. If the question is unrelated to the uploaded report, answer it normally using your medical knowledge.

Always prioritize:
User Question > Medical Report > Recent Chat History > Older Chat History.
                      """),
        HumanMessage(content=f'Query:{state["messages"][-1].content} \n Medical_text:{full_text} \n chat history:{state["messages"][:-1]}'),
    ])
    return {
        "messages":[responce]
    }


graph = StateGraph(State)

graph.add_node("retrived", retrived)
graph.add_node("final_responce", final_responce)

graph.add_edge(START , "retrived")
graph.add_edge("retrived" , "final_responce")
graph.add_edge("final_responce" , END)

graphh = graph.compile(checkpointer=checkpointer)

