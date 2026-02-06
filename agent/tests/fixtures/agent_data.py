"""
Fixture data for Agent tests.
Contains realistic mock data for testing Agent class methods.
"""

from agent.basemodels import *
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.documents import Document
from langchain_core.messages import AIMessageChunk


# ============================================
#           MOCK REQUEST DATA
# ============================================

def get_mock_ask_agent_request() -> AskAgentRequest:
    """Returns a mock AskAgentRequest for testing."""
    return AskAgentRequest(
        question="Hva er de viktigste faktaene i denne saken?",
        session_id="8fbac4e4-c2ff-4f58-95ba-7836f207a89d",
        query_id="0c22552d-8bee-4c24-a099-335c80db5573",
        project_id="ce119cd7-2c72-4400-8133-a08888b747ff",
        llm_model="google_gemini-2.5-flash",
        attachments=[]
    )


def get_mock_ask_agent_request_with_attachments() -> AskAgentRequest:
    """Returns a mock AskAgentRequest with attachments for testing."""
    return AskAgentRequest(
        question="Analyser disse dokumentene og oppsummer hovedpunktene",
        session_id="8fbac4e4-c2ff-4f58-95ba-7836f207a89d",
        query_id="0c22552d-8bee-4c24-a099-335c80db5573",
        project_id="ce119cd7-2c72-4400-8133-a08888b747ff",
        llm_model="google_gemini-2.5-flash",
        attachments=[
            AttachmentModel(
                file_id="fc545f59-ac93-4cda-8b41-83eed0d04ee3",
                filename="2023-08-25_kjoepekontrakt.pdf",
                file_type="application/pdf",
                content="""KJØPEKONTRAKT

Mellom Camilla Marie Hansen og Daniel Erik Hansen (selgere)
og Andreas Nilsen og Berit Johansen (kjøpere).

Eiendom: Granveien 15B, Oslo
Kjøpesum: NOK 15 500 000,-
Overtakelse: 11. november 2023

Kjøper har mottatt og gjennomgått tilstandsrapport.
Eiendommen selges med boligselgerforsikring.
Standard vilkår i Norges Eiendomsmeglerforbunds kjøpekontrakt legges til grunn.

Medfølgende dokumentasjon:
- Tilstandsrapport datert 30. mars 2023 fra ProTakst AS v/David Storvik
""",
                size=4944,
                path="53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/fc545f59-ac93-4cda-8b41-83eed0d04ee3.txt",
                query_id="0c22552d-8bee-4c24-a099-335c80db5573"
            ),
            AttachmentModel(
                file_id="cbb594a1c8bda2dbec6904b560d5c3ad",
                filename="2023-08-21_epost_selger_til_kjoeper.txt",
                file_type="text/plain",
                content="""Fra: Daniel Hansen <daniel.hansen@email.no>
Til: Andreas Nilsen <andreas.nilsen@email.no>
Dato: 21. august 2023
Emne: Svar på spørsmål om boligen

Hei Andreas og Berit,

Takk for hyggelig visning i går! Her kommer svar på spørsmålene deres:

Varmepumpene: Ja, de fungerer fint.
Utbedringer: Nei, vi har ingen planlagte utbedringer. Alt vi ønsket å gjøre er ferdig.
Huset er klart til innflytting.

Som dere så gjorde vi bad oppe i 2020/2021 med fagfolk (Moderne Bygg),
og vi skiftet tak i 2021 (AllFix).

Elektrikeren har også vært innom og gjort det som skulle gjøres.
Alt er sjekket og i orden.

Dere vil få all dokumentasjon på arbeidene vi har gjort.

Mvh,
Daniel og Camilla
""",
                size=1094,
                path="53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/cbb594a1c8bda2dbec6904b560d5c3ad.txt",
                query_id="0c22552d-8bee-4c24-a099-335c80db5573"
            )
        ]
    )


# ============================================
#           MOCK PROJECT DATA
# ============================================

