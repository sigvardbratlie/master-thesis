import json
import requests
import streamlit as st
import logging
from typing import Generator, Callable
from ui.models import *

logger = logging.getLogger(__name__)


class StreamingService:
    """Handles SSE streaming from backend /ask-agent endpoint"""

    def __init__(self, backend_url: str, access_token: str):
        self.backend_url = backend_url
        self.access_token = access_token
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'Authorization': f'Bearer {access_token}'
        }

    def stream_response(
        self,
        request: AskAgentRequest,
        on_token: Callable[[str], None] | None = None,
        on_ai_message: Callable[[StreamEvent], None] | None = None,
        on_tool_result: Callable[[StreamEvent], None] | None = None,
        on_reasoning: Callable[[str], None] | None = None,
        status_callback: Callable[[str, str], None] | None = None
    ) -> Generator[str, None, None]:
        """
        Stream response from backend and invoke callbacks.

        Yields tokens for st.write_stream compatibility.

        Args:
            request: AskAgentRequest model
            on_token: Callback for token events (str) -> None
            on_ai_message: Callback for AI messages (StreamEvent) -> None
            on_tool_result: Callback for tool results (StreamEvent) -> None
            status_callback: Callback for status updates (label: str, state: str) -> None

        Yields:
            Token strings for streaming display
        """
        streaming_started = False

        try:
            with requests.post(
                f'{self.backend_url}/ask-agent',
                json=request.model_dump(),
                stream=True,
                headers=self.headers
            ) as response:
                response.raise_for_status()

                for line in response.iter_lines():
                    if not line:
                        continue

                    decoded_line = line.decode('utf-8')
                    if not decoded_line.startswith('data:'):
                        continue

                    try:
                        data = json.loads(decoded_line[5:])

                        # Handle list wrapper for backward compatibility
                        if isinstance(data, list) and len(data) == 1:
                            data = data[0]

                        if not isinstance(data, dict):
                            st.error(f"Unexpected data format: {type(data)}\n{data}")
                            return

                        event_type = data.get("type")

                        # Handle reasoning events
                        if event_type == "reasoning":
                            content = data.get("data", "")
                            if content and on_reasoning:
                                on_reasoning(content)

                        # Handle token events
                        elif event_type == "token":
                            # Clear status box on first token
                            if not streaming_started and status_callback:
                                status_callback("", "complete")
                                streaming_started = True

                            content = data.get("data", "")
                            if on_token:
                                on_token(content)
                            if content:
                                yield content

                        # Handle AI message events
                        elif event_type == "ai":
                            try:
                                ai_event = StreamEvent(data = AIEventData(**data['data']),
                                                       **{k: data[k] for k in data if k != 'data'})
                                #ai_event = AIEvent(**data)

                                # Add to session messages
                                st.session_state.messages.append(data)

                                # Invoke callback
                                if on_ai_message:
                                    on_ai_message(ai_event)

                                # Update status for tool calls
                                if status_callback and ai_event.data.tool_calls:
                                    for tool_call in ai_event.data.tool_calls:
                                        if tool_call.get("name"):
                                            status_callback(
                                                f"⚙️ Kaller verktøy: {tool_call.get('name')}...",
                                                "running"
                                            )

                            except Exception as e:
                                logger.error(f"Error processing AI event: {e}")
                                st.error(f"Error processing AI event: {e}")

                        # Handle tool result events
                        elif event_type == "tool_result":
                            try:
                                tool_event = StreamEvent(data = ToolResultData(**data['data']),
                                                        **{k: data[k] for k in data if k != 'data'})
                                #tool_event = ToolResultEvent(**data)

                                # Add to session messages
                                st.session_state.messages.append(data)

                                # Invoke callback
                                if on_tool_result:
                                    on_tool_result(tool_event)

                            except Exception as e:
                                logger.error(f"Error processing tool result: {e}")
                                st.error(f"Error processing tool result: {e}")

                    except json.JSONDecodeError as e:
                        st.error(f'JSON decode error: {e}')
                        logger.error(f"JSON decode error: {e}")

        except requests.exceptions.RequestException as e:
            if status_callback:
                status_callback("❌ Feil oppstod", "error")
            st.error(f"En feil oppstod: {e}")
            logger.error(f"Streaming request failed: {e}", exc_info=True)
            raise

    def init_project_stream(self, payload: AskAgentRequest) -> Generator[dict, None, None]:
        """
        Stream status updates from the /init-project endpoint.

        Yields parsed status event dicts as they arrive from the backend SSE stream.
        """
        try:
            with requests.post(
                url=f"{self.backend_url}/init-project",
                json=payload.model_dump(),
                headers=self.headers,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded_line = line.decode('utf-8')
                    if not decoded_line.startswith('data:'):
                        continue
                    try:
                        data = json.loads(decoded_line[5:])
                        logger.debug(f"Init project stream data: {data}")
                        yield data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error in init_project_stream: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in init_project stream: {e}", exc_info=True)
            raise

    def update_project_stream(self, payload: AskAgentRequest) -> Generator[dict, None, None]:
        """
        Stream status updates from the /update-project endpoint.

        Yields parsed status event dicts as they arrive from the backend SSE stream.
        """
        try:
            with requests.post(
                url=f"{self.backend_url}/update-project",
                json=payload.model_dump(),
                headers=self.headers,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded_line = line.decode('utf-8')
                    if not decoded_line.startswith('data:'):
                        continue
                    try:
                        data = json.loads(decoded_line[5:])
                        logger.debug(f"Update project stream data: {data}")
                        yield data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error in update_project_stream: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in update_project stream: {e}", exc_info=True)
            raise

    def update_project_from_session_stream(self, payload: AskAgentRequest) -> Generator[dict, None, None]:
        """
        Stream status updates from the /update-project-from-session endpoint.

        Yields parsed status event dicts as they arrive from the backend SSE stream.
        """
        try:
            with requests.post(
                url=f"{self.backend_url}/update-project-from-session",
                json=payload.model_dump(),
                headers=self.headers,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded_line = line.decode('utf-8')
                    if not decoded_line.startswith('data:'):
                        continue
                    try:
                        data = json.loads(decoded_line[5:])
                        logger.debug(f"Update project from session stream data: {data}")
                        yield data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error in update_project_from_session_stream: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in update_project_from_session stream: {e}", exc_info=True)
            raise

    def cleanup_project_element_stream(self, payload : AskAgentRequest, element_type : str) -> Generator[dict, None, None]:
        """
        Stream status updates from the /cleanup-project-element endpoint.

        Yields parsed status event dicts as they arrive from the backend SSE stream.
        """
        try:
            with requests.post(
                url=f"{self.backend_url}/cleanup-project-element/{element_type}",
                json=payload.model_dump(),
                headers=self.headers,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded_line = line.decode('utf-8')
                    if not decoded_line.startswith('data:'):
                        continue
                    try:
                        data = json.loads(decoded_line[5:])
                        logger.debug(f"Cleanup element stream data: {data}")
                        yield data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error in cleanup_project_element_stream: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in cleanup_project_element stream: {e}", exc_info=True)
            raise

    # def cleanup_factsheet(self, payload : AskAgentRequest):
    #     try:
    #         response = requests.post(
    #         url=f"{self.backend_url}/cleanup-factsheet/",
    #         json=payload.model_dump(),
    #         headers=self.headers,
    #         )
    #         response.raise_for_status()
    #         return response
    #     except requests.exceptions.RequestException as e:
    #         logger.error(f"Error cleaning up factsheet: {e}", exc_info=True)
    #         raise

    def cleanup_attr_stream(self, payload : AskAgentRequest, element_type : str) -> Generator[dict, None, None]:
        try:
            with requests.post(
                url=f"{self.backend_url}/cleanup-project-attr/{element_type}",
                json=payload.model_dump(),
                headers=self.headers,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded_line = line.decode('utf-8')
                    if not decoded_line.startswith('data:'):
                        continue
                    try:
                        data = json.loads(decoded_line[5:])
                        logger.debug(f"Cleanup attr stream data: {data}")
                        yield data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error in cleanup_project_attr_stream: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in cleanup_project_attr stream: {e}", exc_info=True)
            raise
    
    def cleanup_all_metadata_stream(self, payload: AskAgentRequest) -> Generator[dict, None, None]:
        try:
            with requests.post(
                url=f"{self.backend_url}/cleanup-all-metadata",
                json=payload.model_dump(),
                headers=self.headers,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded_line = line.decode('utf-8')
                    if not decoded_line.startswith('data:'):
                        continue
                    try:
                        data = json.loads(decoded_line[5:])
                        logger.debug(f"Cleanup all metadata stream data: {data}")
                        yield data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error in cleanup_all_metadata_stream: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in cleanup_all_metadata_stream: {e}", exc_info=True)
            raise

    def cleanup_elements_stream(self, payload: CleanupElementsRequest) -> Generator[dict, None, None]:
        try:
            with requests.post(
                url=f"{self.backend_url}/cleanup-project-elements",
                json=payload.model_dump(),
                headers=self.headers,
                stream=True,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded_line = line.decode('utf-8')
                    if not decoded_line.startswith('data:'):
                        continue
                    try:
                        data = json.loads(decoded_line[5:])
                        logger.debug(f"Cleanup elements stream data: {data}")
                        yield data
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error in cleanup_elements_stream: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in cleanup_elements_stream: {e}", exc_info=True)
            raise

    def delete_project_vectorstore(self, project_id: str) -> dict:
        """Delete project from BigQuery vector store."""
        try:
            response = requests.delete(
                f'{self.backend_url}/delete-vectorstore-project/{project_id}',
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error deleting project from vector store: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def delete_file_vectorstore(self, file_id: str) -> dict:
        """Delete file from BigQuery vector store."""
        try:
            response = requests.delete(
                f'{self.backend_url}/delete-vectorstore-file/{file_id}',
                headers=self.headers
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error deleting file from vector store: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


@st.cache_resource
def get_streaming_service(backend_url: str, access_token: str) -> StreamingService:
    """Cached StreamingService instance"""
    return StreamingService(backend_url, access_token)

