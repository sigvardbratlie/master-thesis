import os
import logging
from models.api_request_models import *
from fastapi import FastAPI,HTTPException,status,Depends
from supabase import create_client, Client
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


logger = logging.getLogger(__name__)


# Define security at module level so FastAPI can access it
security = HTTPBearer()

class SupabaseAuth:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.url, self.key)
        # Initialize Supabase client here if needed

    
    # AUTH #
    def get_current_user(self, token: HTTPAuthorizationCredentials = Depends(security)) -> str:
        """
        Verify token and get user ID from Supabase.
        
        Args:
            token: HTTPAuthorizationCredentials automatically extracted from 
                   'Authorization: Bearer <token>' header by FastAPI
        
        Returns:
            user_id as string
        """
        try:
            # token.credentials gives you the actual token string
            response = self.supabase.auth.get_user(token.credentials)
            logger.debug('🔐 User auth OK')
            return response.user.id
        except Exception as e:
            logger.exception(f'❌ Auth failed')
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    

