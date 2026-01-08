from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Tuple, AsyncIterator
import asyncio

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    PendingWrite,
    get_checkpoint_id,
    ChannelVersions
)
from google.cloud import firestore
# Sørg for at du har en FirestoreSerializer-implementasjon
# For dette eksempelet antar vi at den ligner på den originale.
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


# Enkel Serializer for demonstrasjon, erstatt med din egen om nødvendig.
class FirestoreSerializer:
    def __init__(self, inner_serde):
        self._inner_serde = inner_serde

    def dumps(self, obj: Any) -> str:
        return self._inner_serde.dumps(obj).decode('utf-8')

    def loads(self, s: str) -> Any:
        return self._inner_serde.loads(s.encode('utf-8'))

    def dumps_typed(self, obj: Any) -> Tuple[str, str]:
        if isinstance(obj, dict) and "v" in obj and "id" in obj:
            return "checkpoint", self.dumps(obj)
        return type(obj).__name__, self.dumps(obj)

    def loads_typed(self, typed_obj: Tuple[str, str]) -> Any:
        # Denne funksjonen må kanskje justeres basert på din faktiske logikk
        return self.loads(typed_obj[1])


class FirestoreSaver(BaseCheckpointSaver):
    """
    En LangGraph Checkpoint Saver som bruker Google Cloud Firestore som backend.
    """

    def __init__(
            self,
            project_id: str,
            database_id: str = "(default)",
            checkpoints_collection: str = "checkpoints",
            writes_collection: str = "writes",
    ):
        """
        Initialiserer FirestoreSaver.

        Args:
            project_id (str): Din Google Cloud prosjekt-ID.
            database_id (str): ID-en til Firestore-databasen. Standard er "(default)".
            checkpoints_collection (str): Navnet på rot-collection for sjekkpunkter.
            writes_collection (str): Navnet på rot-collection for 'pending writes'.
        """
        super().__init__(serde=JsonPlusSerializer())
        self.client = firestore.Client(project=project_id, database=database_id)
        self.firestore_serde = FirestoreSerializer(self.serde)
        self.checkpoints_collection_ref = self.client.collection(checkpoints_collection)
        self.writes_collection_ref = self.client.collection(writes_collection)
        print(f"FirestoreSaver initialisert for prosjekt '{project_id}' og database '{database_id}'")

    @classmethod
    @contextmanager
    def from_conn_info(
            cls,
            project_id: str,
            database_id: str = "(default)",
            checkpoints_collection: str = "checkpoints",
            writes_collection: str = "writes",
    ) -> Iterator["FirestoreSaver"]:
        saver = None
        try:
            saver = cls(
                project_id, database_id, checkpoints_collection, writes_collection
            )
            yield saver
        finally:
            # Firestore-klienten håndterer sin egen tilkoblingspooling, så ingen 'close' er nødvendig.
            pass

    def put(
            self,
            config: RunnableConfig,
            checkpoint: Checkpoint,
            metadata: CheckpointMetadata,
            new_versions: ChannelVersions
    ) -> RunnableConfig:

        thread_id = config["configurable"].get("thread_id")
        user_id = config["configurable"].get("user_id")
        domain = config["configurable"].get("domain")
        if not user_id:
            raise ValueError(f'UserId must be present')
        if not thread_id:
            raise ValueError(f'ThreadId must be present')
        checkpoint_id = checkpoint["id"]
        parent_checkpoint_id = config["configurable"].get("checkpoint_id")

        #print(f"--- KJØRER ALLER SISTE VERSJON AV FirestoreSaver.put ---\nTHREAD ID : {thread_id} | CHECKPOINT ID {checkpoint_id}")
        #print(f'Instance of thread ID : {type(thread_id)}')
        # new_thread=  dict(thread_id)
        # print(f'Try this : {new_thread.get("configurable").get("thread_id")}')

        # Bygg dokumentreferansen
        doc_ref = (
            self.checkpoints_collection_ref.document(user_id)
            .collection("checkpoints")
            .document(thread_id)
            .collection(checkpoint_id)
            .document("data")
        )

        # Serialiser data
        type_, serialized_checkpoint = self.firestore_serde.dumps_typed(checkpoint)
        serialized_metadata = self.firestore_serde.dumps(metadata)

        data_to_save = {
            "checkpoint": serialized_checkpoint,
            "type": type_,
            "metadata": serialized_metadata,
            "parent_checkpoint_id": parent_checkpoint_id or "",
            "ts": firestore.SERVER_TIMESTAMP,
            "domain" : domain
        }

        # Skriv til Firestore
        doc_ref.set(data_to_save)

        return {
            "configurable": {
                "user_id" : user_id,
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
            self, config: RunnableConfig, writes: List[Tuple[str, Any]], task_id: str
    ) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_id = config["configurable"]["checkpoint_id"]
        user_id = config["configurable"].get("user_id")  # Hent user_id

        if not user_id:
            raise ValueError("user_id must be present in config to put writes")

        batch = self.client.batch()
        for idx, (channel, value) in enumerate(writes):
            type_, serialized_value = self.firestore_serde.dumps_typed(value)

            doc_id = f"{task_id}_{idx}"
            # Oppdater doc_ref til å inkludere user_id
            doc_ref = (
                self.writes_collection_ref.document(user_id)
                .collection("writes")  # Legg til et ekstra nivå for konsistens
                .document(thread_id)
                .collection(checkpoint_id)
                .document(doc_id)
            )

            data = {
                "channel": channel,
                "type": type_,
                "value": serialized_value,
                "task_id": task_id,
                "idx": idx
            }
            batch.set(doc_ref, data)
        batch.commit()

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        user_id = config["configurable"]["user_id"]
        #domain = config["configurable"]["domain"]
        checkpoint_id = get_checkpoint_id(config)

        # Hvis ingen checkpoint_id er spesifisert, finn den siste.
        if not checkpoint_id:
            checkpoint_id = self._get_latest_checkpoint_id(thread_id=thread_id,user_id=user_id)
            if not checkpoint_id:
                return None

        doc_ref = self.checkpoints_collection_ref.document(user_id).collection("checkpoints").document(thread_id).collection(checkpoint_id).document("data")
        doc_snapshot = doc_ref.get()

        if not doc_snapshot.exists:
            return None

        checkpoint_data = doc_snapshot.to_dict()

        pending_writes = self._load_pending_writes(user_id = user_id, thread_id  = thread_id, checkpoint_id=checkpoint_id)

        return self._parse_checkpoint_data(
            config,
            thread_id,
            checkpoint_id,
            checkpoint_data,
            pending_writes=pending_writes,
        )

    def list(
            self,
            config: RunnableConfig,
            *,
            filter: Optional[dict[str, Any]] = None,
            before: Optional[RunnableConfig] = None,
            limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        user_id = config["configurable"]["user_id"]

        # Bygg en query for å hente sjekkpunkter
        query = self.checkpoints_collection_ref.document(user_id).collection("checkpoints").document(thread_id).collections()

        # Firestore API støtter ikke direkte filtrering og sortering på collection-IDer på denne måten.
        # En mer robust løsning ville vært en flat collection med thread_id som et felt.
        # Gitt den nåværende strukturen, henter vi ID-er og sorterer i minnet.

        collection_ids = [c.id for c in query]

        if before:
            before_id = get_checkpoint_id(before)
            collection_ids = [cid for cid in collection_ids if cid < before_id]

        # Sorter synkende for å få de nyeste først
        sorted_ids = sorted(collection_ids, reverse=True)

        if limit:
            sorted_ids = sorted_ids[:limit]

        for checkpoint_id in sorted_ids:
            # Gjenbruk get_tuple for å unngå kodeduplisering
            current_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                }
            }
            checkpoint_tuple = self.get_tuple(current_config)
            if checkpoint_tuple:
                yield checkpoint_tuple

    def _get_latest_checkpoint_id(self, user_id : str, thread_id: str) -> Optional[str]:
        collections = self.checkpoints_collection_ref.document(user_id).collection("checkpoints").document(thread_id).collections()
        collection_ids = [c.id for c in collections]

        # Sorterer for å finne den nyeste (antar at leksikografisk sortering er ok)
        if not collection_ids:
            return None
        return sorted(collection_ids, reverse=True)[0]

    def _load_pending_writes(self, user_id: str, thread_id: str, checkpoint_id: str) -> List[PendingWrite]:
        writes_query = (
            self.writes_collection_ref.document(user_id)
            .collection("writes")
            .document(thread_id)
            .collection(checkpoint_id)
            .order_by("idx")
        )

        writes = []
        for doc in writes_query.stream():
            data = doc.to_dict()
            value = self.firestore_serde.loads_typed((data["type"], data["value"]))
            writes.append((data["task_id"], data["channel"], value))

        # Grupper etter task_id
        grouped_writes = {}
        for task_id, channel, value in writes:
            if task_id not in grouped_writes:
                grouped_writes[task_id] = []
            grouped_writes[task_id].append((channel, value))

        # Konverter til PendingWrite-format
        return [
            (task_id, *write)
            for task_id, task_writes in grouped_writes.items()
            for write in task_writes
        ]

    def _parse_checkpoint_data(
            self,
            config: RunnableConfig,
            thread_id: str,
            checkpoint_id: str,
            data: dict,
            pending_writes: Optional[List[PendingWrite]] = None,
    ) -> Optional[CheckpointTuple]:
        if not data:
            return None

        checkpoint = self.firestore_serde.loads_typed((data["type"], data["checkpoint"]))
        metadata = self.firestore_serde.loads(data["metadata"])
        parent_checkpoint_id = data.get("parent_checkpoint_id")

        parent_config = (
            {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": parent_checkpoint_id,
                }
            }
            if parent_checkpoint_id
            else None
        )

        current_config = config.copy()
        current_config["configurable"]["checkpoint_id"] = checkpoint_id

        return CheckpointTuple(
            config=current_config,
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=pending_writes,
        )

    def read_in_user_sessions(self, user_id: str):
        user_sessions = self.checkpoints_collection_ref.document(user_id).collection("checkpoints")
        result = []
        all_sessions = user_sessions.list_documents()
        for session in all_sessions:
            result.append(session.id)
        return result

    def read_in_session_history(self, user_id: str, session_id: str):
        user_sessions = self.checkpoints_collection_ref.document(user_id).collection("checkpoints")
        session_chat = []
        session = user_sessions.document(session_id)
        collections = session.collections()
        for collection in collections:
            # print(collection.id)
            content = collection.document("data").get().to_dict()
            session_chat.append(content)
        return session_chat

    # --- Asynkrone metoder (wrappers) ---

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        return await asyncio.get_running_loop().run_in_executor(None, self.get_tuple, config)

    async def alist(
            self,
            config: RunnableConfig,
            *,
            filter: Optional[dict[str, Any]] = None,
            before: Optional[RunnableConfig] = None,
            limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        # Note: This is not a true async implementation, but wraps the sync iterator.
        sync_iterator = self.list(config, filter=filter, before=before, limit=limit)
        while True:
            try:
                item = await asyncio.get_running_loop().run_in_executor(None, next, sync_iterator)
                yield item
            except StopIteration:
                break

    async def aput(
            self,
            config: RunnableConfig,
            checkpoint: Checkpoint,
            metadata: CheckpointMetadata,
            new_versions: ChannelVersions
    ) -> RunnableConfig:
        return await asyncio.get_running_loop().run_in_executor(
            None, self.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(self, config: RunnableConfig, writes: List[Tuple[str, Any]], task_id: str) -> None:
        await asyncio.get_running_loop().run_in_executor(
            None, self.put_writes, config, writes, task_id
        )