def get_mock_project_data() -> dict:
    """Returns mock project data as returned from load_project."""
    return {
        "factsheet": get_mock_factsheet(),
        "attachments": get_mock_attachments()
    }


def get_mock_factsheet() -> FactSheet:
    """Returns a mock FactSheet for testing."""
    return FactSheet(
        project_id="ce119cd7-2c72-4400-8133-a08888b747ff",
        title="Eiendomskjøpssak - Mangler ved Granveien 15B",
        background="""Andreas Nilsen og Berit Johansen kjøpte en enebolig på Granveien 15B i Oslo
i august 2023 for 15,5 millioner NOK. Overtakelsen var 11. november 2023.
Etter overtakelsen oppdaget de flere alvorlige mangler, inkludert elektriske feil
og problemer med pipa. De sendte reklamasjon i desember 2023.""",
        parties=[
            Party(
                party_id="2bd1e4d6-506c-4676-83b3-7c6c56f838d6",
                legal_name="Andreas Nilsen",
                role="plaintiff",
                entity_type="individual",
                key_contact=KeyContact(name="Andreas Nilsen", email="andreas.nilsen@email.no")
            ),
            Party(
                party_id="2a0108fa-eadc-444c-889b-6197d43d3952",
                legal_name="Berit Johansen",
                role="plaintiff",
                entity_type="individual",
                key_contact=KeyContact(name="Berit Johansen", email="berit.johansen@email.no")
            ),
            Party(
                party_id="seller-001",
                legal_name="Daniel Erik Hansen",
                role="defendant",
                entity_type="individual",
                key_contact=KeyContact(name="Daniel Hansen", email="daniel.hansen@email.no")
            ),
            Party(
                party_id="seller-002",
                legal_name="Camilla Marie Hansen",
                role="defendant",
                entity_type="individual",
                key_contact=KeyContact(name="Camilla Hansen")
            )
        ],
        events=[
            Event(
                event_id="event-001",
                event_date="2023-08-25",
                event_name="ContractSigned",
                description="Kjøpekontrakt for Granveien 15B ble signert",
                parties=["plaintiff", "defendant"],
                significance="high",
                disputed=False,
                category="transaction"
            ),
            Event(
                event_id="event-002",
                event_date="2023-11-11",
                event_name="PropertyTakeover",
                description="Overtakelse av eiendommen Granveien 15B",
                parties=["plaintiff"],
                significance="high",
                disputed=False,
                category="transaction"
            ),
            Event(
                event_id="event-003",
                event_date="2023-12-01",
                event_name="DefectsDiscovered",
                description="Kjøperne oppdaget elektriske feil og problemer med pipa",
                parties=["plaintiff"],
                significance="high",
                disputed=True,
                category="dispute"
            )
        ],
        claims=[
            Claim(
                claim_id="claim-001",
                file_id="file-001",
                party_role="plaintiff",
                legal_basis="Avhendingslova § 3-9 - Mangel ved eiendommen",
                relief_sought="Prisavslag eller erstatning for utbedringskostnader"
            )
        ],
        damages=[
            Damage(
                damage_id="damage-001",
                file_id="file-001",
                party_role="plaintiff",
                category="property",
                amount="150000",
                currency="NOK",
                description="Utbedring av elektrisk anlegg"
            ),
            Damage(
                damage_id="damage-002",
                file_id="file-001",
                party_role="plaintiff",
                category="property",
                amount="75000",
                currency="NOK",
                description="Rehabilitering av pipe"
            )
        ],
        deadlines=[
            Deadline(
                deadline_id="deadline-001",
                file_id="file-001",
                deadline_date="2024-06-01",
                description="Frist for å reise søksmål (5 år fra overtakelse)",
                party_role="plaintiff"
            )
        ],
        disputed_facts=[
            "Selger hadde kunnskap om de elektriske feilene før salget",
            "Selgers opplysninger om at 'alt er sjekket og i orden' var uriktige"
        ],
        undisputed_facts=[
            "Eiendommen ble solgt for NOK 15 500 000",
            "Overtakelse skjedde 11. november 2023",
            "Tilstandsrapport fra ProTakst AS var vedlagt kjøpekontrakten",
            "Selger opplyste at elektrikeren hadde vært innom og gjort det som skulle gjøres"
        ],
        governing_law=GoverningLaw(
            primary_jurisdiction="Norsk rett",
            key_areas=["Avhendingslova", "Kontraktsrett", "Erstatningsrett"],
            procedural_law="tvisteloven"
        )
    )


