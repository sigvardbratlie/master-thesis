import os 
import logging
from utils import AppConfig
from models import AttachmentModel
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class BaseStorageManager:
    def __init__(self, config : AppConfig):
        self.config = config

    @abstractmethod
    def save_attachment(self, 
                        content: bytes, 
                        path : str, 
                        metadata : dict = None) -> str | None:
        pass

    @abstractmethod
    async def save_raw_documents(self, 
                                 attachments: list[AttachmentModel], 
                                 ) -> bool:
        pass

    @abstractmethod
    def read_attachment(self, path : str) -> bytes:
        pass

    @abstractmethod
    def read_attachments(self, paths: list[str]) -> dict[str, bytes | None]:
        pass

    @abstractmethod
    def delete_attachment(self, path : str) -> None:
        pass

    