import secrets
from typing import cast

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Header
from fastapi import HTTPException
from sqlalchemy.orm import Session

from payserai.configs.constants import DocumentSource
from payserai.connectors.models import Document
from payserai.connectors.models import IndexAttemptMetadata
from payserai.db.connector import fetch_connector_by_id
from payserai.db.connector import fetch_ingestion_connector_by_name
from payserai.db.connector_credential_pair import get_connector_credential_pair
from payserai.db.credentials import fetch_credential_by_id
from payserai.db.engine import get_session
from payserai.dynamic_configs import get_dynamic_config_store
from payserai.dynamic_configs.interface import ConfigNotFoundError
from payserai.indexing.indexing_pipeline import build_indexing_pipeline
from payserai.server.models import ApiKey
from payserai.server.models import IngestionDocument
from payserai.server.models import IngestionResult
from payserai.utils.logger import setup_logger

logger = setup_logger()

# not using /api to avoid confusion with nginx api path routing
router = APIRouter(prefix="/payserai-api")

# Assumes this gives admin privileges, basic users should not be allowed to call any payserai apis
_PAYSERAI_API_KEY = "dn_ogcD-qmuT2NV0d0Me8Q9LhgMsYVXIlZsG-A0khB0"
# _PAYSERAI_API_KEY = "payserai_api_key"


def get_payserai_api_key(key_len: int = 30, dont_regenerate: bool = False) -> str | None:
    kv_store = get_dynamic_config_store()
    try:
        return str(kv_store.load(_PAYSERAI_API_KEY))
    except ConfigNotFoundError:
        if dont_regenerate:
            return None

    logger.info("Generating payserai API Key")

    api_key = "dn_" + secrets.token_urlsafe(key_len)
    kv_store.store(_PAYSERAI_API_KEY, api_key)

    return api_key


def delete_payserai_api_key() -> None:
    kv_store = get_dynamic_config_store()
    try:
        kv_store.delete(_PAYSERAI_API_KEY)
    except ConfigNotFoundError:
        pass


def api_key_dep(authorization: str = Header(...)) -> str:
    saved_key = get_payserai_api_key(dont_regenerate=True)
    token = authorization.removeprefix("Bearer ").strip()
    if token != saved_key or not saved_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return token


# Provides a way to recover if the api key is deleted for some reason
# Can also just restart the server to regenerate a new one
def api_key_dep_if_exist(authorization: str | None = Header(None)) -> str | None:
    token = authorization.removeprefix("Bearer ").strip() if authorization else None
    saved_key = get_payserai_api_key(dont_regenerate=True)
    if not saved_key:
        return None

    if token != saved_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return token


@router.post("/regenerate-key")
def regenerate_key(_: str | None = Depends(api_key_dep_if_exist)) -> ApiKey:
    delete_payserai_api_key()
    return ApiKey(api_key=cast(str, get_payserai_api_key()))


@router.post("/doc-ingestion")
def document_ingestion(
    doc_info: IngestionDocument,
    _: str = Depends(api_key_dep),
    db_session: Session = Depends(get_session),
) -> IngestionResult:
    """Currently only attaches docs to existing connectors (cc-pairs).
    Or to the default ingestion connector that is accessible to all users

    Things to note:
    - The document id if not provided is automatically generated from the semantic identifier
      so if the document source type etc is updated, it won't create a duplicate
    """
    if doc_info.credential_id:
        credential_id = doc_info.credential_id
        credential = fetch_credential_by_id(
            credential_id=credential_id,
            user=None,
            db_session=db_session,
            assume_admin=True,
        )
        if credential is None:
            raise ValueError("Invalid Credential for doc, does not exist.")
    else:
        credential_id = 0

    connector_id = doc_info.connector_id
    # If user provides id and name, id takes precedence
    if connector_id is not None:
        connector = fetch_connector_by_id(connector_id, db_session)
        if connector is None:
            raise ValueError("Invalid Connector for doc, id does not exist.")
    elif doc_info.connector_name:
        connector = fetch_ingestion_connector_by_name(
            doc_info.connector_name, db_session
        )
        if connector is None:
            raise ValueError("Invalid Connector for doc, name does not exist.")
        connector_id = connector.id
    else:
        connector_id = 0

    cc_pair = get_connector_credential_pair(
        connector_id=connector_id, credential_id=credential_id, db_session=db_session
    )
    if cc_pair is None:
        raise ValueError("Connector and Credential not associated.")

    # Disregard whatever value is passed, this must be True
    doc_info.document.from_ingestion_api = True

    document = Document.from_base(doc_info.document)

    # TODO once the frontend is updated with this enum, remove this logic
    if document.source == DocumentSource.INGESTION_API:
        document.source = DocumentSource.FILE

    indexing_pipeline = build_indexing_pipeline()

    new_doc, chunks = indexing_pipeline(
        documents=[document],
        index_attempt_metadata=IndexAttemptMetadata(
            connector_id=connector_id,
            credential_id=credential_id,
        ),
    )

    return IngestionResult(document_id=document.id, already_existed=not bool(new_doc))
