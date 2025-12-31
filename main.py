from dotenv import load_dotenv
load_dotenv()

import os
import shutil
from uuid import uuid4
from pathlib import Path as _Path
from typing import Optional

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Query,
    Form,
    UploadFile,
    File
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from sqlalchemy.orm import Session
from sqlalchemy import func

from supabase import create_client

import models, schemas, crud, auth
from database import Base, engine, SessionLocal

# --------------------------------------------------
# Environment
# --------------------------------------------------

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("Supabase environment variables are missing")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

BASE_DIR = _Path(__file__).resolve().parent

# --------------------------------------------------
# Database init
# --------------------------------------------------

try:
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created/verified successfully")
except Exception as e:
    print(f"⚠️ Database not reachable at startup: {e}")

# --------------------------------------------------
# App
# --------------------------------------------------

app = FastAPI(title="Home Inventory System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# Dependencies
# --------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --------------------------------------------------
# Frontend pages
# --------------------------------------------------

@app.get("/", include_in_schema=False)
def serve_frontend():
    return FileResponse(BASE_DIR / "index.html")

@app.get("/auth/login-page", include_in_schema=False)
def login_page():
    return FileResponse(BASE_DIR / "static" / "auth.html")

@app.get("/auth/signup-page", include_in_schema=False)
def signup_page():
    return FileResponse(BASE_DIR / "static" / "signup-new.html")

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return HTMLResponse(status_code=204)

app.mount("/static", StaticFiles(directory="static"), name="static")

# --------------------------------------------------
# Auth
# --------------------------------------------------

@app.post("/auth/signup", response_model=schemas.UserOut)
def signup(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = crud.get_user_by_email(db, user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db, user)

@app.post("/auth/login", response_model=schemas.Token)
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = crud.authenticate_user(db, user.email, user.password)
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = auth.create_access_token(data={"sub": db_user.email})
    return {"access_token": token, "token_type": "bearer"}

# --------------------------------------------------
# Items
# --------------------------------------------------

@app.post("/items/", response_model=schemas.ItemOut)
def create_item(
    item: schemas.ItemCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return crud.create_item(db, item, owner_id=current_user.id)

@app.get("/items/", response_model=list[schemas.ItemOut])
def read_items(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return crud.get_items(db, owner_id=current_user.id)

@app.get("/items/{item_id}", response_model=schemas.ItemOut)
def read_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    item = crud.get_item(db, item_id, owner_id=current_user.id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.put("/items/{item_id}", response_model=schemas.ItemOut)
def update_item(
    item_id: int,
    item: schemas.ItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return crud.update_item(db, item_id, item)

@app.delete("/items/{item_id}")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    crud.delete_item(db, item_id, owner_id=current_user.id)
    return {"message": "Item deleted"}

# --------------------------------------------------
# Upload image → Supabase Storage
# --------------------------------------------------

@app.post("/items/{item_id}/upload-image", response_model=schemas.ItemOut)
def upload_item_image(
    item_id: int,
    file: UploadFile = File(...),
    image_name: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Ensure item belongs to user
    item = crud.get_item(db, item_id, owner_id=current_user.id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Generate filename
    ext = _Path(file.filename).suffix
    filename = f"{uuid4().hex}{ext}"

    # Read file bytes
    file_bytes = file.file.read()

    # Upload to Supabase Storage (NO result.get())
    supabase.storage.from_("uploads").upload(
        path=filename,
        file=file_bytes,
        file_options={
            "content-type": file.content_type or "application/octet-stream"
        },
    )

    # Build public URL
    image_path = f"{SUPABASE_URL}storage/v1/object/public/uploads/{filename}"

    # Save in DB
    updated_item = crud.attach_image_to_item(
        db,
        item_id,
        image_name or file.filename,
        image_path,
        owner_id=current_user.id
    )

    return updated_item

# --------------------------------------------------
# Search / filters
# --------------------------------------------------

@app.get("/search/", response_model=list[schemas.ItemOut])
def search_items(
    q: Optional[str] = Query(None),
    mode: str = Query("text"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return crud.search_items(
        db,
        q,
        owner_id=current_user.id,
        mode=mode
    )

@app.get("/rooms/list")
def list_rooms(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    rows = (
        db.query(models.Item.room, func.count(models.Item.id))
        .filter(models.Item.owner_id == current_user.id)
        .group_by(models.Item.room)
        .all()
    )
    return [{"name": r[0], "count": r[1]} for r in rows if r[0]]

@app.get("/categories/list")
def list_categories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    rows = (
        db.query(models.Item.category, func.count(models.Item.id))
        .filter(models.Item.owner_id == current_user.id)
        .group_by(models.Item.category)
        .all()
    )
    return [{"name": r[0], "count": r[1]} for r in rows if r[0]]

@app.get("/items/by-category/{category}", response_model=list[schemas.ItemOut])
def get_items_by_category(
    category: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Item).filter(
        models.Item.owner_id == current_user.id,
        models.Item.category == category
    ).all()

@app.get("/items/by-room/{room}", response_model=list[schemas.ItemOut])
def get_items_by_room(
    room: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    return db.query(models.Item).filter(
        models.Item.owner_id == current_user.id,
        models.Item.room == room
    ).all()