def get_mock_attachments() -> list[Attachment]:
    """Returns mock attachments list for testing."""
    return [
        Attachment(
            file_id="fc545f59-ac93-4cda-8b41-83eed0d04ee3",
            filename="2023-08-25_kjoepekontrakt.pdf",
            path="53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/fc545f59-ac93-4cda-8b41-83eed0d04ee3.pdf",
            file_type="application/pdf",
            size=4944,
            description="Kjøpekontrakt for eiendommen Granveien 15B mellom selgere og kjøpere",
            category="agreement",
            significance="high",
            party_roles=["plaintiff", "defendant"],
            key_provisions=[
                "Kjøpesum: NOK 15 500 000,-",
                "Overtakelse: 11. november 2023",
                "Eiendommen selges med boligselgerforsikring",
                "Tilstandsrapport datert 30. mars 2023 fra ProTakst AS"
            ],
            file_date="2023-08-25"
        ),
        Attachment(
            file_id="cbb594a1c8bda2dbec6904b560d5c3ad",
            filename="2023-08-21_epost_selger_til_kjoeper.txt",
            path="53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/cbb594a1c8bda2dbec6904b560d5c3ad.txt",
            file_type="text/plain",
            size=1094,
            description="E-post fra selger til kjøper med svar på spørsmål om boligens tilstand",
            category="correspondence",
            significance="high",
            party_roles=["plaintiff", "defendant"],
            key_provisions=[
                "Varmepumpene fungerer fint",
                "Ingen planlagte utbedringer",
                "Bad renovert 2020/2021 av Moderne Bygg",
                "Tak skiftet i 2021 av AllFix",
                "Elektriker har sjekket og alt er i orden"
            ],
            file_date="2023-08-21"
        )
    ]


# ============================================
#           MOCK LLM RESPONSES
# ============================================

def get_mock_ai_message() -> AIMessage:
    """Returns a mock AIMessage response."""
    return AIMessage(
        content="""Basert på dokumentene kan jeg oppsummere følgende hovedpunkter:

**Sakens bakgrunn:**
Andreas Nilsen og Berit Johansen kjøpte eiendommen Granveien 15B i Oslo for 15,5 millioner NOK.
Overtakelsen var 11. november 2023.

**Mangler oppdaget:**
Etter overtakelsen ble det oppdaget alvorlige mangler:
- Elektriske feil
- Problemer med pipa

**Selgers opplysninger:**
Før kjøpet opplyste selger at:
- Elektrikeren hadde vært innom og sjekket alt
- Alle planlagte utbedringer var fullført
- Huset var klart til innflytting

**Rettslig grunnlag:**
Saken gjelder mulig brudd på avhendingslova § 3-9 om mangler ved eiendommen.""",
        id="ai-msg-001"
    )


def get_mock_ai_message_with_tool_calls() -> AIMessage:
    """Returns a mock AIMessage with tool calls."""
    return AIMessage(
        content="",
        id="ai-msg-002",
        tool_calls=[
            {
                "name": "run_query",
                "args": {"query": "SELECT * FROM relevant_laws WHERE topic = 'avhendingslova'"},
                "id": "tool-call-001"
            }
        ]
    )


