import base64
from agent.basemodels import AttachmentModel


def get_mock_pdf_content() -> str:
    """Base64-encoded minimal valid PDF for testing."""
    # Minimal valid PDF
    pdf_bytes = (
        b"%PDF-1.0\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n"
        b"0000000058 00000 n \n0000000115 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
    )
    return base64.b64encode(pdf_bytes).decode("utf-8")


def get_mock_text_content() -> str:
    """Plain text content for testing."""
    return "Dette er et testdokument med innhold om en eiendomstvist i Stavanger kommune."


def get_mock_pdf_attachment() -> AttachmentModel:
    return AttachmentModel(
        filename="stevning_2024.pdf",
        file_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        content=get_mock_pdf_content(),
        path="user123/session456/a1b2c3d4-e5f6-7890-abcd-ef1234567890.pdf",
        file_type="application/pdf",
        size=2048,
        query_id="q1-test-query-id",
    )


def get_mock_text_attachment() -> AttachmentModel:
    return AttachmentModel(
        filename="epost_korrespondanse.txt",
        file_id="b2c3d4e5-f6a7-8901-bcde-f12345678901",
        content=get_mock_text_content(),
        path="user123/session456/b2c3d4e5-f6a7-8901-bcde-f12345678901.txt",
        file_type="text/plain",
        size=512,
        query_id="q1-test-query-id",
    )


def get_mock_attachments_list() -> list[AttachmentModel]:
    return [get_mock_pdf_attachment(), get_mock_text_attachment()]
