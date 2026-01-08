import json
import requests
import streamlit as st
import logging
from typing import Generator, Callable, Optional
from ui.models import AskAgentRequest, AIEvent, ToolResultEvent

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
        on_token: Optional[Callable[[str], None]] = None,
        on_ai_message: Optional[Callable[[AIEvent], None]] = None,
        on_tool_result: Optional[Callable[[ToolResultEvent], None]] = None,
        status_callback: Optional[Callable[[str, str], None]] = None
    ) -> Generator[str, None, None]:
        """
        Stream response from backend and invoke callbacks.

        Yields tokens for st.write_stream compatibility.

        Args:
            request: AskAgentRequest model
            on_token: Callback for token events (str) -> None
            on_ai_message: Callback for AI messages (AIEvent) -> None
            on_tool_result: Callback for tool results (ToolResultEvent) -> None
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

                if response.status_code != 200:
                    st.error(f'Error when asking agent: {response.text}, {response.status_code}')
                    return

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

                        # Handle token events
                        if event_type == "token":
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
                                ai_event = AIEvent(**data)

                                # Add to session messages
                                st.session_state.messages.append(data)

                                # Invoke callback
                                if on_ai_message:
                                    on_ai_message(ai_event)

                                # Update status for tool calls
                                if status_callback and ai_event.data.tool_calls:
                                    for tool_call in ai_event.data.tool_calls:
                                        if tool_call.name:
                                            status_callback(
                                                f"⚙️ Kaller verktøy: {tool_call.name}...",
                                                "running"
                                            )

                            except Exception as e:
                                logger.error(f"Error processing AI event: {e}")
                                st.error(f"Error processing AI event: {e}")

                        # Handle tool result events
                        elif event_type == "tool_result":
                            try:
                                tool_event = ToolResultEvent(**data)

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
            logger.error(f"Streaming request failed: {e}")
            raise
