from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter


def text_splitter():
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=600,
        chunk_overlap=120
    )


