import base64
from langchain_core.documents import Document
from models.api_request_models import AttachmentModel


# ============================================
#           DOCUMENT PROCESSOR DATA
# ============================================

def get_mock_pdf_bytes_with_text() -> bytes:
    """Minimal valid PDF with extractable text for testing parse_pdf."""
    # This creates a PDF with actual text content using PDF stream objects
    content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
        b"4 0 obj<</Length 44>>\nstream\nBT /F1 12 Tf 100 700 Td (Testdokument for rettssak om eiendomstvist i Stavanger) Tj ET\nendstream\nendobj\n"
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000360 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n429\n%%EOF"
    )
    return content


def get_mock_pdf_bytes_empty() -> bytes:
    """Minimal valid PDF with no extractable text (needs OCR)."""
    content = (
        b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
    )
    return content


def get_mock_pdf_base64_with_text() -> str:
    """Base64 encoded PDF with text for process_attachment testing."""
    return base64.b64encode(get_mock_pdf_bytes_with_text()).decode("utf-8")


def get_mock_pdf_base64_empty() -> str:
    """Base64 encoded empty PDF for process_attachment testing."""
    return base64.b64encode(get_mock_pdf_bytes_empty()).decode("utf-8")


def get_mock_text_content() -> str:
    """Norwegian legal text content for parse_text testing."""
    return (
        "Stevning i sak om eiendomstvist.\n\n"
        "Saksøker Anders Kristiansen og Berit Kristiansen kjøpte eiendommen "
        "Fjellveien 42A i Stavanger den 15. juni 2019 for kr 4 500 000. "
        "Etter overtakelse ble det oppdaget flere vesentlige mangler ved eiendommen, "
        "herunder grenseoverskridelse mot naboeiendommen, lekkasje i kjeller og "
        "problemer med betongdekke i garasjen.\n\n"
        "Det gjøres gjeldende at eiendommen var i vesentlig dårligere stand enn det "
        "kjøperne hadde grunn til å forvente basert på kjøpekontrakten og "
        "selgers opplysninger. Saksøkte Carl Danielsen er ansvarlig for å dekke "
        "utbedringskostnadene som er beregnet til mellom kr 1 195 000 og kr 6 350 000.\n\n"
        "Saksøkerne anfører at det foreligger brudd på avhendingslovas bestemmelser "
        "om opplysningsplikt og at eiendommen har en mangel etter avhendingslova § 3-9."
    )


def get_mock_long_text_content() -> str:
    """Longer text that will produce multiple chunks."""
    base = get_mock_text_content()
    # Repeat to ensure multiple chunks with default chunk_size=800
    return (base + "\n\n") * 5


def get_mock_metadata() -> dict:
    """Standard metadata dict for document processing."""
    return {
        "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "session_id": "s1-test-session-id",
    }


# ============================================
#           VECTORSTORE DATA
# ============================================

def get_mock_documents() -> list[Document]:
    """List of Document objects for vector store testing."""
    return [
        Document(
            page_content="Saksøker kjøpte eiendommen Fjellveien 42A i Stavanger den 15. juni 2019.",
            metadata={
                "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "session_id": "s1-test-session-id",
                "chunk": 0,
                "total_chunks": 3,
            },
        ),
        Document(
            page_content="Det ble oppdaget grenseoverskridelse mot naboeiendommen etter overtakelse.",
            metadata={
                "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "session_id": "s1-test-session-id",
                "chunk": 1,
                "total_chunks": 3,
            },
        ),
        Document(
            page_content="Utbedringskostnadene er beregnet til mellom kr 1 195 000 og kr 6 350 000.",
            metadata={
                "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "session_id": "s1-test-session-id",
                "chunk": 2,
                "total_chunks": 3,
            },
        ),
    ]


def get_mock_query_results() -> list[Document]:
    """Simulated query results from vector store."""
    return [
        Document(
            page_content="Saksøker kjøpte eiendommen Fjellveien 42A i Stavanger den 15. juni 2019.",
            metadata={
                "file_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "session_id": "s1-test-session-id",
                "chunk": 0,
            },
        ),
    ]


def get_mock_chroma_get_all_response() -> dict:
    """Simulated response from Chroma collection.get()."""
    return {
        "documents": [
            "Saksøker kjøpte eiendommen Fjellveien 42A.",
            "Grenseoverskridelse mot naboeiendommen.",
            "Utbedringskostnader beregnet til mellom kr 1 195 000 og kr 6 350 000.",
        ],
        "metadatas": [
            {"file_id": "file1", "chunk": 0},
            {"file_id": "file1", "chunk": 1},
            {"file_id": "file1", "chunk": 2},
        ],
        "ids": ["id-1", "id-2", "id-3"],
    }


def get_mock_pdf_attachment_for_processing() -> AttachmentModel:
    return AttachmentModel(
        filename="stevning_2024.pdf",
        file_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        content=get_mock_pdf_base64_with_text(),
        path="user123/session456/a1b2c3d4.pdf",
        file_type="application/pdf",
        size=2048,
        query_id="q1-test-query-id",
    )


def get_mock_text_attachment_for_processing() -> AttachmentModel:
    return AttachmentModel(
        filename="epost_korrespondanse.txt",
        file_id="b2c3d4e5-f6a7-8901-bcde-f12345678901",
        content=get_mock_text_content(),
        path="user123/session456/b2c3d4e5.txt",
        file_type="text/plain",
        size=512,
        query_id="q1-test-query-id",
    )
