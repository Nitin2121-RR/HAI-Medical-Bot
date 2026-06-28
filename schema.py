from pydantic import BaseModel

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