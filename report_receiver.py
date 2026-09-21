import fitz
import numpy as np
import os
import base64
from rapidocr import RapidOCR
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from PIL import Image
from io import BytesIO
from dotenv import load_dotenv

load_dotenv('.env')

# Gemini vision model — no local download, runs via API

ocr = RapidOCR()
splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)


def page_to_image(page):
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return image


def extract_pdf(pdf_path):
    pdf = fitz.open(pdf_path)
    pages = []

    for page_number, page in enumerate(pdf):
        text = page.get_text("text").strip()

        if text:
            pages.append({
                "page": page_number + 1,
                "text": text,
                "has_visual": len(page.get_images(full=True)) > 0
            })
        else:
            image = page_to_image(page)
            result, _ = ocr(image)
            ocr_text = " ".join(item[1] for item in result) if result else ""
            pages.append({
                "page": page_number + 1,
                "text": ocr_text,
                "has_visual": True
            })

    pdf.close()
    return pages


def conv_to_doc(pdf_path):
    documents = []
    for page in extract_pdf(pdf_path):
        documents.append(Document(
            page_content=page["text"],
            metadata={
                "page": page["page"],
                "has_visual": page["has_visual"],
                "source": pdf_path
            }
        ))
    return documents


def split_doc(documents):
    return splitter.split_documents(documents)


def analyze_visual(image_bytes: bytes) -> str:
    """Send image bytes to Gemini vision and return a text description."""
    vision_model = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        google_api_key=os.getenv("GEMINI_API_KEY_1")
    )
    # Encode to base64 for the Gemini API
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    # Detect mime type from bytes header
    if image_bytes[:4] == b'\x89PNG':
        mime = "image/png"
    elif image_bytes[:2] == b'\xff\xd8':
        mime = "image/jpeg"
    else:
        mime = "image/png"  # safe default

    msg = HumanMessage(content=[
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"}
        },
        {
            "type": "text",
            "text": (
                "Analyze this medical report visual (chart, table, diagram, or image). "
                "Extract all visible values, labels, units, and relationships. "
                "Return concise factual text that can be used to answer patient questions."
            )
        }
    ])

    result = vision_model.invoke([msg])
    # result.content may be a list of blocks in newer langchain-google-genai versions
    content = result.content
    if isinstance(content, list):
        content = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return content


def extract_images_from_page(pdf, page_number):
    page = pdf[page_number - 1]
    images = []
    for img in page.get_images(full=True):
        xref = img[0]
        image_data = pdf.extract_image(xref)
        images.append(image_data["image"])
    return images
