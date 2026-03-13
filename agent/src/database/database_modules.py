import os
import logging
import base64
from google.cloud import firestore

from supabase import create_client, Client

from models import *
from fastapi import FastAPI,HTTPException,status,Depends
from agent.agent_modules import Summarizer
import email 
from email.message import Message 

from datetime import datetime
from pydantic import BaseModel

import uuid

logger = logging.getLogger(__name__)




class SupabaseManager:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.url, self.key)
        # Initialize Supabase client here if needed

    def load_factsheet(self, project_id: str,) -> FactSheet:
        select_query = """
            *,
            project_events(*),
            project_parties(*),
            project_damages(*),
            project_claims(*),
            project_deadlines(*)
        """

        # Utfør spørringen — ved limited: filtrer ut low-significance events og parties
        try:
            query = (
                self.supabase.table("projects")
                .select(select_query)
                .eq("project_id", project_id)
            )
            response = query.single().execute()
        except Exception as e:
            raise ValueError(f"Feil ved lasting av factsheet: {e}")

        data = response.data

        # Pop ut nested arrays (Supabase returnerer dem som lister)
        project_events    = data.pop("project_events",    [])
        project_parties   = data.pop("project_parties",   [])
        project_deadlines = data.pop("project_deadlines", [])
        project_damages   = data.pop("project_damages",   [])
        project_claims    = data.pop("project_claims",    [])

        # Bygg FactSheet-objektet
        factsheet = FactSheet(
            **data,                     # resten av prosjekt-feltene
            parties=project_parties,
            events=project_events,
            deadlines=project_deadlines,
            damages=project_damages,
            claims=project_claims,
        )
        return factsheet
    
    def load_project(self, project_id: str) -> ProjectData:
        select_query = """
                *,
                project_attachments(*),
                project_events(*),
                project_parties(*),
                project_deadlines(*),
                project_damages(*),
                project_claims(*),
                project_emails(*)"""

        project = self.supabase.table("projects").select(select_query).eq("project_id", project_id).single().execute()

        # Extract nested data from single query
        data = project.data
        attachments = data.pop("project_attachments", [])
        project_events = data.pop("project_events", [])
        project_parties = data.pop("project_parties", [])
        project_deadlines = data.pop("project_deadlines", [])
        project_damages = data.pop("project_damages", [])
        project_claims = data.pop("project_claims", [])
        project_emails = data.pop("project_emails", [])

        factsheet = FactSheet(**data,
                              parties=project_parties,
                              events=project_events,
                              deadlines=project_deadlines,
                              damages=project_damages,
                              claims=project_claims)
        attachments_models = [Attachment(**attachment) for attachment in attachments]
        emails_models = [Email(**email) for email in project_emails]
        return ProjectData(
            factsheet=factsheet,
            attachments=attachments_models,
            emails=emails_models,
        )

    def save_project(self,
                       factsheet : FactSheet,
                       attachments  : list[Attachment],
                       user_id : str,
                       project_id : str,
                       session_id : str,
                       query_id : str = "",
                       llm_model : str = "",
                       emails : list[Email] = [],
                       ):
                
        attachment_dicts = []
        email_dicts = []
        if attachments:
            for attachment in attachments:
                attachment_dict = attachment.model_dump(mode='json', exclude={"events","claims","damages","deadlines"})
                attachment_dict["project_id"] = project_id
                attachment_dict["created_by"] = llm_model
                attachment_dicts.append(attachment_dict)
            #logger.debug(f' ========= ATTACHEMNT CONTENTS TO SAVE ======== \n {attachment_dicts} \n')
        
        if emails:
            seen_email_ids = set()
            for email in emails:
                email_dict = email.model_dump(mode='json', exclude={"events","claims","damages","deadlines"})
                email_dict["project_id"] = project_id
                email_dict["created_by"] = llm_model
                if email_dict["email_id"] not in seen_email_ids:
                    seen_email_ids.add(email_dict["email_id"])
                    email_dicts.append(email_dict)
        
        factsheet_dict = factsheet.model_dump(mode='json')
        claims = factsheet_dict.pop("claims", [])
        damages = factsheet_dict.pop("damages", [])
        deadlines = factsheet_dict.pop("deadlines", [])
        events = factsheet_dict.pop("events", [])
        parties = factsheet_dict.pop("parties", [])
        
        factsheet_dict["project_id"] = project_id
        factsheet_dict["user_id"] = user_id
        factsheet_dict["updated_session_id"] = session_id
        factsheet_dict["updated_query_id"] = query_id
        factsheet_dict["updated_at"] = datetime.now().isoformat()
        factsheet_dict["created_by"] = llm_model
        # ========== PROJECT FACTSHEET ==========
        if factsheet_dict:
            try:
                self.supabase.table("projects").upsert(factsheet_dict).execute()
                logger.debug(f'Project {project_id} upserted in Supabase.')
            except Exception as e:
                logger.error(f'❌ Upsert failed for project {project_id}: {e} — stopping', exc_info=True)
                return

        if attachment_dicts:
            try:
                # ========== PROJECT ATTACHMENTS ==========
                self.supabase.table("project_attachments").upsert(attachment_dicts).execute()
                logger.debug(f'Upserted {len(attachments)} attachments for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting attachments for project {project_id} in Supabase: {e}', exc_info=True)
        if email_dicts:
            try:
                # ========== PROJECT EMAILS ==========
                self.supabase.table("project_emails").upsert(email_dicts).execute()
                logger.debug(f'Upserted {len(emails)} emails for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting emails for project {project_id} in Supabase: {e}', exc_info=True)
                logger.error(f'\n\nEmail dicts DEBUG:\n {email_dicts}\n\n')

        if parties:
            # ========== PROJECT PARTIES ==========
            try:
                parties_with_project = [
                        {**party, "project_id": project_id, "created_by": llm_model}
                        for party in parties]
                self.supabase.table("project_parties").upsert(parties_with_project).execute()
                logger.debug(f'Upserted {len(parties)} parties for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting parties for project {project_id} in Supabase: {e}', exc_info=True)

        if events:
            # ========== PROJECT EVENTS ==========
            try:
                events_with_project = [
                        {**event, "project_id": project_id, "created_by": llm_model}
                        for event in events]
                self.supabase.table("project_events").upsert(events_with_project).execute()
                logger.debug(f'Upserted {len(events)} events for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting events for project {project_id} in Supabase: {e}', exc_info=True)

        if deadlines:
            # ========== PROJECT DEADLINES ==========
            try:
                deadlines_with_project = [
                        {**deadline, "project_id": project_id, "created_by": llm_model}
                        for deadline in deadlines]
                self.supabase.table("project_deadlines").upsert(deadlines_with_project).execute()
                logger.debug(f'Upserted {len(deadlines)} deadlines for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting deadlines for project {project_id} in Supabase: {e}', exc_info=True)

        # ========== PROJECT DAMAGES ==========
        if damages:
            try:
                damages_with_project = [
                        {**damage, "project_id": project_id, "created_by": llm_model}
                        for damage in damages]
                self.supabase.table("project_damages").upsert(damages_with_project).execute()
                logger.debug(f'Upserted {len(damages)} damages for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting damages for project {project_id} in Supabase: {e}', exc_info=True)

        if claims:
            # ========== PROJECT CLAIMS ==========
            try:
                claims_with_project = [
                        {**claim, "project_id": project_id, "created_by": llm_model}
                        for claim in claims]
                self.supabase.table("project_claims").upsert(claims_with_project).execute()
                logger.debug(f'Upserted {len(claims)} claims for project {project_id} in Supabase.')
            except Exception as e:
                logger.error(f'Error upserting claims for project {project_id} in Supabase: {e}', exc_info=True)
        
        logger.debug(f'Completed save_project for project {project_id}. Parties: {len(parties) if parties else 0}, Events: {len(events) if events else 0}, Deadlines: {len(deadlines) if deadlines else 0}, Damages: {len(damages) if damages else 0}, Claims: {len(claims) if claims else 0}')

    def insert_project_element(self,data : list[dict],
                    project_id : str,
                    table_name: str,
                    llm_model : str = ""):
        if not data:
            logger.warning(f"No data provided to insert for project {project_id} in table {table_name}. Skipping insert.")
            return
        if not isinstance(data, list):
            raise ValueError("Data must be a list of BaseModel or dict instances.")
        
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Each item in data must be a BaseModel or a dict.")
            item["project_id"] = project_id
            item["created_by"] = llm_model
        try:
            self.supabase.table(table_name).insert(data).execute()
            logger.debug(f'Inserted {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.error(f'Error inserting items for project {project_id} in Supabase table {table_name}: {e}',exc_info=True)
    
    def replace_project_element(self,
                    data : list[BaseModel],
                    project_id : str,
                    table_name: str,
                    llm_model : str = ""
                    ):
        if not data:
            logger.warning(f"No data provided to replace for project {project_id} in table {table_name}. Skipping replace.")
            return

        data_dicts = []
        for item in data:
            item_dict = item.model_dump(mode='json') if hasattr(item, 'model_dump') else item
            if not isinstance(item_dict, dict):
                raise ValueError("Each item in data must be a BaseModel or a dict.")
            item_dict["project_id"] = project_id
            item_dict["created_by"] = llm_model
            data_dicts.append(item_dict)

        try:
            self.supabase.table(table_name).delete().eq("project_id", project_id).execute()
            
            if data_dicts:  
                self.supabase.table(table_name).insert(data_dicts).execute()
            else:
                logger.warning(f"No data provided to replace for project {project_id} in table {table_name}. Skipping insert after delete.")
            
            logger.debug(f'Replaced {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.error(f'Error replacing items for project {project_id} in Supabase table {table_name}: {e}')

    def upsert_project(self, 
                       data: dict | str, 
                       element_type: str,
                       project_id: str,
                       llm_model: str = ""):
        if not data:
            logger.warning(f"No data provided to upsert for project {project_id}. Skipping upsert.")
            return
        if not isinstance(data, dict):
            data = {element_type: data}
        data["project_id"] = project_id
        data["created_by"] = llm_model
        try:
            self.supabase.table("projects").upsert(data).execute()
            logger.debug(f'Project {project_id} upserted in Supabase.')
        except Exception as e:
            logger.error(f'Error upserting project {project_id} in Supabase: {e}')

    def load_projects(self, user_id: str) -> list[ProjectSummary]:
        projects = self.supabase.table("projects").select("project_id, title, created_at").eq("user_id", user_id).execute()
        if projects.data:
            sorted_projects = sorted(
                projects.data,
                key=lambda x: x.get("created_at") or "",
                reverse=True
            )
            return [ProjectSummary(**p) for p in sorted_projects]
        return []

    def load_project_sessions(self, project_id: str) -> list[SessionSummary]:
        project_sessions = self.supabase.table("sessions").select("session_id, title, updated_at, llm_model").eq("project_id", project_id).execute()
        if project_sessions.data:
            sorted_sessions = sorted(
                project_sessions.data,
                key=lambda x: x.get("updated_at") or "",
                reverse=True
            )
            return [SessionSummary(**s) for s in sorted_sessions]
        return []

    def load_user_sessions(self, user_id: str) -> list[SessionSummary]:
        '''Load all sessions for a user from Supabase'''
        try:
            sessions = self.supabase.table("sessions").select("title, session_id, updated_at").eq("user_id", user_id).order("updated_at", desc=True).execute()
            if sessions.data:
                sorted_sessions = sorted(
                    sessions.data,
                    key=lambda x: x.get("updated_at") or "",
                    reverse=True
                )
                logger.debug(f'Loaded {len(sessions.data)} sessions for user {user_id} from Supabase.')
                return [SessionSummary(**s) for s in sorted_sessions]
            return []
        except Exception as e:
            logger.error(f'❌ Could not load sessions for user {user_id}: {e}', exc_info=True)
            return []

    def load_session_history(self, session_id: str) -> SessionHistory:
        '''Load session history for a given session from Supabase'''
        query = """ *,
                    session_events(*),
                    session_attachments(*)
                    """
        response = self.supabase.table("sessions").select(query).eq("session_id", session_id).single().execute()
        if response.data:
            session_data = response.data
            session_events = session_data.pop("session_events", [])
            session_attachments = session_data.pop("session_attachments", [])
            attachments = [AttachmentModel.model_validate(att) for att in session_attachments]
            logger.debug(f'Loaded session history for session {session_id} from Supabase.')
            return SessionHistory(
                events=session_events,
                attachments=attachments,
                project_id=session_data.get("project_id") or "",
                title=session_data.get("title", ""),
                llm_model=session_data.get("llm_model"),
                updated_at=session_data.get("updated_at"),
            )
        else:
            logger.warning(f"No session found for session_id: {session_id} in Supabase.")
            return SessionHistory(events=[], attachments=[], project_id="", title="Ny samtale")

    def load_session_attachments(self, session_id: str) -> list[AttachmentModel]:
        '''Load attachments for a given session from Supabase'''
        response = self.supabase.table("session_attachments").select("*").eq("session_id", session_id).execute()
        if response.data:
            logger.debug(f'Loaded {len(response.data)} attachments for session {session_id} from Supabase.')
            return [AttachmentModel.model_validate(att) for att in response.data]
        else:
            logger.warning(f"No attachments found for session_id: {session_id} in Supabase.")
            return []

    def save_stream(self, 
                    data : StreamData,
                    user_id : str,
                    session_id : str): 
        # Implement saving stream to Supabase
        new_events = [] 
        new_attachments = [] 
        for event in data.events:
            event_dict = event.model_dump(mode = "json")
            event_dict["session_id"] = session_id
            new_events.append(event_dict)
        for attachment in data.attachments:
            attachment_dict = attachment.model_dump(mode = "json")
            attachment_dict["session_id"] = session_id
            attachment_dict.pop("content", None)  # Remove content if present before saving
            new_attachments.append(attachment_dict)

        result = (
            self.supabase
            .table("sessions")
            .select("title")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )

        title = result.data[0]["title"] if result.data else None

        if not title or title == "Ny samtale":
            try:
                title_msg = [msg.get("content") for msg in new_events if msg.get("type") == "human" or msg.get("type") == "ai"]
                #title = await self.mk_title(title_msg)
                summarizer = Summarizer()
                title = summarizer.mk_title(title_msg)
            except Exception as e:
                logger.error(f"Error creating title: {e}", exc_info=True)
                title = "Ny samtale"

        try:
            self.supabase.table("sessions").upsert({
                "session_id": session_id,
                "user_id": user_id,
                "title" : title,
                "project_id": data.project_id,
                "llm_model" : data.llm_model,}).execute()
            logger.debug(f'Session {session_id} upserted in Supabase.')
        except Exception as e:
            logger.error(f'❌ Upsert failed for session {session_id}: {e} — stopping', exc_info=True)
            return 

        try:
            self.supabase.table("session_events").insert(new_events).execute() if new_events else None
            logger.debug(f'Inserted {len(new_events)} events for session {session_id} in Supabase.')
        except Exception as e:
            logger.error(f'Error inserting events for session {session_id} in Supabase: {e}', exc_info=True)
        try:
            self.supabase.table("session_attachments").insert(new_attachments).execute() if new_attachments else None
            logger.debug(f'Inserted {len(new_attachments)} attachments for session {session_id} in Supabase.')
        except Exception as e:
            logger.error(f'Error inserting attachments for session {session_id} in Supabase: {e}', exc_info=True)

    def delete_project(self, project_id: str):
        """Delete project from Supabase (vector store cleanup handled separately by FE calling agent API)"""
        try:
            self.supabase.table("projects").delete().eq("project_id", project_id).execute()
            logger.debug(f'Project {project_id} deleted from Supabase.')
        except Exception as e:
            logger.error(f'Error deleting project {project_id} from Supabase: {e}', exc_info=True)

