from fastapi import Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_security = HTTPBearer()

def get_current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(_security)) -> str:
    auth = request.app.state.auth
    return auth.get_current_user(credentials)

def get_agent(request: Request):
    return request.app.state.agent

def get_pm(request: Request):
    return request.app.state.pm

def get_clean(request: Request):
    return request.app.state.clean

def get_config(request: Request):
    return request.app.state.config

def get_vectorstore(request : Request):
    return request.app.state.vectorstore

def get_conversation_manager(request : Request):
    return request.app.state.conversation_manager

def get_gcs(request: Request):
    return request.app.state.gcs

def get_email_parser(request: Request):
    return request.app.state.email_parser