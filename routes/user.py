from fastapi import FastAPI , Request , Depends , APIRouter , HTTPException , status
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from database import get_db
import models
from schema import CreateUser , login_user 
from auth import create_token
from passlib.context import CryptContext


router = APIRouter(prefix='/user' , tags=["User"])
templates = Jinja2Templates(directory="templates")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home.html"
    )

@router.post("/login")
def login(user: login_user , db: Session = Depends(get_db)):
    typed_pass = user.password
    log_user = db.query(models.user).filter(models.user.email == user.email).first()
    if pwd_context.verify(typed_pass , log_user.password) == False:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    token = create_token(data={'user_id': log_user.id})
    if token == None:
        raise HTTPException(status_code=404, detail="Non Authorised")
    return {"access_token": token , "message": "Logged In Successfully"}

@router.get('/create')
def create(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="create.html"
    )

@router.post('/create')
def create(user : CreateUser , db: Session = Depends(get_db)):
    password_hash = pwd_context.hash(user.password)
    user.password = password_hash
    account = models.user(**user.dict())
    db.add(account)
    db.commit()
    db.refresh(account)
    return {"acc": account , "message": "Account Created"}
    