def get_mock_tool_result() -> dict:
    """Returns mock tool execution result."""
    return {
        "data": [
            {
                "law_id": "avhl-3-9",
                "title": "Avhendingslova § 3-9",
                "content": "Eigedomen har mangel dersom han ikkje er i samsvar med det som følgjer av avtala"
            },
            {
                "law_id": "avhl-4-12",
                "title": "Avhendingslova § 4-12",
                "content": "Har eigedomen mangel, kan kjøparen krevje prisavslag"
            }
        ],
        "status": "success"
    }


# ============================================
#           MOCK STREAM DATA
# ============================================

def get_mock_stream_events() -> list[dict]:
    """Returns mock stream events for testing stream_response."""
    return [
        {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": AIMessageChunk(content="Basert på ")
            },
            "name": "ChatModel"
        },
        {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": AIMessageChunk(content="dokumentene ")
            },
            "name": "ChatModel"
        },
        {
            "event": "on_chat_model_stream",
            "data": {
                "chunk": AIMessageChunk(content="kan jeg oppsummere...")
            },
            "name": "ChatModel"
        },
        {
            "event": "on_chain_end",
            "data": {
                "output": {
                    "messages": [get_mock_ai_message()]
                }
            },
            "name": "call_llm"
        }
    ]


# ============================================
#           MOCK INITIAL INPUT
# ============================================

def get_mock_initial_input() -> InitialInput:
    """Returns a mock InitialInput for testing initialize_project."""
    return InitialInput(
        title="Eiendomskjøpssak - Mangler ved Granveien 15B",
        background="""Andreas Nilsen og Berit Johansen kjøpte en enebolig på Granveien 15B i Oslo
i august 2023 for 15,5 millioner NOK. Overtakelsen var 11. november 2023.
Etter overtakelsen oppdaget de flere alvorlige mangler, inkludert elektriske feil
og problemer med pipa. De sendte reklamasjon i desember 2023, og et forsikringsselskap
har svart på reklamasjonen.""",
        parties=[
            Party(
                party_id="2bd1e4d6-506c-4676-83b3-7c6c56f838d6",
                legal_name="Andreas Nilsen",
                role="plaintiff",
                entity_type="individual"
            ),
            Party(
                party_id="2a0108fa-eadc-444c-889b-6197d43d3952",
                legal_name="Berit Johansen",
                role="plaintiff",
                entity_type="individual"
            ),
            Party(
                party_id="e1dd3160-7f06-41d3-a5df-76d3a6d55b63",
                legal_name="Ukjent forsikringsselskap",
                role="respondent",
                entity_type="company"
            )
        ]
    )


# ============================================
#           MOCK DOCUMENT ANALYSIS
# ============================================

def get_mock_analyzed_doc() -> dict:
    """Returns mock analyzed document result."""
    return {
        "file": Attachment(
            file_id="fc545f59-ac93-4cda-8b41-83eed0d04ee3",
            filename="2023-08-25_kjoepekontrakt.pdf",
            path="53d63d18-cfa1-416e-96e8-770c8f66507b/8fbac4e4-c2ff-4f58-95ba-7836f207a89d/fc545f59-ac93-4cda-8b41-83eed0d04ee3.pdf",
            file_type="application/pdf",
            size=4944,
            description="Kjøpekontrakt for eiendommen Granveien 15B, Oslo, mellom Camilla Marie Hansen og Daniel Erik Hansen (selgere) og Andreas Nilsen og Berit Johansen (kjøpere)",
            category="agreement",
            significance="high",
            party_roles=["plaintiff", "defendant"],
            key_provisions=[
                "Kjøpesum: NOK 15 500 000,-",
                "Overtakelse: 11. november 2023",
                "Kjøper har mottatt og gjennomgått tilstandsrapport",
                "Eiendommen selges med boligselgerforsikring"
            ],
            file_date="2023-08-25",
            deadlines=[
                Deadline(
                    deadline_id="deadline-from-doc-001",
                    deadline_date="2023-11-11",
                    description="Overtakelsesdato for eiendommen Granveien 15B",
                    file_id="fc545f59-ac93-4cda-8b41-83eed0d04ee3",
                    party_role="plaintiff"
                )
            ]
        ),
        "events": [
            Event(
                event_id="event-from-doc-001",
                event_date="2023-08-25",
                event_name="ContractSigned",
                description="Kjøpekontrakt for Granveien 15B ble signert",
                parties=["plaintiff", "defendant"],
                significance="high",
                disputed=False,
                category="transaction",
                file_id="fc545f59-ac93-4cda-8b41-83eed0d04ee3"
            ),
            Event(
                event_id="event-from-doc-002",
                event_date="2023-11-11",
                event_name="PropertyTakeover",
                description="Planlagt overtakelse av eiendommen",
                parties=["plaintiff"],
                significance="high",
                disputed=False,
                category="transaction",
                file_id="fc545f59-ac93-4cda-8b41-83eed0d04ee3"
            )
        ]
    }


