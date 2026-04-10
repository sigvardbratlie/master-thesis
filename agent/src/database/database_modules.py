import os
import json
import logging
import base64
from google.cloud import firestore

import httpx
import functools
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

def _strip_null_bytes(obj: Any) -> Any:
    """Recursively strip null bytes from strings in dicts/lists (PostgreSQL rejects \\u0000)."""
    if isinstance(obj, str):
        return obj.replace('\x00', '')
    if isinstance(obj, dict):
        return {k: _strip_null_bytes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_strip_null_bytes(item) for item in obj]
    return obj


_TABLE_ID_FIELDS = {
    "project_parties": "party_id",
    "project_events": "event_id",
    "project_claims": "claim_id",
    "project_damages": "damage_id",
    "project_deadlines": "deadline_id",
    "project_attachments": "file_id",
    "project_emails": "email_id",
}

_STALE_CONNECTION_ERRORS = (httpx.ReadError, httpx.RemoteProtocolError, httpx.WriteError)


def _with_reconnect(method):
    """Decorator that retries once after recreating the Supabase client on stale HTTP/2 connection errors."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except _STALE_CONNECTION_ERRORS:
            logger.warning(f"Stale Supabase connection in {method.__name__}, reconnecting and retrying.")
            self.supabase = create_client(self.url, self.key)
            return method(self, *args, **kwargs)
    return wrapper


class SupabaseManager:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(self.url, self.key)

    def _execute(self, fn):
        """Execute fn(), reconnecting once on stale HTTP/2 connection errors."""
        try:
            return fn()
        except _STALE_CONNECTION_ERRORS:
            logger.warning("Stale Supabase connection, reconnecting and retrying.")
            self.supabase = create_client(self.url, self.key)
            return fn()

    def match_party_reps(self, project_party_reps, project_parties) -> None:
        party_ids = set(party["party_id"] for party in project_parties)
        party_ids_from_reps = set(rep["party_id"] for rep in project_party_reps)
        if not party_ids_from_reps.issubset(party_ids):
            missing_parties = party_ids_from_reps - party_ids
            raise ValueError(f"Fant reps for ukjente parter: {missing_parties}")
        reps = {}
        for rep in project_party_reps:
            if rep["party_id"] not in reps:
                reps[rep["party_id"]] = [rep]
            else:
                reps[rep["party_id"]].append(rep)

        for party in project_parties:
            if party["party_id"] not in reps:
                party["party_reps"] = []
            else:
                party["party_reps"] = reps[party["party_id"]]

    def load_factsheet(self, project_id: str,
                       tables: list[Literal["events", "parties", "party_reps", "deadlines", "damages", "claims", ]] = None
                       ) -> FactSheet:
        if tables is None:
            tables = ["events", "parties", "party_reps", "deadlines", "damages", "claims", ]
        
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
        project_party_reps = data.pop("project_party_reps", [])
        project_deadlines = data.pop("project_deadlines", [])
        project_damages   = data.pop("project_damages",   [])
        project_claims    = data.pop("project_claims",    [])

        self.match_party_reps(project_party_reps, project_parties)

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
                     tables: list[Literal["attachments", "events", "parties", "party_reps", "deadlines", "damages", "claims", "emails"]] = None) -> ProjectData:
        if tables is None:
            tables = ["events", "parties", "party_reps", "deadlines", "damages", "claims", ]
            attach_email_tables = ["attachments", "emails"]
        else:
            attach_email_tables = [table for table in tables if table in ["attachments", "emails"]]
            tables = [table for table in tables if table not in ["attachments", "emails"]]

        attach_emails = self.load_attachments(project_id, attach_email_tables,)
        attachments = attach_emails.get("attachments", [])
        project_emails = attach_emails.get("emails", [])
        factsheet = self.load_factsheet(project_id, tables)
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
                "parties" : "get_parties_with_reps", 
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

    @_with_reconnect
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
        exclude_fields = {"events","claims","damages","deadlines","parties"}
        attachment_dicts = []
        email_dicts = []
        if attachments:
            for attachment in attachments:
                attachment_dict = attachment.model_dump(mode='json', exclude=exclude_fields)
                attachment_dict["project_id"] = project_id
                attachment_dict["created_by"] = llm_model
                attachment_dicts.append(attachment_dict)
            #logger.debug(f' ========= ATTACHEMNT CONTENTS TO SAVE ======== \n {attachment_dicts} \n')
        
        if emails:
            seen_email_ids = set()
            for email in emails:
                email_dict = email.model_dump(mode='json', exclude=exclude_fields)
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
        party_reps = []

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
                attachment_dicts = [_strip_null_bytes(d) for d in attachment_dicts]
                payload_size = len(json.dumps(attachment_dicts, default=str).encode())
                if payload_size > 1 * 1024 * 1024:
                    logger.warning(f"⚠️ Large attachment payload: {payload_size / 1024 / 1024:.1f}MB ({len(attachment_dicts)} rows) for project {project_id}")
                self.supabase.table("project_attachments").upsert(attachment_dicts).execute()
                logger.debug(f'Upserted {len(attachments)} attachments for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting attachments for project {project_id} in Supabase: {e}')
        if email_dicts:
            try:
                # ========== PROJECT EMAILS ==========
                payload_size = len(json.dumps(email_dicts, default=str).encode())
                if payload_size > 1 * 1024 * 1024:
                    logger.warning(f"⚠️ Large email payload: {payload_size / 1024 / 1024:.1f}MB ({len(email_dicts)} rows) for project {project_id}")
                self.supabase.table("project_emails").upsert(email_dicts).execute()
                logger.debug(f'Upserted {len(emails)} emails for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting emails for project {project_id} in Supabase: {e}')
                logger.exception(f'\n\nEmail dicts DEBUG:\n {email_dicts}\n\n')

        if parties:
            # ========== PROJECT PARTIES ==========
            for party in parties:
                party["project_id"] = project_id
                party["created_by"] = llm_model
                party["updated_by"] = llm_model
                party["updated_at"] = now
                reps = party.pop("party_reps", None)
                for rep in (reps or []):
                    rep_dict = rep.model_dump(mode='json') if hasattr(rep, 'model_dump') else rep
                    if not rep_dict.get("party_rep_id"):
                        rep_dict["party_rep_id"] = str(uuid.uuid4())
                    rep_dict["project_id"] = project_id
                    rep_dict["created_by"] = llm_model
                    rep_dict["updated_by"] = llm_model
                    rep_dict["updated_at"] = now
                    party_reps.append(rep_dict)
            
            try: 
                self.supabase.table("project_parties").upsert(parties).execute()
                logger.debug(f'Upserted {len(parties)} parties for project {project_id} in Supabase.')
            except Exception as e:
                logger.exception(f'Error upserting parties for project {project_id} in Supabase: {e}')

            if party_reps:
                try:
                    self.supabase.table("project_party_reps").upsert(party_reps).execute()
                    logger.debug(f'Upserted {len(party_reps)} party representatives for project {project_id} in Supabase.')
                except Exception as e:
                    logger.exception(f'Error upserting party representatives for project {project_id} in Supabase: {e}')

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

    @_with_reconnect
    def insert_project_element(self,data : list[BaseModel],
                    project_id : str,
                    table_name: Literal[*_TABLE_ID_FIELDS],
                    llm_model: str = ""):
        if not data:
            logger.warning(f"No data provided to insert for project {project_id} in table {table_name}. Skipping insert.")
            return
        if not isinstance(data, list):
            raise ValueError("Data must be a list of BaseModel or dict instances.")
        data = [d.model_dump(mode= "json", exclude={"events","claims","damages","deadlines","parties"}) if hasattr(d, 'model_dump') else d for d in data]

        now = datetime.now().isoformat()
        for item in data:
            if not isinstance(item, dict):
                raise ValueError("Each item in data must be a BaseModel or a dict.")
            item["project_id"] = project_id
            item["created_by"] = llm_model
            item["updated_by"] = llm_model
            item["updated_at"] = now
        try:
            self._execute(lambda: self.supabase.table(table_name).upsert([_strip_null_bytes(d) for d in data], ignore_duplicates=True).execute())
            logger.debug(f'Inserted {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.exception(f'Error inserting items for project {project_id} in Supabase table {table_name}')
            raise
    
    @_with_reconnect
    def replace_project_element(self,
                    data : list[BaseModel],
                    project_id : str,
                    table_name: Literal["project_parties", "project_events", "project_claims", "project_damages", "project_deadlines"],
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
            self._execute(lambda: self.supabase.table(table_name).delete().eq("project_id", project_id).execute())
            self._execute(lambda: self.supabase.table(table_name).insert([_strip_null_bytes(d) for d in data_dicts]).execute())
            logger.debug(f'Replaced {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.exception(f'Error replacing items for project {project_id} in Supabase table {table_name}: {e}')

    @_with_reconnect
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
            if id_field and not item_id:
                item_id = str(uuid.uuid4())
                item_dict[id_field] = item_id
            existing_entry = existing_map.get(item_id) if item_id else None
            item_dict["project_id"] = project_id
            item_dict["updated_by"] = llm_model
            item_dict["updated_at"] = now
            item_dict["created_by"] = existing_entry["created_by"] if existing_entry else llm_model
            item_dict["created_at"] = existing_entry["created_at"] if existing_entry else now
            data_dicts.append(item_dict)

        new_ids = [d[id_field] for d in data_dicts if id_field and d.get(id_field)]

        try:
            self._execute(lambda: self.supabase.table(table_name).upsert([_strip_null_bytes(d) for d in data_dicts]).execute())
            if new_ids:
                self._execute(lambda: self.supabase.table(table_name).delete().eq("project_id", project_id).not_.in_(id_field, new_ids).execute())
            else:
                self._execute(lambda: self.supabase.table(table_name).delete().eq("project_id", project_id).execute())
            logger.debug(f'Upsert-replaced {len(data)} items for project {project_id} in Supabase table {table_name}.')
        except Exception as e:
            logger.exception(f'Error upsert-replacing items for project {project_id} in Supabase table {table_name}: {e}')

    @_with_reconnect
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
            self._execute(lambda: self.supabase.table("projects").upsert(data).execute())
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

    @_with_reconnect
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
    
    def get_body_by_id(self, ids: list[str]) -> list[dict]:
        """Get email bodies for given email IDs from Supabase"""
        try:
            response = self.supabase.rpc("get_body_by_id", {"file_ids" : ids}).execute()
            return response.data if response.data else []
        except Exception:
            logger.exception(f"Error reading bodies for ids {ids} from Supabase")
            return []
        
    def get_project_base(self, project_id: str) -> dict:
        """Get base project info (without nested tables) for given project ID from Supabase"""
        try:
            response = self.supabase.table("projects").select("title, background").eq("project_id", project_id).single().execute()
            return response.data if response.data else {}
        except Exception:
            logger.exception(f"Error reading base project info for project_id {project_id} from Supabase")
            return {}
        
    def get_party_context(self, project_id : str) -> list[dict]:
        """Get email context (sender, recipient, subject) for all emails in a project from Supabase"""
        context = ""
        email_cols = ["party_roles", "from_addr", "from_name", "to", "to_names", "cc", "cc_names", "title", "description"]
        docs_cols = ["party_roles", "title", "description"]
        
        try:
            response_email = self.supabase.table("project_emails").select(", ".join(email_cols)).eq("project_id", project_id).execute()
        except Exception:
            logger.exception(f"Error reading email party context for project_id {project_id} from Supabase")
        
        try:
            response_docs = self.supabase.table("project_attachments").select(", ".join(docs_cols)).eq("project_id", project_id).execute()
        except Exception:
            logger.exception(f"Error reading document party context for project_id {project_id} from Supabase")

        if response_email.data:
            context = "**Party info from Emails** : " + "\n" #+  " | ".join(email_cols) + "\n"
            for row in response_email.data:
                if row.get("party_roles"):
                    context += " | ".join([str(row[col]) for col in email_cols]) + "\n"
        if response_docs.data:
            context += "\n**Party info from Documents** : " + "\n"  #+ " | ".join(docs_cols) + "\n"
            for row in response_docs.data:
                if row.get("party_roles"):
                    context += " | ".join([str(row[col]) for col in docs_cols]) + "\n"
        if not context:
            context = "No email or document context available."
        return context