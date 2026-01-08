# src/auth.py
#import os
#import bcrypt
from google.cloud import firestore
from google.auth.transport import requests as google_requests
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
from google.oauth2 import id_token
from datetime import datetime, timedelta
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

class TokenData(BaseModel):
    user_id: Optional[str] = None

class GoogleAuth:
    def __init__(self, db, secret_key, algorithm = "HS256", access_token_expire_minutes = 60 * 24):
        self.db = db
        self.users_ref = db.collection("users")
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.access_token_expire_minutes = access_token_expire_minutes

    def create_access_token(self, data: dict,
                            expires_delta: Optional[timedelta] = None,
                            ) -> str:
        """Lager en ny JWT-token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now() + expires_delta
        else:
            expire = datetime.now() + timedelta(minutes=self.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    # def verify_google_token(self, token: str) -> dict:
    #     """
    #     Verifiserer ID-tokenet fra Google og returnerer brukerinformasjon.
    #     """
    #     try:
    #         # Verifiser tokenet
    #         idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), os.getenv("GOOGLE_CLIENT_ID"))
    #         return idinfo
    #     except ValueError as e:
    #         # Tokenet er ugyldig
    #         raise ValueError(f"Invalid Google token: {e}")

    def get_or_create_user(self, google_user_info: dict) -> str:
        """
        Finner en bruker basert på Google User ID, eller oppretter en ny hvis den ikke finnes.
        Returnerer appens interne user_id (dokument-ID i Firestore).
        """
        google_user_id = google_user_info['sub']

        # Sjekk om brukeren allerede finnes
        query = self.users_ref.where('google_user_id', '==', google_user_id).limit(1)
        existing_users = list(query.stream())

        if existing_users:
            # Brukeren finnes, returner ID-en
            user_doc = existing_users[0]
            return user_doc.id
        else:
            # Opprett en ny bruker
            new_user_data = {
                'google_user_id': google_user_id,
                'email': google_user_info.get('email'),
                'name': google_user_info.get('name'),
                'picture': google_user_info.get('picture'),
                'created_at': firestore.SERVER_TIMESTAMP
            }
            update_time, user_ref = self.users_ref.add(new_user_data)
            return user_ref.id

    class GoogleToken(BaseModel):
        token: str
    oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

    async def get_current_user(self, token : str = Depends(oauth2_scheme)):
        credentials_exception = HTTPException(status_code = status.HTTP_401_UNAUTHORIZED,
                                            detail = "Could not validate credentials",
                                            headers = {"WWW-Authenticate" : "bearer"})
        try:
            payload = jwt.decode(token,self.secret_key,algorithms=[self.algorithm])
            user_id : str = payload.get("sub")
            if user_id is None:
                raise credentials_exception
            return user_id
        except Exception as e:
            print(f"Error occurred while decoding JWT: {e}")
            raise e