# ============================================
#      MOCK VECTOR STORE DOCUMENTS
# ============================================

def get_mock_vector_store_docs() -> list[Document]:
    """Returns mock documents from vector store query."""
    return [
        Document(
            page_content="""KJØPEKONTRAKT

Mellom Camilla Marie Hansen og Daniel Erik Hansen (selgere)
og Andreas Nilsen og Berit Johansen (kjøpere).

Eiendom: Granveien 15B, Oslo
Kjøpesum: NOK 15 500 000,-
Overtakelse: 11. november 2023""",
            metadata={
                "file_id": "fc545f59-ac93-4cda-8b41-83eed0d04ee3",
                "chunk_id": "chunk-001",
                "filename": "2023-08-25_kjoepekontrakt.pdf"
            }
        ),
        Document(
            page_content="""Kjøper har mottatt og gjennomgått tilstandsrapport.
Eiendommen selges med boligselgerforsikring.
Standard vilkår i Norges Eiendomsmeglerforbunds kjøpekontrakt legges til grunn.

Medfølgende dokumentasjon:
- Tilstandsrapport datert 30. mars 2023 fra ProTakst AS v/David Storvik""",
            metadata={
                "file_id": "fc545f59-ac93-4cda-8b41-83eed0d04ee3",
                "chunk_id": "chunk-002",
                "filename": "2023-08-25_kjoepekontrakt.pdf"
            }
        ),
        Document(
            page_content="""Fra: Daniel Hansen
Til: Andreas Nilsen
Dato: 21. august 2023

Varmepumpene: Ja, de fungerer fint.
Utbedringer: Nei, vi har ingen planlagte utbedringer.
Elektrikeren har også vært innom og gjort det som skulle gjøres.
Alt er sjekket og i orden.""",
            metadata={
                "file_id": "cbb594a1c8bda2dbec6904b560d5c3ad",
                "chunk_id": "chunk-001",
                "filename": "2023-08-21_epost_selger_til_kjoeper.txt"
            }
        )
    ]


# ============================================
#           MOCK AGENT STATE
# ============================================

def get_mock_agent_state() -> dict:
    """Returns mock agent state for testing."""
    return {
        "messages": [
            SystemMessage(content="Du er en juridisk assistent som hjelper med eiendomssaker."),
            HumanMessage(
                content="Hva er hovedpunktene i denne saken?",
                additional_kwargs={
                    "query_id": "0c22552d-8bee-4c24-a099-335c80db5573",
                    "session_id": "8fbac4e4-c2ff-4f58-95ba-7836f207a89d",
                    "attachments": []
                }
            ),
            AIMessage(content="Basert på dokumentene ser dette ut til å være en eiendomstvist..."),
            HumanMessage(content="Kan du utdype de elektriske problemene?"),
            AIMessage(content="De elektriske problemene inkluderer...")
        ],
        "factsheet": get_mock_factsheet(),
        "attachments": get_mock_attachments(),
        "tool_results": []
    }
