import os
import logging
import base64
from google.cloud import firestore

from supabase import create_client, Client

from models import *
from fastapi import FastAPI,HTTPException,status,Depends
import email 
from email.message import Message 

from datetime import datetime
from pydantic import BaseModel

import uuid
from typing import Any, Literal
logger = logging.getLogger(__name__)

_TABLE_ID_FIELDS = {
    "project_parties": "party_id",
    "project_events": "event_id",
    "project_claims": "claim_id",
    "project_damages": "damage_id",
    "project_deadlines": "deadline_id",
}




class SupabaseManager:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.url, self.key)
        # Initialize Supabase client here if needed

    def load_factsheet(self, project_id: str,
                       tables: list[Literal["events", "parties", "deadlines", "damages", "claims", ]] = None
                       ) -> FactSheet:
        if tables is None:
            tables = ["events", "parties", "deadlines", "damages", "claims", ]
        
        select = ""
        for table in tables:
            select += f"project_{table}(*),\n"
        
        select_query = f"""
            *,
            {select.strip().rstrip(',\n')}
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
    
    def load_project(self, project_id: str, 
                     tables: list[Literal["attachments", "events", "parties", "deadlines", "damages", "claims", "emails"]] = None) -> ProjectData:
        if tables is None:
            tables = ["attachments", "events", "parties", "deadlines", "damages", "claims", "emails"]

        select = ""
        for table in tables:
            select += f"project_{table}(*),\n"

        select_query = f"""
                *,
                {select.rstrip(',\n')}
            """
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

    def load_attachments(self, 
                         project_id: str, 
                         tables : list[Literal["emails", "attachments"]],
                         params : dict = None,
                         ) -> dict[str, Any]:
        result = {}
        rpc_params = { "p_project_id" : project_id, **params} if params else  { "p_project_id" : project_id }
                                                
        for element in tables:
            try:
                data = self.supabase.rpc(f'get_{element}', 
                                        params = rpc_params,
                                        ).execute()
                result[element] = data.data
            except Exception as e:
                logger.exception(f"Failed loading {element} with RPC function from supabase")
                result[element] = None
        return result
        

    def load_elements(self, 
                      project_id : str,
                      tables : list[Literal["parties", "events", "claims", "damages", "deadlines"]], 
                      params : dict = None,
                      ):
        function_map = {"events": "get_events",
                "claims" : "get_claims_with_dates",
                "damages" : "get_damages_with_dates",
                "deadlines": "get_deadlines",
                }
        result = {}
        
        rpc_params = { "p_project_id" : project_id, **params} if params else  { "p_project_id" : project_id }
                                                
        for element in tables:
            try:
                data = self.supabase.rpc(function_map[element], 
                                        params = rpc_params,
                                        ).execute()
                result[element] = data.data
            except Exception as e:
                logger.exception(f"Failed loading {element} with RPC function from supabase")
                result[element] = None
        return result

    def save_project(self,
                       factsheet : FactSheet,
                       attachments  : list[Attachment],
                       user_id : str,
                       project_id : str,
                       session_id : str,
                       query_id : str = "",
                       emails : list[Email] = [],
                       llm_model: str = "",
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
        
        now = datetime.now().isoformat()
        factsheet_dict["project_id"] = project_id
        factsheet_dict["user_id"] = user_id
        factsheet_dict["updated_session_id"] = session_id
        factsheet_dict["updated_query_id"] = query_id
        factsheet_dict["updated_at"] = now
        factsheet_dict["created_by"] = llm_model
        factsheet_dict["updated_by"] = llm_model
        # ========== PROJECT FACTSHEET ==========
        if factsheet_dict:
            try:
                self.supabase.table("projects").upsert(factsheet_dict).execute()
                logger.debug(f'Project {project_id} upserted in Supabase.')
            except Exception as e:
                logger.exception(f'❌ Upsert failed for project {project_id}: {e} — stopping')
                return

        if attachment_dicts:
            try:
                # ========== PROJECT ATTACHMENTS ==========
                self.supabase.table("project_attachments").upsert(attachment_dicts).execute()
                logger.debug(f'Upserted {len(attachments)} attachments for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting attachments for project {project_id} in Supabase: {e}')
        if email_dicts:
            try:
                # ========== PROJECT EMAILS ==========
                self.supabase.table("project_emails").upsert(email_dicts).execute()
                logger.debug(f'Upserted {len(emails)} emails for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting emails for project {project_id} in Supabase: {e}')
                logger.exception(f'\n\nEmail dicts DEBUG:\n {email_dicts}\n\n')

        if parties:
            # ========== PROJECT PARTIES ==========
            try:
                parties_with_project = [
                        {**party, "project_id": project_id, "created_by": llm_model, "updated_by": llm_model, "updated_at": now}
                        for party in parties]
                self.supabase.table("project_parties").upsert(parties_with_project).execute()
                logger.debug(f'Upserted {len(parties)} parties for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting parties for project {project_id} in Supabase: {e}')

        if events:
            # ========== PROJECT EVENTS ==========
            try:
                events_with_project = [
                        {**event, "project_id": project_id, "created_by": llm_model, "updated_by": llm_model, "updated_at": now}
                        for event in events]
                self.supabase.table("project_events").upsert(events_with_project).execute()
                logger.debug(f'Upserted {len(events)} events for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting events for project {project_id} in Supabase: {e}')

        if deadlines:
            # ========== PROJECT DEADLINES ==========
            try:
                deadlines_with_project = [
                        {**deadline, "project_id": project_id, "created_by": llm_model, "updated_by": llm_model, "updated_at": now}
                        for deadline in deadlines]
                self.supabase.table("project_deadlines").upsert(deadlines_with_project).execute()
                logger.debug(f'Upserted {len(deadlines)} deadlines for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting deadlines for project {project_id} in Supabase: {e}')

        # ========== PROJECT DAMAGES ==========
        if damages:
            try:
                damages_with_project = [
                        {**damage, "project_id": project_id, "created_by": llm_model, "updated_by": llm_model, "updated_at": now}
                        for damage in damages]
                self.supabase.table("project_damages").upsert(damages_with_project).execute()
                logger.debug(f'Upserted {len(damages)} damages for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting damages for project {project_id} in Supabase: {e}')

        if claims:
            # ========== PROJECT CLAIMS ==========
            try:
                claims_with_project = [
                        {**claim, "project_id": project_id, "created_by": llm_model, "updated_by": llm_model, "updated_at": now}
                        for claim in claims]
                self.supabase.table("project_claims").upsert(claims_with_project).execute()
                logger.debug(f'Upserted {len(claims)} claims for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting claims for project {project_id} in Supabase: {e}')
        
        logger.debug(f'Completed save_project for project {project_id}. Parties: {len(parties) if parties else 0}, Events: {len(events) if events else 0}, Deadlines: {len(deadlines) if deadlines else 0}, Damages: {len(damages) if damages else 0}, Claims: {len(claims) if claims else 0}')

    def insert_project_element(self,data : list[dict],
                    project_id : str,
                    table_name: str,
                    llm_model: str = ""):
        if not data:
            logger.warning(f"No data provided to insert for project {project_id} in table {table_name}. Skipping insert.")
            return
        if not isinstance(data, list):
            raise ValueError("Data must be a list of BaseModel or dict instances.")

        now = datetime.now().isoformat()
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Each item in data must be a BaseModel or a dict.")
            item["project_id"] = project_id
            item["created_by"] = llm_model
            item["updated_by"] = llm_model
            item["updated_at"] = now
        try:
            self.supabase.table(table_name).insert(data).execute()
            logger.debug(f'Inserted {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.exception(f'Error inserting items for project {project_id} in Supabase table {table_name}')
    
    def replace_project_element(self,
                    data : list[BaseModel],
                    project_id : str,
                    table_name: str,
                    llm_model: str = ""):
        if not data:
            logger.warning(f"No data provided to replace for project {project_id} in table {table_name}. Skipping replace.")
            return

        id_field = _TABLE_ID_FIELDS.get(table_name)
        now = datetime.now().isoformat()

        existing_map = {}
        if id_field:
            existing = self.supabase.table(table_name).select(f"{id_field}, created_by, created_at").eq("project_id", project_id).execute()
            existing_map = {row[id_field]: {"created_by": row.get("created_by"), "created_at": row.get("created_at")} for row in existing.data}

        data_dicts = []
        for item in data:
            item_dict = item.model_dump(mode='json') if hasattr(item, 'model_dump') else item
            if not isinstance(item_dict, dict):
                raise ValueError("Each item in data must be a BaseModel or a dict.")
            item_id = item_dict.get(id_field) if id_field else None
            existing_entry = existing_map.get(item_id) if item_id else None
            item_dict["project_id"] = project_id
            item_dict["updated_by"] = llm_model
            item_dict["updated_at"] = now
            item_dict["created_by"] = existing_entry["created_by"] if existing_entry else llm_model
            item_dict["created_at"] = existing_entry["created_at"] if existing_entry else now
            data_dicts.append(item_dict)

        try:
            self.supabase.table(table_name).delete().eq("project_id", project_id).execute()
            self.supabase.table(table_name).insert(data_dicts).execute()
            logger.debug(f'Replaced {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.exception(f'Error replacing items for project {project_id} in Supabase table {table_name}: {e}')

    def upsert_replace_project_element(self,
                    data: list[BaseModel],
                    project_id: str,
                    table_name: str,
                    llm_model: str = ""):
        """Upsert new/updated items and delete items no longer in the list.
        Safer than replace_project_element (no delete+insert race condition)."""
        if not data:
            logger.warning(f"No data provided to upsert-replace for project {project_id} in table {table_name}. Skipping.")
            return

        id_field = _TABLE_ID_FIELDS.get(table_name)
        now = datetime.now().isoformat()

        existing_map = {}
        if id_field:
            existing = self.supabase.table(table_name).select(f"{id_field}, created_by, created_at").eq("project_id", project_id).execute()
            existing_map = {row[id_field]: {"created_by": row.get("created_by"), "created_at": row.get("created_at")} for row in existing.data}

        data_dicts = []
        for item in data:
            item_dict = item.model_dump(mode='json') if hasattr(item, 'model_dump') else item
            if not isinstance(item_dict, dict):
                raise ValueError("Each item in data must be a BaseModel or a dict.")
            item_id = item_dict.get(id_field) if id_field else None
            existing_entry = existing_map.get(item_id) if item_id else None
            item_dict["project_id"] = project_id
            item_dict["updated_by"] = llm_model
            item_dict["updated_at"] = now
            item_dict["created_by"] = existing_entry["created_by"] if existing_entry else llm_model
            item_dict["created_at"] = existing_entry["created_at"] if existing_entry else now
            data_dicts.append(item_dict)

        new_ids = [d[id_field] for d in data_dicts if id_field and d.get(id_field)]

        try:
            self.supabase.table(table_name).upsert(data_dicts).execute()
            if new_ids:
                self.supabase.table(table_name).delete().eq("project_id", project_id).not_.in_(id_field, new_ids).execute()
            else:
                self.supabase.table(table_name).delete().eq("project_id", project_id).execute()
            logger.debug(f'Upsert-replaced {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.exception(f'Error upsert-replacing items for project {project_id} in Supabase table {table_name}: {e}')

    def upsert_project_custom(self,
                    data : dict | str,
                    element_type : str,
                    project_id : str,
                    table_name = "project_legal",
                    llm_model: str = ""):
        if not data:
            logger.warning(f"No custom field data provided to replace for project {project_id}. Skipping replace.")
            return
        if not isinstance(data, dict):
            data = {element_type: data}

        existing = self.supabase.table(table_name).select("created_by").eq("project_id", project_id).execute()
        data["project_id"] = project_id
        data["created_by"] = existing.data[0].get("created_by") if existing.data else llm_model
        data["updated_by"] = llm_model
        data["updated_at"] = datetime.now().isoformat()

        try:
            self.supabase.table(table_name).upsert(data).execute()
            logger.debug(f'Replaced custom fields for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.exception(f'Error replacing custom fields for project {project_id} in Supabase: {e}')

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

        existing = self.supabase.table("projects").select("created_by").eq("project_id", project_id).execute()
        data["project_id"] = project_id
        data["created_by"] = existing.data[0].get("created_by") if existing.data else llm_model
        data["updated_by"] = llm_model
        data["updated_at"] = datetime.now().isoformat()
        try:
            self.supabase.table("projects").upsert(data).execute()
            logger.debug(f'Project {project_id} upserted in Supabase.')
        except Exception as e:
            logger.exception(f'Error upserting project {project_id} in Supabase: {e}')

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
                from agent.agent_modules import Summarizer
                summarizer = Summarizer()
                title = summarizer.mk_title(title_msg)
            except Exception as e:
                logger.exception(f"Error creating title")
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
            logger.exception(f'❌ Upsert failed for session {session_id}: {e} — stopping')
            return 

        try:
            self.supabase.table("session_events").insert(new_events).execute() if new_events else None
            logger.debug(f'Inserted {len(new_events)} events for session {session_id} in Supabase.')
        except Exception as e:
            logger.exception(f'Error inserting events for session {session_id} in Supabase: {e}')
        try:
            self.supabase.table("session_attachments").insert(new_attachments).execute() if new_attachments else None
            logger.debug(f'Inserted {len(new_attachments)} attachments for session {session_id} in Supabase.')
        except Exception as e:
            logger.exception(f'Error inserting attachments for session {session_id} in Supabase: {e}')

    def delete_project(self, project_id: str):
        """Delete project from Supabase (vector store cleanup handled separately by FE calling agent API)"""
        try:
            self.supabase.table("projects").delete().eq("project_id", project_id).execute()
            logger.debug(f'Project {project_id} deleted from Supabase.')
        except Exception as e:
            logger.exception(f'Error deleting project {project_id} from Supabase: {e}')

    def get_paths(self, file_ids: list[str]) -> list[str]:
        """Get storage paths for given file IDs from Supabase"""
        response_att = self.supabase.table("project_attachments").select("path").in_("file_id", file_ids).execute()
        response_emails = self.supabase.table("project_emails").select("path").in_("email_id", file_ids).execute()
        paths = [item["path"] for item in response_att.data]
        emails = [item["path"] for item in response_emails.data]
        return emails + paths