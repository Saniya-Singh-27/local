from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from database import Base
from datetime import datetime, timezone
from sqlalchemy.orm import relationship

# Function to get UTC time for both SQLite and Postgres
def get_utc_now():
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)

    # Relationships
    sessions = relationship("UserSession", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")
    chat_history = relationship("ChatHistory", back_populates="user")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)

    user = relationship("User", back_populates="conversations")
    messages = relationship("ChatHistory", back_populates="conversation")

class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    login_time = Column(DateTime, default=get_utc_now)
    logout_time = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="sessions")

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    conversation_id = Column(Integer, ForeignKey("conversations.id"))
    question = Column(String, nullable=False)
    response = Column(JSON, nullable=False)  # Store the full JSON response from model
    created_at = Column(DateTime, default=get_utc_now)

    user = relationship("User", back_populates="chat_history")
    conversation = relationship("Conversation", back_populates="messages")
