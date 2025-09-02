from pydantic import BaseModel
from typing import Optional


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenRefresh(BaseModel):
    refresh_token: str


class GoogleAuthRequest(BaseModel):
    code: str


class GoogleAuthURL(BaseModel):
    auth_url: str