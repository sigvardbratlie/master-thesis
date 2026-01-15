from google.cloud import firestore
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

class TokenData(BaseModel):
    user_id: Optional[str] = None

class GoogleToken(BaseModel):
        token: str

class BaseAuth:
    def __init__(self, 
                 secret_key, 
                 algorithm = "HS256", 
                 access_token_expire_minutes = 60 * 24, 
                 ):
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


class GoogleAuth(BaseAuth):
    def __init__(self, 
                 secret_key, 
                 algorithm = "HS256", 
                 access_token_expire_minutes = 60 * 24, 
                 ):
        super().__init__(secret_key, algorithm, access_token_expire_minutes)

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

