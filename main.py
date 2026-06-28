from fastapi import FastAPI , Request , Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import get_db
import models
from schema import CreateUser 
from routes import user , current_user

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

app.include_router(user.router)
app.include_router(current_user.router)
