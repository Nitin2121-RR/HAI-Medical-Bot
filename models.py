from sqlalchemy import Column, Integer, String , ForeignKey, DateTime
from sqlalchemy.sql import func
from database import Base


class user(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    name = Column(String, nullable=False)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, nullable=False, index=True)  # UUID string
    name = Column(String, nullable=False, default="New Chat")
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class messages(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True)
    session_id = Column(String, ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=True)


class Documents(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    file_path = Column(String, nullable=False)
    uuid = Column(String, nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True)