from database import get_db
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
import os
from datetime import datetime , timedelta
from jose import JWTError , jwt
from fastapi import Depends , HTTPException , status
from sqlalchemy.orm import Session
import models

load_dotenv('.env')

oauth = OAuth2PasswordBearer('/user/login') 

def create_token(data : dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES')))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, os.getenv('SECRET_KEY'), algorithm=os.getenv('ALGORITHM'))
    return encoded_jwt

def verify_token(token: str, credentials_exception):
    try:
        payload = jwt.decode(token, os.getenv('SECRET_KEY'), algorithms=[os.getenv('ALGORITHM')])
        id: str = payload.get("user_id")
        if id is None:
            raise credentials_exception
        token_data = {"id": id}
    except JWTError:
        raise credentials_exception

    return token_data

def current_user(token: str = Depends(oauth), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = verify_token(token, credentials_exception)
    user = db.query(models.user).filter(models.user.id == token_data['id']).first()
    return user