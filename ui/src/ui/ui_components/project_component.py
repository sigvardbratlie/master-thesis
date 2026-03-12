import streamlit as st
from uuid import uuid4
from ui.utils import init_state
import logging
from ui.models import *
from ui.ui_components.attachments import AttachmentComponent, get_attachment_component
from ui.services import get_streaming_service, get_supabase_manager
from .utils_component import _render_project_stream_progress

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProjectComponent:
    def __init__(self):
        # self.streaming_service = get_streaming_service(
        #             st.session_state.backend_url,
        #             st.session_state.access_token
        #         )
        self.backend_service = get_supabase_manager()
        self.attachment_component = get_attachment_component()

    def _handle_duplicate_files(self, new_attachments: list) -> list:
        """
        Handle duplicate filenames in project uploads.
        Returns filtered list of attachments based on user choices.
        """
        if not st.session_state.get("project_id") or not new_attachments:
            return new_attachments
        
        streaming_service = get_streaming_service(
            backend_url=st.session_state.backend_url,
            access_token=st.session_state.access_token
        )
        
        # Get existing filenames
        existing_files = {att.get("filename"): att for att in st.session_state.get("attachments", [])}
        
        # Find duplicates
        duplicates = []
        seen_uploads = {}
        
        for att in new_attachments:
            if att.filename in existing_files:
                duplicates.append({
                    "filename": att.filename,
                    "type": "existing",
                    "existing": existing_files[att.filename],
                    "new": att
                })
            elif att.filename in seen_uploads:
                duplicates.append({
                    "filename": att.filename,
                    "type": "multiple_upload",
                    "first": seen_uploads[att.filename],
                    "new": att
                })
            else:
                seen_uploads[att.filename] = att
        
        if not duplicates:
            return new_attachments
        
        # Show duplicate handler UI
        st.warning(f"⚠️ Found {len(duplicates)} duplicate filename(s)")
        
        with st.expander("⚠️ Handle duplicate files", expanded=True):
            st.markdown("**Choose how to handle each duplicate:**")
            
            # Initialize choices
            if "duplicate_choices" not in st.session_state:
                st.session_state.duplicate_choices = {}
            
            for i, dup in enumerate(duplicates):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    if dup["type"] == "existing":
                        st.markdown(f"**📄 {dup['filename']}**  \n🔄 Already exists in project")
                    else:
                        st.markdown(f"**📄 {dup['filename']}**  \n🔄 Uploaded multiple times")
                
                with col2:
                    choice = st.selectbox(
                        "Action:",
                        options=["Keep both", "Replace existing", "Skip new"],
                        key=f"dup_choice_{i}_{dup['filename']}",
                        label_visibility="collapsed"
                    )
                    st.session_state.duplicate_choices[dup['filename']] = choice
        
        # Process attachments based on choices
        filtered = []
        duplicate_names = {d["filename"] for d in duplicates}
        
        for att in new_attachments:
            if att.filename not in duplicate_names:
                # No duplicate - keep it
                filtered.append(att)
                continue
            
            choice = st.session_state.duplicate_choices.get(att.filename, "Keep both")
            
            if choice == "Keep both":
                # Rename new file
                name, ext = (att.filename.rsplit('.', 1) if '.' in att.filename 
                           else (att.filename, ''))
                att.filename = f"{name}_copy.{ext}" if ext else f"{name}_copy"
                filtered.append(att)
                
            elif choice == "Replace existing":
                # Delete old file from storage, database, and vector store
                existing = existing_files.get(att.filename)
                if existing:
                    file_id = existing.get("file_id")
                    path = existing.get("path")
                    
                    # Delete from Supabase (storage + database)
                    if path:
                        self.backend_service.delete_project_file(path)
                    
                    # Delete from vector store
                    if file_id:
                        streaming_service.delete_file_vectorstore(file_id)
                    
                    logger.info(f"Replaced file {att.filename} (deleted old: {file_id})")
                
                filtered.append(att)
            
            # "Skip new" - don't add to filtered list
        
        return filtered

    def clean_element(self,):
        streaming_service = get_streaming_service(backend_url=st.session_state.backend_url,
                                                  access_token=st.session_state.access_token)

        # Popover only collects selections and stores them — streaming happens outside
        with st.popover("Clean and update project element"):
            relational_options = ["Events", "Parties", "Claims", "Damages", "Deadlines"]
            metadata_options = ["Title", "Background", "All Metadata"]
            custom_law_options = ["Governing Law", "Disputed Facts", "Undisputed Facts"]

            selected_relational = st.multiselect("Relational elements", options=relational_options, key="ce_relational")
            selected_metadata = st.selectbox("Metadata", options=["—"] + metadata_options, key="ce_metadata")
            selected_law = st.selectbox("Legal attributes", options=["—"] + custom_law_options, key="ce_law")

            if st.button("Clean selected", icon="🧹"):
                # Save selections before popover closes and resets widget state
                st.session_state["ce_trigger"] = {
                    "relational": list(selected_relational),
                    "metadata": selected_metadata,
                    "law": selected_law,
                }
                st.rerun()

        # Process OUTSIDE the popover so st.status is visible
        trigger = st.session_state.pop("ce_trigger", None)
        if not trigger:
            return

        payload = AskAgentRequest(
            project_id=st.session_state.project_id,
            session_id=st.session_state.session_id,
            attachments=[],
            question="",
            query_id=str(uuid4()),
            llm_model=st.session_state.llm_model,
        )
        rerun_needed = False

        # --- Relational elements (any subset) ---
        if trigger["relational"]:
            element_types = [e.lower() for e in trigger["relational"]]
            elements_payload = CleanupElementsRequest(
                **payload.model_dump(),
                element_types=element_types,
            )
            success = self._stream_cleanup_progress(
                streaming_service.clean_elements_stream, elements_payload
            )
            if success:
                for field in element_types:
                    st.session_state.factsheet[field] = self.backend_service.load_project_element(
                        project_id=st.session_state.project_id, element_type=field
                    )
                rerun_needed = True

        # --- Metadata ---
        if trigger["metadata"] != "—":
            if trigger["metadata"] == "All Metadata":
                success = self._stream_cleanup_progress(
                    streaming_service.clean_metadata_stream, payload
                )
                if success:
                    for field in ["title", "background"]:
                        st.session_state.factsheet[field] = self.backend_service.load_project_element(
                            project_id=st.session_state.project_id, element_type=field
                        )
                    rerun_needed = True
            else:
                element_key = trigger["metadata"].lower()
                success = self._stream_cleanup_progress(
                    streaming_service.cleanup_attr_stream, payload, element_key
                )
                if success:
                    st.session_state.factsheet[element_key] = self.backend_service.load_project_element(
                        project_id=st.session_state.project_id, element_type=element_key
                    )
                    rerun_needed = True

        # --- Legal attributes ---
        if trigger["law"] != "—":
            element_key_map = {
                "Disputed Facts": "disputed_facts",
                "Undisputed Facts": "undisputed_facts",
            }
            element_key = element_key_map.get(trigger["law"], trigger["law"].lower().replace(" ", "_"))
            success = self._stream_cleanup_progress(
                streaming_service.cleanup_attr_stream, payload, element_key
            )
            if success:
                st.session_state.factsheet[element_key] = self.backend_service.load_project_element(
                    project_id=st.session_state.project_id, element_type=element_key
                )
                rerun_needed = True

        if rerun_needed:
            st.rerun()

    def _stream_cleanup_progress(self, streaming_function: callable, payload, element_type: str = None):
        """Display live streaming progress for cleanup operation."""
        label = element_type or "elements"
        with st.status(f"🧹 Cleaning {label}...", expanded=True) as status:
            try:
                stream = streaming_function(payload) if element_type is None else streaming_function(payload, element_type)
                for event in stream:
                    if event.get("error"):
                        status.update(label="❌ Error occurred", state="error")
                        st.error(event["error"])
                        return False

                    phase_raw = event.get("phase", "")
                    phase = phase_raw[0] if isinstance(phase_raw, list) else phase_raw
                    event_status = event.get("status", "")
                    data = event.get("data", {})

                    if phase.startswith("cleanup_"):
                        element = phase[len("cleanup_"):]
                        emoji, phase_label = "🧹", f"Cleaning {element}"
                    elif phase == "storage":
                        emoji, phase_label = "💾", "Saving to database"
                    else:
                        emoji, phase_label = "⏳", phase

                    if event_status == "starting":
                        status.update(label=f"{emoji} {phase_label}...")
                        original = data.get("original_count", 0)
                        if original:
                            st.caption(f"📋 {original} {data.get('element_type', label)} to process")

                    elif event_status == "complete":
                        detail = ""
                        if phase.startswith("cleanup_"):
                            original = data.get("original_count", 0)
                            cleaned = data.get("cleaned_count", 0)
                            removed = data.get("removed", 0)
                            if original or cleaned:
                                detail = f": {cleaned} kept, {removed} removed (from {original})"
                        st.markdown(f"✅ {phase_label}{detail}")

                status.update(label=f"✅ Done!", state="complete")
                return True

            except Exception as e:
                status.update(label="❌ Error during cleanup", state="error")
                st.error(str(e))
                logger.error(f"Error during cleanup progress: {e}", exc_info=True)
                return False

    # def clean_factsheet(self,):
    #     streaming_service = get_streaming_service(backend_url=st.session_state.backend_url,
    #                                               access_token=st.session_state.access_token)
    #     if st.button("Clean Factsheet", icon="🧹"):
    #         response = streaming_service.cleanup_factsheet(
    #             AskAgentRequest(
    #                 project_id=st.session_state.project_id,
    #                 session_id=st.session_state.session_id,
    #                 attachments=[],
    #                 question="",
    #                 query_id=str(uuid4()),
    #                 llm_model=st.session_state.llm_model,
    #             ),
    #         )
    #         if response.status_code == 200 and response.json().get("success") == True:
    #             response_json = response.json()
    #             st.session_state.factsheet = response_json.get('data')
    #             st.success(f"{response_json.get('message')}")
    #             st.rerun()


    def display_field(self, label,value, icon,factsheet):
        with st.expander(label.title(), expanded=False, icon=icon):
            content = factsheet.get(value, []) if factsheet.get(value) else []
            for i, item in enumerate(content, start=1):
                st.markdown(f"**{label.title()} {i}**")
                if isinstance(item, dict):
                    for k,v in item.items():
                        if v:
                            st.markdown(f"  - **{k.replace('_',' ').title()}**: {v}")
                elif isinstance(item, list):
                    for sub_item in item:
                        st.markdown(f"  - {sub_item}")
                elif isinstance(item, str):
                    st.markdown(f"  - {item}")
                else:
                    st.markdown(f"  - {str(item)}")

    def on_project_select(self, project : dict):
        # Preserve auth credentials before clearing
        user_id = st.session_state.get('user_id')
        user_name = st.session_state.get('user_name')
        user_first_name = st.session_state.get('user_first_name')
        user_last_name = st.session_state.get('user_last_name')
        access_token = st.session_state.get('access_token')
        refresh_token = st.session_state.get('refresh_token')
        auth_initialized = st.session_state.get('_auth_initialized')
        backend_url = st.session_state.get('backend_url')

        st.session_state.clear()
        init_state()

        # Restore auth credentials
        st.session_state.user_id = user_id
        st.session_state.user_name = user_name
        st.session_state.user_first_name = user_first_name
        st.session_state.user_last_name = user_last_name
        st.session_state.access_token = access_token
        st.session_state.refresh_token = refresh_token
        st.session_state._auth_initialized = auth_initialized
        st.session_state.backend_url = backend_url

        st.session_state.project_id = project['project_id']
        logger.info(f"Selected project: {st.session_state.project_id}")

        # Load the factsheet for the selected project
        project_data =  self.backend_service.load_project(project_id=st.session_state.project_id)
        if project_data and "factsheet" in project_data and "attachments" in project_data and "emails" in project_data:
            st.session_state.factsheet = project_data.get('factsheet')
            st.session_state.attachments = project_data.get('attachments', [])
            st.session_state.emails = project_data.get('emails', [])
            logger.info(f"Loaded factsheet for project: {st.session_state.project_id}")
        else:
            st.session_state.factsheet = None
            st.session_state.attachments = []
            st.session_state.emails = []
            logger.warning(f"No Project data found for project: {st.session_state.project_id}")

        #st.rerun()

    def _delete_project(self, project_id: str):
        """Delete project from Supabase and vector store."""
        # Delete from Supabase first
        if self.backend_service.delete_project(project_id):
            # Then delete from vector store via agent API
            streaming_service = get_streaming_service(
                backend_url=st.session_state.backend_url,
                access_token=st.session_state.access_token
            )
            result = streaming_service.delete_project_vectorstore(project_id)
            
            if result.get("success"):
                logger.info(f"Successfully deleted project {project_id} from both Supabase and vector store")
            else:
                logger.warning(f"Project {project_id} deleted from Supabase but vector store cleanup failed: {result.get('error')}")
            
            # Clear session state
            if st.session_state.get('project_id') == project_id:
                st.session_state.project_id = None
                st.session_state.factsheet = None
                st.session_state.attachments = []
                st.session_state.emails = []
            
            st.toast("Project deleted")
        else:
            st.toast("Could not delete project", icon="⚠️")

    def render_projects(self, ):
        st.header("Select Project")
        projects = self.backend_service.load_projects(user_id=st.session_state.user_id)
        if projects:
            with st.expander("Projects", expanded=True):
                for project in projects:
                    is_selected = st.session_state.get('project_id') == project.get('project_id')
                    st.button(f"{project.get('title', 'No Title')}",
                            on_click=lambda p=project: self.on_project_select(p),
                            key=project.get('project_id', 'no-id'),
                            use_container_width=True,
                            type="primary" if is_selected else "secondary")
                if st.session_state.get('project_id'):
                    st.button("Delete current project", icon=":material/delete:", type="tertiary",
                              key="del_current_project",
                              on_click=lambda: self._delete_project(st.session_state.project_id))
        else:
            st.info("No projects found. Please initialize a new project.")

    def render_selected_project(self, factsheet, key_prefix: str = ""):
        st.header("Selected Project:")
        st.markdown(f"### {factsheet.get('title')}")
        
        with st.expander("Events", expanded=False, icon="🕒"):
            events = factsheet.get('events', [])
            sorted_events = sorted(events, key=lambda x: x.get('event_start_date', '') or '')
            for event in sorted_events:
                sig = event.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sig, "⚪")
                start_date = event.get('event_start_date', 'No Date')
                end_date = event.get('event_end_date', 'No Date')
                if end_date and start_date and end_date != start_date:
                    st.markdown(f"- {sig_icon} **{start_date} - {end_date}**: {event.get('description', 'No Description')}")
                elif start_date and start_date != 'No Date':
                    st.markdown(f"- {sig_icon} **{start_date}**: {event.get('description', 'No Description')}")
                else:
                    st.markdown(f"- {sig_icon} **No Date**: {event.get('description', 'No Description')}")
        
        # elements = {"parties" : "👥", "claims" : "📄", "damages" : "💰", "deadlines" : "⏰",
        # }
        # for field, icon in elements.items():
        #     self.display_field(label = field.replace("_"," ").title(), value = field, icon = icon, factsheet=factsheet)
        with st.expander("Parties", expanded=False, icon="👥"):
            parties = factsheet.get("parties", [])
            for party in parties:
                significance = party.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(significance, "⚪")
                st.markdown(f"- {sig_icon} {party.get('legal_name', 'No Legal Name')} ({party.get('role', 'No Role')})")
        
        with st.expander("Claims", expanded=False, icon="📄"):
            claims = factsheet.get("claims", [])
            for claim in claims:
                significance = claim.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(significance, "⚪")
                st.markdown(f"- {sig_icon} {claim.get('relief_sought', 'No Relief Sought')}")
        
        with st.expander("Damages", expanded=False, icon="💰"):
            damages = factsheet.get("damages", [])
            for damage in damages:
                significance = damage.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(significance, "⚪")
                st.markdown(f"- {sig_icon} {damage.get('basis', 'No Basis')} | {damage.get('amount', 'No Amount')} {damage.get('currency', '')}")
        
        with st.expander("Deadlines", expanded=False, icon="⏰"):
            deadlines = factsheet.get("deadlines", [])
            for deadline in deadlines:
                significance = deadline.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(significance, "⚪")
                date = deadline.get('deadline_date', 'No Date',)
                st.markdown(f"- {sig_icon} **{date}**: {deadline.get('description', 'No Description')}")


        with st.expander("Background", expanded=False, icon="📚"):
            st.markdown(factsheet.get("background", ""))
        
        # with st.expander("disputed & undisputed facts", expanded=False, icon="⚔️"):
        #     disputed_facts = factsheet.get('disputed_facts', [])
        #     with st.expander("Disputed Facts", expanded=False, icon="❌"):
        #         for fact in disputed_facts:
        #             st.markdown(f"- {fact}")
            
        #     with st.expander("Undisputed Facts", expanded=True, icon="✅"):
        #         for fact in factsheet.get('undisputed_facts', []):
        #             st.markdown(f"- {fact}")
            

        with st.expander("Attachments Overview", expanded=False, icon="📎"):
            sorted_attachments = sorted(
                st.session_state.get('attachments', []),
                key=lambda x: x.get('file_date', '') or '',
                reverse=True
            )
            for file in sorted_attachments:
                sig = file.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sig, "⚪")
                self.attachment_component.view_attachment(file, key=f"{key_prefix}proj_att_{file.get('file_id', '')}", sig_icon=sig_icon)

        with st.expander("Correspondence Overview", expanded=False, icon="✉️"):
            sorted_emails = sorted(
                st.session_state.get("emails", []),
                key=lambda x: x.get('date', '') or '',
                reverse=True
            )
            for file in sorted_emails:
                sig = file.get("significance", "medium")
                sig_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sig, "⚪")
                email_att = {
                    "file_id": file.get("email_id"),
                    "filename": file.get("subject", "No Subject"),
                    "file_type": "message/rfc822",
                    "body": file.get("body"),
                    "from_addr": file.get("from_addr", file.get("from", "")),
                    "to": file.get("to", []),
                    "subject": file.get("subject", ""),
                    "date": str(file.get("date", "")),
                    "reference_paths" : file.get("reference_paths", "")
                }
                self.attachment_component.view_attachment(email_att, key=f"{key_prefix}proj_email_{file.get('email_id', '')}", sig_icon=sig_icon)

    def _delete_session(self, session_id: str):
        if self.backend_service.delete_session(session_id):
            if st.session_state.get('session_id') == session_id:
                st.session_state.session_id = None
                st.session_state.messages = []
                st.session_state.session_title = None
            st.toast("Session deleted")
        else:
            st.toast("Could not delete session", icon="⚠️")

    def render_project_sessions(self):
        sessions = self.backend_service.load_project_sessions(project_id=st.session_state.project_id)
        if sessions:
            for session in sessions:
                is_selected = st.session_state.get('session_id') == session.session_id
                session_selected = st.button(
                    f"{session.title if session.title else 'No Title'}",
                    key=f"psession_{session.session_id}",
                    use_container_width=True,
                    type="primary" if is_selected else "secondary",
                )
                if session_selected:
                    history = self.backend_service.load_session_history(session.session_id)
                    st.session_state.messages = history.events
                    st.session_state.session_id = session.session_id
                    st.session_state.session_title = session.title
                    st.session_state.first_question = None
                    logger.info(f"Selected session: {st.session_state.session_id}")
                    st.rerun()
            if st.session_state.get('session_id'):
                st.button("Delete current session", icon=":material/delete:", type="tertiary",
                          key="del_current_psession",
                          on_click=lambda: self._delete_session(st.session_state.session_id))
        else:
            st.info("No sessions found for this project.")

        
    def _stream_init_progress(self, streaming_service, payload):
        """Display live streaming progress for project initialization."""
        return _render_project_stream_progress(
            stream_iter=streaming_service.init_project_stream(payload),
            initial_label="🚀 Initializing project...",
            complete_label="✅ Project initialized!",
        )

    def _stream_update_progress(self, streaming_service, payload):
        """Display live streaming progress for project update."""
        return _render_project_stream_progress(
            stream_iter=streaming_service.update_project_stream(payload),
            initial_label="🔄 Updating project...",
            complete_label="✅ Project updated!",
        )

    def render_new_project_input(self, mode : Literal["update","init"] = "init"):
        streaming_service = get_streaming_service(backend_url=st.session_state.backend_url,
                                                  access_token=st.session_state.access_token)
        user_input = st.text_area("Project details",
                                placeholder="Describe your project here...",
                                help="Provide details about your project to initialize it.",
                                height=150,
                                key = f"project_input_{st.session_state.clear_input_counter}")
        if "clear_input_counter" not in st.session_state:
            st.session_state.clear_input_counter = 0
        # Bruk CSS for å gjøre file uploader større
        st.markdown("""
            <style>
            [data-testid="stFileUploader"] {
                padding: 3rem 1rem !important;
            }
            [data-testid="stFileUploader"] section {
                min-height: 300px !important;
            }
            </style>
        """, unsafe_allow_html=True)

        query_id = str(uuid4())
        project_id = st.session_state.project_id if st.session_state.project_id else str(uuid4())

        user_files = st.file_uploader("Upload project files:",
                                    accept_multiple_files=True,
                                    type=FileExt,
                                    help="You can upload multiple files.",
                                    key = f"file_uploader_{st.session_state.clear_input_counter}")
        
        # Process uploaded files
        attachment_list = [self.attachment_component.mk_attachment_payload(f, query_id=query_id) 
                          for f in user_files] if user_files else []
        all_attachments = [att for att in attachment_list if att]
        
        # Handle duplicate filenames (with UI for user choice)
        all_attachments = self._handle_duplicate_files(all_attachments)

        payload = AskAgentRequest(
            question=user_input,
            attachments=[att.model_dump(mode = "json") for att in all_attachments],
            session_id=st.session_state.session_id,
            query_id=query_id,
            llm_model=st.session_state.llm_model,
            project_id=project_id
        )

        init_project = st.button("Initialize Project", icon="🚀") if mode == "init" else st.button("Update Project", icon="🚀")
        if init_project:
            st.session_state.project_id = project_id
            if mode == "init":
                success = self._stream_init_progress(streaming_service, payload)
                if success:
                    project_data = self.backend_service.load_project(project_id=project_id)
                    if project_data:
                        st.session_state.factsheet = project_data.get('factsheet')
                        st.session_state.attachments = project_data.get('attachments', [])
                        st.session_state.emails = project_data.get('emails', [])
                        st.session_state.update_project_view = True
                        st.session_state.clear_input_counter += 1
                        st.rerun()
                    else:
                        st.warning("Project saved but could not load data. Please refresh.")
            else:
                success = self._stream_update_progress(streaming_service, payload)
                if success:
                    project_data = self.backend_service.load_project(project_id=st.session_state.project_id)
                    if project_data:
                        st.session_state.factsheet = project_data.get('factsheet')
                        st.session_state.attachments = project_data.get('attachments', [])
                        st.session_state.emails = project_data.get('emails', [])
                        st.session_state.update_project_view = True
                        st.session_state.clear_input_counter += 1
                        st.rerun()
                    else:
                        st.warning("Project updated but could not load data. Please refresh.")

    def on_session_select(self,):
        user_id = st.session_state.get('user_id')
        user_name = st.session_state.get('user_name')
        user_first_name = st.session_state.get('user_first_name')
        user_last_name = st.session_state.get('user_last_name')
        access_token = st.session_state.get('access_token')
        refresh_token = st.session_state.get('refresh_token')
        auth_initialized = st.session_state.get('_auth_initialized')
        backend_url = st.session_state.get('backend_url')
        project_id = st.session_state.project_id

        st.session_state.clear()
        init_state()

        # Restore auth credentials
        st.session_state.user_id = user_id
        st.session_state.user_name = user_name
        st.session_state.user_first_name = user_first_name
        st.session_state.user_last_name = user_last_name
        st.session_state.access_token = access_token
        st.session_state.refresh_token = refresh_token
        st.session_state._auth_initialized = auth_initialized
        st.session_state.backend_url = backend_url
        st.session_state.project_id = project_id
        logger.info(f"Initialized new session: {st.session_state.session_id}")
        #st.rerun()

    def run_sidebar(self,):
        new_project = st.button("Initialize New Project", icon=":material/add_circle:", type="tertiary")
        if new_project:
            st.session_state.clear()
            init_state()
            st.rerun()

        st.divider()
        self.render_projects()
        st.divider()
        if st.session_state.get('project_id', None):
            project_title = st.session_state.get('factsheet', {}).get('title', '') if st.session_state.get('factsheet') else ''
            if project_title:
                st.caption(f"Aktivt prosjekt: **{project_title}**")
            with st.expander("Project Sessions", expanded=True):
                self.render_project_sessions()
                st.button("New session", icon=":material/chat:", on_click=self.on_session_select, type="tertiary")

            st.divider()
            if st.session_state.get('factsheet', None):
                with st.expander("Project info", expanded=False):
                    cols = st.columns(2)
                    update_project = cols[0].button("Update Project", icon=":material/refresh:", type="tertiary")
                    if update_project:
                        st.session_state.update_project_view = True
                    with cols[1]:
                        self.clean_element()

                    self.render_selected_project(factsheet=st.session_state.factsheet, key_prefix="sidebar_")


def get_project_component() -> ProjectComponent:
    """Cached ProjectComponent instance"""
    return ProjectComponent()


