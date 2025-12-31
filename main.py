from dotenv import load_dotenv
load_dotenv()
import os
from fastapi import FastAPI, Depends, HTTPException, Query, Form
from fastapi import UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import Base, engine, SessionLocal
import models, schemas, crud
import auth
from typing import Optional
import shutil
from uuid import uuid4
from pathlib import Path as _Path
from supabase_client import supabase

# project base directory
BASE_DIR = _Path(__file__).resolve().parent

# Create all tables (with error handling for network issues)
try:
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created/verified successfully")
except Exception as db_error:
    print(f"⚠️  Warning: Could not connect to database: {db_error}")
    print("    Continuing without database for now (network/DNS issue)")

app = FastAPI(title="Home Inventory System", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# AUTH PAGES
@app.get("/auth/login-page", include_in_schema=False)
def login_page():
    return FileResponse(BASE_DIR / "static" / "auth.html")


@app.get("/auth/signup-page", include_in_schema=False)
def signup_page():
    return FileResponse(BASE_DIR / "static" / "signup-new.html")

# Serve Frontend (root index.html in project root)
@app.get("/", include_in_schema=False)
def serve_frontend():
    index_path = BASE_DIR / "index.html"
    if not index_path.exists():
        raise RuntimeError(f"index.html not found at {index_path}")
    return FileResponse(str(index_path))

# Mount static files so uploads and other assets are served
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post("/auth/signup", response_model=schemas.UserOut)
def signup(user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    try:
        existing = crud.get_user_by_email(db, user_in.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        user = crud.create_user(db, user_in)
        return user
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        if "could not translate host name" in str(e) or "Name or service not known" in str(e):
            raise HTTPException(status_code=503, detail="Database connection unavailable - check network connectivity to Supabase")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.post("/auth/login", response_model=schemas.Token)
def login(user_login: schemas.UserLogin, db: Session = Depends(get_db)):
    try:
        user = crud.authenticate_user(db, user_login.email, user_login.password)
        if not user:
            raise HTTPException(status_code=401, detail="Incorrect email or password")
        access_token = auth.create_access_token(data={"sub": user.email})
        return {"access_token": access_token, "token_type": "bearer"}
    except Exception as e:
        if "could not translate host name" in str(e) or "Name or service not known" in str(e):
            raise HTTPException(status_code=503, detail="Database connection unavailable - check network connectivity to Supabase")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# Fix favicon error
@app.get("/favicon.ico")
async def favicon():
    return HTMLResponse(status_code=204)

# Search Endpoint (text or image mode)
@app.get("/search/", response_model=list[schemas.ItemOut])
def search_items(
    q: str | None = Query(None, description="Search term for finding items"),
    mode: str = Query('text', description="Search mode: 'text' or 'image'"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if mode not in ('text', 'image'):
        raise HTTPException(status_code=400, detail="Invalid search mode")
    if mode == 'text' and (not q or len(q.strip()) == 0):
        raise HTTPException(status_code=400, detail="Search term cannot be empty for text mode")
    results = crud.search_items(db, q.strip() if q else None, owner_id=current_user.id, mode=mode)
    return results

# Get all unique rooms
@app.get("/rooms/list")
def get_all_rooms(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Get all unique room names with item counts"""
    rooms = db.query(
        models.Item.room,
        func.count(models.Item.id).label('count')
    ).filter(models.Item.owner_id == current_user.id).group_by(models.Item.room).all()
    
    return [{"name": room[0], "count": room[1]} for room in rooms]

# Get all unique categories
@app.get("/categories/list")
def get_all_categories(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Get all unique categories with item counts"""
    categories = db.query(
        models.Item.category,
        func.count(models.Item.id).label('count')
    ).filter(models.Item.category.isnot(None)).filter(models.Item.owner_id == current_user.id).group_by(models.Item.category).all()
    
    return [{"name": cat[0], "count": cat[1]} for cat in categories if cat[0]]


@app.get("/images/", response_model=list[schemas.ItemOut])
def list_images(db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Return all items for current user that have images (for image-based search/gallery)"""
    return crud.search_items(db, owner_id=current_user.id, mode='image')

# Get items by room
@app.get("/items/by-room/{room_name}", response_model=list[schemas.ItemOut])
def get_items_by_room(room_name: str, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Get all items in a specific room for the current user"""
    items = db.query(models.Item).filter(models.Item.room == room_name, models.Item.owner_id == current_user.id).all()
    return items

# Get items by category
@app.get("/items/by-category/{category_name}", response_model=list[schemas.ItemOut])
def get_items_by_category(category_name: str, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    """Get all items in a specific category for the current user"""
    items = db.query(models.Item).filter(models.Item.category == category_name, models.Item.owner_id == current_user.id).all()
    return items

# Item Endpoints
@app.post("/items/", response_model=schemas.ItemOut)
def create_item(item: schemas.ItemCreate, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    owner_id = getattr(current_user, 'id', None)
    return crud.create_item(db, item, owner_id=owner_id)

@app.get("/items/", response_model=list[schemas.ItemOut])
def read_items(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    return crud.get_items(db, owner_id=current_user.id, skip=skip, limit=limit)

@app.get("/items/{item_id}", response_model=schemas.ItemOut)
def read_item(item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    db_item = crud.get_item(db, item_id, owner_id=current_user.id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    return db_item

@app.post("/items/{item_id}/upload-image", response_model=schemas.ItemOut)
def upload_item_image(
    item_id: int,
    file: UploadFile = File(...),
    image_name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Upload an image for an existing item.
    Stores the file in Supabase Storage (bucket: uploads)
    and saves the public URL in the database.
    """

    # 1️⃣ Generate safe unique filename
    original_name = image_name or file.filename or "image"
    ext = _Path(file.filename or "").suffix
    filename = f"{uuid4().hex}{ext}"

    # 2️⃣ Read file bytes
    file_bytes = file.file.read()
    file.file.close()

    # 3️⃣ Upload to Supabase Storage
    result = supabase.storage.from_("uploads").upload(
        path=filename,
        file=file_bytes,
        file_options={
            "content-type": file.content_type or "application/octet-stream"
        },
    )

    if result.get("error"):
        raise HTTPException(
            status_code=500,
            detail=f"Supabase upload failed: {result['error']}",
        )

    # 4️⃣ Get public URL
    public_url = supabase.storage.from_("uploads").get_public_url(filename)

    # 5️⃣ Save image info in DB (ownership enforced)
    item = crud.attach_image_to_item(
        db=db,
        item_id=item_id,
        image_name=original_name,
        image_path=public_url,
        owner_id=current_user.id,
    )

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    return item


@app.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(auth.get_current_user)):
    db_item = crud.delete_item(db, item_id, owner_id=current_user.id)
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    return {"message": "Item deleted"}