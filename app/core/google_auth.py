from typing import Optional, Dict, Any
from authlib.integrations.httpx_client import AsyncOAuth2Client
from app.config import settings
import httpx


class GoogleAuth:
    """Google OAuth 2.0 authentication handler"""
    
    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USER_INFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"
    
    def __init__(self):
        self.client_id = settings.GOOGLE_CLIENT_ID
        self.client_secret = settings.GOOGLE_CLIENT_SECRET
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI
    
    def get_auth_url(self, state: Optional[str] = None) -> str:
        """Get Google OAuth authorization URL"""
        client = AsyncOAuth2Client(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            scope="openid email profile"
        )
        
        authorization_url, _ = client.create_authorization_url(
            self.GOOGLE_AUTH_URL,
            state=state,
            access_type="offline",
            prompt="consent"
        )
        
        return authorization_url
    
    async def get_token(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code"
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get token: {response.text}")
            
            return response.json()
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from Google"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.GOOGLE_USER_INFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get user info: {response.text}")
            
            return response.json()
    
    async def authenticate(self, code: str) -> Dict[str, Any]:
        """Complete OAuth flow and return user info"""
        # Exchange code for token
        token_data = await self.get_token(code)
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise Exception("No access token received")
        
        # Get user info
        user_info = await self.get_user_info(access_token)
        
        return {
            "email": user_info.get("email"),
            "full_name": user_info.get("name"),
            "google_id": user_info.get("id"),
            "picture": user_info.get("picture"),
            "access_token": access_token,
            "refresh_token": token_data.get("refresh_token")
        }


google_auth = GoogleAuth()