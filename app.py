from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from chatbot import SmartChatbot
from sqlalchemy.orm import Session
from typing import List, Optional
import uvicorn
import models
import schemas
import auth
from database import engine, get_db
from datetime import datetime, timezone

def get_utc_now():
    return datetime.now(timezone.utc)

# Create the database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart Science Chatbot API",
    description="An API that automatically detects and answers plain science questions or MCQs with User Auth and Session Recording.",
    version="1.2.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify the actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the chatbot once on startup
chatbot = SmartChatbot()

# OAuth2 setup
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# --- Dependency to get current user ---
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = auth.decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username: str = payload.get("sub")
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

# --- Auth Endpoints ---

@app.post("/signup", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(models.User).filter(
        (models.User.username == user.username) | (models.User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Hash password and save user
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        username=user.username,
        email=user.email,
        password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.Token)
def login(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    # Find user by username
    user = db.query(models.User).filter(models.User.username == user_credentials.username).first()
    if not user or not auth.verify_password(user_credentials.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Record login session
    new_session = models.UserSession(user_id=user.id)
    db.add(new_session)
    db.commit()
    
    # Create JWT token
    access_token = auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.post("/logout")
def logout(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Find the most recent active session and set logout time
    last_session = db.query(models.UserSession).filter(
        models.UserSession.user_id == current_user.id,
        models.UserSession.logout_time == None
    ).order_by(models.UserSession.login_time.desc()).first()
    
    if last_session:
        last_session.logout_time = get_utc_now()
        db.commit()
        return {"message": f"User {current_user.username} logged out successfully"}
    return {"message": "No active session found"}

@app.get("/history", response_model=List[schemas.ConversationResponse])
def get_chat_history(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Return list of conversations instead of individual messages
    conversations = db.query(models.Conversation).filter(
        models.Conversation.user_id == current_user.id
    ).order_by(models.Conversation.created_at.desc()).all()
    return conversations

@app.delete("/history")
def clear_chat_history(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Delete all chat history and conversations for the current user
    try:
        db.query(models.ChatHistory).filter(models.ChatHistory.user_id == current_user.id).delete()
        db.query(models.Conversation).filter(models.Conversation.user_id == current_user.id).delete()
        db.commit()
        return {"message": "Chat history cleared successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify the conversation belongs to the user
    conversation = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id,
        models.Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    try:
        # Delete messages first then the conversation
        db.query(models.ChatHistory).filter(models.ChatHistory.conversation_id == conversation_id).delete()
        db.delete(conversation)
        db.commit()
        return {"message": "Conversation deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/conversations/{conversation_id}", response_model=List[schemas.ChatHistoryResponse])
def get_conversation_messages(
    conversation_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify the conversation belongs to the user
    conversation = db.query(models.Conversation).filter(
        models.Conversation.id == conversation_id,
        models.Conversation.user_id == current_user.id
    ).first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
        
    messages = db.query(models.ChatHistory).filter(
        models.ChatHistory.conversation_id == conversation_id
    ).order_by(models.ChatHistory.created_at.asc()).all()
    return messages

# --- Chatbot Endpoints ---

class QuestionRequest(BaseModel):
    question: str
    conversation_id: Optional[int] = None

@app.get("/")
async def root():
    return {"message": "Welcome to the Smart Science Chatbot API. Use /ask to post a question."}

@app.post("/ask")
async def ask_question(
    request: QuestionRequest, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    user_input = request.question.strip()
    conversation_id = request.conversation_id
    
    print(f"DEBUG: /ask received - question: '{user_input}', conversation_id: {conversation_id}")
    
    if not user_input:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    try:
        # 1. Handle/Validate Conversation
        if conversation_id:
            # Ensure it belongs to the user
            conv = db.query(models.Conversation).filter(
                models.Conversation.id == conversation_id,
                models.Conversation.user_id == current_user.id
            ).first()
            if not conv:
                print(f"DEBUG: conversation_id {conversation_id} not found for user {current_user.id}, fallback to new")
                conversation_id = None
            else:
                print(f"DEBUG: Using existing conversation: {conversation_id}")

        if not conversation_id:
            # Create new conversation if none provided or not found
            title = user_input[:50] + ("..." if len(user_input) > 50 else "")
            conv = models.Conversation(user_id=current_user.id, title=title)
            db.add(conv)
            db.commit()
            db.refresh(conv)
            conversation_id = conv.id
            print(f"DEBUG: Created new conversation: {conversation_id} with title: '{title}'")

        # 2. Get model response
        if chatbot.is_mcq(user_input):
            parsed = chatbot.parse_mcq(user_input)
            response = chatbot.get_mcq_response(parsed)
        else:
            response = chatbot.get_plain_response(user_input)
            
        # Ensure response is a dictionary we can modify
        if not isinstance(response, dict):
            response = {"response": str(response), "type": "plain"}

        # 3. Record question and response in ChatHistory
        history_entry = models.ChatHistory(
            user_id=current_user.id,
            conversation_id=conversation_id,
            question=user_input,
            response=response
        )
        db.add(history_entry)
        db.commit()
            
        print(f"DEBUG: Returning response with conversation_id: {conversation_id}")
        # Return the final payload with the conversation_id
        return {
            **response,
            "conversation_id": conversation_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /ask: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- Serve Frontend (Single Container Deployment) ---
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dist):
    # Mount assets so JS/CSS load correctly
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
    
    # Catch-all route to serve the React SPA
    @app.get("/{catchall:path}")
    async def serve_spa(catchall: str):
        file_path = os.path.join(frontend_dist, catchall)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
