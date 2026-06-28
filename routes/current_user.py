from fastapi import APIRouter , Depends , Request , File , UploadFile , HTTPException
from sqlalchemy.orm import Session
from database import get_db
from fastapi.templating import Jinja2Templates
from auth import current_user
import models
from schema import ChatRequest
import os
import uuid
import json
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from structure import graphh
from langchain_core.messages import SystemMessage , HumanMessage
from langchain_huggingface import HuggingFaceEndpointEmbeddings 
from dotenv import load_dotenv
import os 
from langchain_core.documents import Document
import shutil
import fitz
from rapidocr_onnxruntime import RapidOCR
load_dotenv('.env')
router = APIRouter(prefix="/current_user" , tags=["Current User"])

template = Jinja2Templates(directory="templates")


emb = HuggingFaceEndpointEmbeddings(
    model="sentence-transformers/all-MiniLM-L6-v2",
    huggingfacehub_api_token=os.getenv("HUGGINGFACE")
)


@router.get('/dashboard')
def current(request: Request , db: Session = Depends(get_db)):
    return template.TemplateResponse(
        request=request,
        name = "dashboard.html"
    )

@router.get('/')
def con(db: Session = Depends(get_db) , current_user = Depends(current_user)):
    name = current_user.name
    email = current_user.email
    return {
        "name": name,
        "email": email
    }

@router.get('/chat')
def chat(request: Request , db: Session = Depends(get_db)):
    return template.TemplateResponse(
        request=request,
        name = "chat.html"
    )

@router.get("/messages")
def messages(db: Session = Depends(get_db) , current_user = Depends(current_user)):
    messages = db.query(models.messages).filter(models.messages.user_id == current_user.id).all()
    return messages

@router.post("/chat")
def chat(message: ChatRequest , db: Session = Depends(get_db) , current_user = Depends(current_user)):
    new_message = models.messages(role="user" , content=message.question , user_id=current_user.id)
    responce = graphh.invoke({
        "messages": [HumanMessage(content=message.question)],
        "user_id": current_user.id,
        "uuid": message.uuid_name 
    },
    config={
        "configurable": {
            "thread_id": str(current_user.id)
        }
    }) 
    responce_message = models.messages(role="assistant" , content=responce['messages'][-1].content , user_id=current_user.id)
    db.add(new_message)
    db.add(responce_message)
    db.commit()
    db.refresh(new_message)
    db.refresh(responce_message)
    return {"answer": responce['messages'][-1].content}


@router.post("/upload-pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(current_user)
):

    
    # ------------------------
    # Create folders
    # ------------------------

    os.makedirs("uploads", exist_ok=True)
    os.makedirs("vectorstore", exist_ok=True)
    os.makedirs("temp_images", exist_ok=True)
    uuid_name = str(uuid.uuid4())
    pdf_path = f"uploads/{current_user.id}_{uuid_name}.pdf"
    persist_dir = f"vectorstore/{current_user.id}_{uuid_name}"


    # ------------------------
    # Save PDF
    # ------------------------

    with open(pdf_path, "wb") as f:
        f.write(await file.read())

    # ------------------------
    # OCR Engine
    # ------------------------

    engine = RapidOCR()

    pdf = fitz.open(pdf_path)
    total_pages = len(pdf)
    full_text = ""

    # ------------------------
    # OCR Every Page
    # ------------------------

    for page_no in range(len(pdf)):

        page = pdf.load_page(page_no)

        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3))

        img_path = f"temp_images/{current_user.id}_{page_no}.png"

        pix.save(img_path)

        result, _ = engine(img_path)

        if result:

            for line in result:

                full_text += line[1] + "\n"

        full_text += "\n\n"

    pdf.close()

    # ------------------------
    # Delete Temp Images
    # ------------------------

    shutil.rmtree("temp_images")
    os.makedirs("temp_images")

    # ------------------------
    # Validate OCR
    # ------------------------

    if len(full_text.strip()) == 0:

        raise HTTPException(
            status_code=400,
            detail="Unable to extract text from PDF."
        )

    print("=" * 100)
    print(full_text[:3000])
    print("=" * 100)

    # ------------------------
    # LangChain Documents
    # ------------------------

    docs = [
        Document(
            page_content=full_text,
            metadata={
                "source": file.filename,
                "user_id": current_user.id
            }
        )
    ]

    # ------------------------
    # Split
    # ------------------------

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    chunks = splitter.split_documents(docs) 

    print(f"Total Chunks : {len(chunks)}")


    #-------------------------
    # Chunks save
    #-------------------------

    chunk_json = [
        {
            "page_content": chunk.page_content,
        }
        for chunk in chunks
    ]
    os.makedirs("chunks" , exist_ok=True)

    
    chunk_path = f"chunks/{current_user.id}_{uuid_name}.json"

    with open(chunk_path, "w" , encoding="utf-8") as f:
        json.dump(chunk_json , f , indent=2 , ensure_ascii=False)

    # ------------------------
    # Chroma
    # ------------------------

    Chroma.from_documents(
        documents=chunks,
        embedding=emb,
        persist_directory=persist_dir
    )

    return {
        "message": "PDF Uploaded Successfully",
        "pages": total_pages,
        "chunks": len(chunks),
        "uuid":uuid_name
    }