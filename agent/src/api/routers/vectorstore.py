from fastapi import APIRouter, Depends, HTTPException
import logging
from api.dependencies import get_current_user, get_vectorstore, get_conversation_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix = "/vectorstore", tags = ["database"])

#DATABASE ENDPOINTS
@router.delete("/delete-project/{project_id}")
async def delete_vectorstore_project_endpoint(project_id: str,
                                            vectorstore = Depends(get_vectorstore),
                                            ):
    """Delete project from BigQuery vector store."""
    try:
        vectorstore.delete_project(project_id)
        logger.info(f"🗑️  Deleted project {project_id} from vector store")
        return {"success": True, "project_id": project_id}
    except Exception as e:
        logger.error(f"Error in /delete-vectorstore-project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting project from vector store: {str(e)}")

@router.delete("/delete-file/{file_id}")
async def delete_vectorstore_file_endpoint(file_id: str,
                                            vectorstore = Depends(get_vectorstore),
                                            ):
    """Delete file from BigQuery vector store."""
    try:
        vectorstore.delete_file(file_id)
        return {"success": True, "file_id": file_id}
    except Exception as e:
        logger.error(f"Error in /delete-vectorstore-file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error deleting file from vector store: {str(e)}")

