from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.schemas.auth import Token, TokenRefresh, GoogleAuthRequest, GoogleAuthURL
from app.core.auth import authenticate_user, create_user, get_user_by_email
from app.core.security import create_token_response, decode_token
from app.core.google_auth import google_auth
from app.config import settings
import uuid

router = APIRouter()


@router.post("/register", response_model=Token)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register new user with email and password"""
    print(f"DEBUG: Registration attempt for email: {user_data.email}")
    
    # Check if user exists
    existing_user = await get_user_by_email(db, user_data.email)
    if existing_user:
        print(f"DEBUG: User already exists: {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    print(f"DEBUG: Creating new user for email: {user_data.email}")
    
    # Create new user
    user = await create_user(
        db=db,
        email=user_data.email,
        password=user_data.password,
        full_name=user_data.full_name,
        is_verified=True,  # Auto-verify for development
        plan=user_data.plan or "basic"
    )
    
    print(f"DEBUG: User created successfully with ID: {user.id}")
    
    # Generate tokens
    tokens = create_token_response(str(user.id), user.email)
    
    print(f"DEBUG: Tokens generated for user: {user.email}")
    
    # TODO: Send verification email
    
    return tokens


@router.post("/login", response_model=Token)
async def login(
    user_credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login with email and password"""
    user = await authenticate_user(db, user_credentials.email, user_credentials.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    # Generate tokens
    tokens = create_token_response(str(user.id), user.email)
    
    return tokens


@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: TokenRefresh,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token"""
    # Decode refresh token
    payload = decode_token(token_data.refresh_token)
    
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_id = payload.get("sub")
    email = payload.get("email")
    
    if not user_id or not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Generate new tokens
    tokens = create_token_response(user_id, email)
    
    return tokens


@router.get("/google", response_model=GoogleAuthURL)
async def google_login():
    """Get Google OAuth login URL"""
    auth_url = google_auth.get_auth_url()
    return {"auth_url": auth_url}


@router.post("/google", response_model=Token)
async def google_callback(
    auth_data: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db)
):
    """Handle Google OAuth callback"""
    try:
        # Authenticate with Google
        user_info = await google_auth.authenticate(auth_data.code)
        
        if not user_info.get("email"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not provided by Google"
            )
        
        # Get or create user (simplified - no OAuth account tracking)
        user = await get_user_by_email(db, user_info["email"])
        if not user:
            user = await create_user(
                db=db,
                email=user_info["email"],
                full_name=user_info.get("full_name"),
                is_verified=True  # OAuth users are pre-verified
            )
        
        # Generate tokens
        tokens = create_token_response(str(user.id), user.email)
        
        return tokens
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google authentication failed: {str(e)}"
        )


@router.get("/google/callback")
async def google_callback_redirect(
    code: str,
    state: str = None,
    db: AsyncSession = Depends(get_db)
):
    """Handle Google OAuth redirect (for browser flow)"""
    try:
        # Authenticate with Google
        user_info = await google_auth.authenticate(code)
        
        # Get or create user (simplified - no OAuth account tracking)
        user = await get_user_by_email(db, user_info["email"])
        if not user:
            user = await create_user(
                db=db,
                email=user_info["email"],
                full_name=user_info.get("full_name"),
                is_verified=True  # OAuth users are pre-verified
            )
        
        # Generate tokens
        tokens = create_token_response(str(user.id), user.email)
        
        # Redirect to frontend with tokens
        redirect_url = f"{settings.FRONTEND_URL}/auth/callback"
        redirect_url += f"?access_token={tokens['access_token']}"
        redirect_url += f"&refresh_token={tokens['refresh_token']}"
        
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        # Redirect to frontend with error
        error_url = f"{settings.FRONTEND_URL}/auth/error?message={str(e)}"
        return RedirectResponse(url=error_url)


@router.post("/logout")
async def logout(response: Response):
    """Logout user (client should remove tokens)"""
    # In a more complex setup, you might want to blacklist the token
    return {"message": "Successfully logged out"}