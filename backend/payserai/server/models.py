from datetime import datetime
from typing import Any, Generic, Optional, TypeVar
from uuid import UUID

from payserai.auth.schemas import UserRole
from payserai.configs import app_configs, constants
from payserai.connectors.models import DocumentBase, InputType
from payserai.db.models import (AllowepayseraiFilters, ChannelConfig,
                                Connector, Credential)
from payserai.db.models import DocumentSet as DocumentSetDBModel
from payserai.db.models import IndexAttempt, IndexingStatus, TaskStatus
from payserai.direct_qa.interfaces import payseraiAnswer, payseraiQuote
from payserai.payseraibot.slack.config import VALID_SLACK_FILTERS
from payserai.search.models import BaseFilters, QueryFlow, SearchType
from payserai.server.utils import mask_credential_dict
from pydantic import BaseModel, validator
from pydantic.generics import GenericModel

DataT = TypeVar("DataT")


class StatusResponse(GenericModel, Generic[DataT]):
    success: bool
    message: Optional[str] = None
    data: Optional[DataT] = None


class AuthTypeResponse(BaseModel):
    auth_type: AuthType


class VersionResponse(BaseModel):
    backend_version: str


class DataRequest(BaseModel):
    data: str


class HelperResponse(BaseModel):
    values: dict[str, str]
    details: list[str] | None = None


class UserInfo(BaseModel):
    id: str
    email: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    role: UserRole


class GoogleAppWebCredentials(BaseModel):
    client_id: str
    project_id: str
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    client_secret: str
    redirect_uris: list[str]
    javascript_origins: list[str]


class GoogleAppCredentials(BaseModel):
    web: GoogleAppWebCredentials


class GoogleServiceAccountKey(BaseModel):
    type: str
    project_id: str
    private_key_id: str
    private_key: str
    client_email: str
    client_id: str
    auth_uri: str
    token_uri: str
    auth_provider_x509_cert_url: str
    client_x509_cert_url: str
    universe_domain: str


class GoogleServiceAccountCredentialRequest(BaseModel):
    google_drive_delegated_user: str | None  # email of user to impersonate


class FileUploadResponse(BaseModel):
    file_paths: list[str]


class ObjectCreationIdResponse(BaseModel):
    id: int | str


class AuthStatus(BaseModel):
    authenticated: bool


class AuthUrl(BaseModel):
    auth_url: str


class GDriveCallback(BaseModel):
    state: str
    code: str


class UserRoleResponse(BaseModel):
    role: str


class BoostDoc(BaseModel):
    document_id: str
    semantic_id: str
    link: str
    boost: int
    hidden: bool


class BoostUpdateRequest(BaseModel):
    document_id: str
    boost: int


class HiddenUpdateRequest(BaseModel):
    document_id: str
    hidden: bool


class SearchDoc(BaseModel):
    document_id: str
    semantic_identifier: str
    link: str | None
    blurb: str
    source_type: str
    boost: int
    # whether the document is hidden when doing a standard search
    # since a standard search will never find a hidden doc, this can only ever
    # be `True` when doing an admin search
    hidden: bool
    score: float | None
    # Matched sections in the doc. Uses Vespa syntax e.g. <hi>TEXT</hi>
    # to specify that a set of words should be highlighted. For example:
    # ["<hi>the</hi> <hi>answer</hi> is 42", "the answer is <hi>42</hi>""]
    match_highlights: list[str]
    # when the doc was last updated
    updated_at: datetime | None

    def dict(self, *args: list, **kwargs: dict[str, Any]) -> dict[str, Any]:  # type: ignore
        initial_dict = super().dict(*args, **kwargs)  # type: ignore
        initial_dict["updated_at"] = (
            self.updated_at.isoformat() if self.updated_at else None
        )
        return initial_dict


class QuestionRequest(BaseModel):
    query: str
    filters: BaseFilters
    collection: str = DOCUMENT_INDEX_NAME
    search_type: SearchType = SearchType.HYBRID
    enable_auto_detect_filters: bool = True
    favor_recent: bool | None = None
    # Is this a real-time/streaming call or a question where payserai can take more time?
    real_time: bool = True
    # Pagination purposes, offset is in batches, not by document count
    offset: int | None = None


class QAFeedbackRequest(BaseModel):
    query_id: int
    feedback: QAFeedbackType


class SearchFeedbackRequest(BaseModel):
    query_id: int
    document_id: str
    document_rank: int
    click: bool
    search_feedback: SearchFeedbackType


class RetrievalDocs(BaseModel):
    top_documents: list[SearchDoc]


# First chunk of info for streaming QA
class QADocsResponse(RetrievalDocs):
    predicted_flow: QueryFlow
    predicted_search: SearchType
    time_cutoff: datetime | None
    favor_recent: bool

    def dict(self, *args: list, **kwargs: dict[str, Any]) -> dict[str, Any]:  # type: ignore
        initial_dict = super().dict(*args, **kwargs)  # type: ignore
        initial_dict["time_cutoff"] = (
            self.time_cutoff.isoformat() if self.time_cutoff else None
        )
        return initial_dict


# second chunk of info for streaming QA
class LLMRelevanceFilterResponse(BaseModel):
    relevant_chunk_indices: list[int]


class CreateChatSessionID(BaseModel):
    chat_session_id: int


class ChatFeedbackRequest(BaseModel):
    chat_session_id: int
    message_number: int
    edit_number: int
    is_positive: bool | None = None
    feedback_text: str | None = None


class CreateChatMessageRequest(BaseModel):
    chat_session_id: int
    message_number: int
    parent_edit_number: int | None
    message: str
    persona_id: int | None


class ChatMessageIdentifier(BaseModel):
    chat_session_id: int
    message_number: int
    edit_number: int


class RegenerateMessageRequest(ChatMessageIdentifier):
    persona_id: int | None


class ChatRenameRequest(BaseModel):
    chat_session_id: int
    name: str | None
    first_message: str | None


class RenameChatSessionResponse(BaseModel):
    new_name: str  # This is only really useful if the name is generated


class ChatSession(BaseModel):
    id: int
    name: str
    time_created: str


class ChatSessionsResponse(BaseModel):
    sessions: list[ChatSession]


class ChatMessageDetail(BaseModel):
    message_number: int
    edit_number: int
    parent_edit_number: int | None
    latest: bool
    message: str
    context_docs: RetrievalDocs | None
    message_type: MessageType
    time_sent: datetime


class ChatSessionDetailResponse(BaseModel):
    chat_session_id: int
    description: str
    messages: list[ChatMessageDetail]


class QueryValidationResponse(BaseModel):
    reasoning: str
    answerable: bool


class AdminSearchRequest(BaseModel):
    query: str
    filters: BaseFilters


class AdminSearchResponse(BaseModel):
    documents: list[SearchDoc]


class SearchResponse(RetrievalDocs):
    query_event_id: int
    source_type: list[DocumentSource] | None
    time_cutoff: datetime | None
    favor_recent: bool


class QAResponse(SearchResponse, payseraiAnswer):
    quotes: list[payseraiQuote] | None
    predicted_flow: QueryFlow
    predicted_search: SearchType
    eval_res_valid: bool | None = None
    llm_chunks_indices: list[int] | None = None
    error_msg: str | None = None


class UserByEmail(BaseModel):
    user_email: str


class IndexAttemptRequest(BaseModel):
    input_type: InputType = InputType.POLL
    connector_specific_config: dict[str, Any]


class IndexAttemptSnapshot(BaseModel):
    id: int
    status: IndexingStatus | None
    new_docs_indexed: int  # only includes completely new docs
    total_docs_indexed: int  # includes docs that are updated
    error_msg: str | None
    time_started: str | None
    time_updated: str

    @classmethod
    def from_index_attempt_db_model(
        cls, index_attempt: IndexAttempt
    ) -> "IndexAttemptSnapshot":
        return IndexAttemptSnapshot(
            id=index_attempt.id,
            status=index_attempt.status,
            new_docs_indexed=index_attempt.new_docs_indexed or 0,
            total_docs_indexed=index_attempt.total_docs_indexed or 0,
            error_msg=index_attempt.error_msg,
            time_started=index_attempt.time_started.isoformat()
            if index_attempt.time_started
            else None,
            time_updated=index_attempt.time_updated.isoformat(),
        )


class DeletionAttemptSnapshot(BaseModel):
    connector_id: int
    credential_id: int
    status: TaskStatus


class ConnectorBase(BaseModel):
    name: str
    source: DocumentSource
    input_type: InputType
    connector_specific_config: dict[str, Any]
    refresh_freq: int | None  # In seconds, None for one time index with no refresh
    disabled: bool


class ConnectorSnapshot(ConnectorBase):
    connector_id: int
    associated_credential_ids: list[int]
    creation_time: datetime
    last_updated_time: datetime

    @classmethod
    def from_connector_db_model(cls, connector: Connector) -> "ConnectorSnapshot":
        return ConnectorSnapshot(
            connector_id=connector.id,
            name=connector.name,
            source=connector.source,
            input_type=connector.input_type,
            connector_specific_config=connector.connector_specific_config,
            refresh_freq=connector.refresh_freq,
            associated_credential_ids=[
                association.credential.id for association in connector.credentials
            ],
            creation_time=connector.time_created,
            last_updated_time=connector.time_updated,
            disabled=connector.disabled,
        )


class RunConnectorRequest(BaseModel):
    connector_id: int
    credential_ids: list[int] | None


class CredentialBase(BaseModel):
    credential_json: dict[str, Any]
    # if `true`, then all Admins will have access to the credential
    admin_public: bool


class CredentialSnapshot(CredentialBase):
    id: int
    user_id: UUID | None
    time_created: datetime
    time_updated: datetime

    @classmethod
    def from_credential_db_model(cls, credential: Credential) -> "CredentialSnapshot":
        return CredentialSnapshot(
            id=credential.id,
            credential_json=mask_credential_dict(credential.credential_json)
            if MASK_CREDENTIAL_PREFIX
            else credential.credential_json,
            user_id=credential.user_id,
            admin_public=credential.admin_public,
            time_created=credential.time_created,
            time_updated=credential.time_updated,
        )


class ConnectorIndexingStatus(BaseModel):
    """Represents the latest indexing status of a connector"""

    cc_pair_id: int
    name: str | None
    connector: ConnectorSnapshot
    credential: CredentialSnapshot
    owner: str
    public_doc: bool
    last_status: IndexingStatus | None
    last_success: datetime | None
    docs_indexed: int
    error_msg: str | None
    latest_index_attempt: IndexAttemptSnapshot | None
    deletion_attempt: DeletionAttemptSnapshot | None
    is_deletable: bool


class ConnectorCredentialPairIdentifier(BaseModel):
    connector_id: int
    credential_id: int


class ConnectorCredentialPairMetadata(BaseModel):
    name: str | None


class ConnectorCredentialPairDescriptor(BaseModel):
    id: int
    name: str | None
    connector: ConnectorSnapshot
    credential: CredentialSnapshot


class ApiKey(BaseModel):
    api_key: str


class DocumentSetCreationRequest(BaseModel):
    name: str
    description: str
    cc_pair_ids: list[int]


class DocumentSetUpdateRequest(BaseModel):
    id: int
    description: str
    cc_pair_ids: list[int]


class CheckDocSetPublicRequest(BaseModel):
    document_set_ids: list[int]


class CheckDocSetPublicResponse(BaseModel):
    is_public: bool


class DocumentSet(BaseModel):
    id: int
    name: str
    description: str
    cc_pair_descriptors: list[ConnectorCredentialPairDescriptor]
    is_up_to_date: bool
    contains_non_public: bool

    @classmethod
    def from_model(cls, document_set_model: DocumentSetDBModel) -> "DocumentSet":
        return cls(
            id=document_set_model.id,
            name=document_set_model.name,
            description=document_set_model.description,
            contains_non_public=any(
                [
                    not cc_pair.is_public
                    for cc_pair in document_set_model.connector_credential_pairs
                ]
            ),
            cc_pair_descriptors=[
                ConnectorCredentialPairDescriptor(
                    id=cc_pair.id,
                    name=cc_pair.name,
                    connector=ConnectorSnapshot.from_connector_db_model(
                        cc_pair.connector
                    ),
                    credential=CredentialSnapshot.from_credential_db_model(
                        cc_pair.credential
                    ),
                )
                for cc_pair in document_set_model.connector_credential_pairs
            ],
            is_up_to_date=document_set_model.is_up_to_date,
        )


class IngestionDocument(BaseModel):
    document: DocumentBase
    connector_id: int | None = None  # Takes precedence over the name
    connector_name: str | None = None
    credential_id: int | None = None
    create_connector: bool = False  # Currently not allowed
    public_doc: bool = True  # To attach to the cc_pair, currently unused


class IngestionResult(BaseModel):
    document_id: str
    already_existed: bool


class SlackBotTokens(BaseModel):
    bot_token: str
    app_token: str


class SlackBotConfigCreationRequest(BaseModel):
    # currently, a persona is created for each slack bot config
    # in the future, `document_sets` will probably be replaced
    # by an optional `PersonaSnapshot` object. Keeping it like this
    # for now for simplicity / speed of development
    document_sets: list[int]
    channel_names: list[str]
    respond_tag_only: bool = False
    # If no team members, assume respond in the channel to everyone
    respond_team_member_list: list[str] = []
    answer_filters: list[AllowepayseraiFilters] = []

    @validator("answer_filters", pre=True)
    def validate_filters(cls, value: list[str]) -> list[str]:
        if any(test not in VALID_SLACK_FILTERS for test in value):
            raise ValueError(
                f"Slack Answer filters must be one of {VALID_SLACK_FILTERS}"
            )
        return value


class SlackBotConfig(BaseModel):
    id: int
    # currently, a persona is created for each slack bot config
    # in the future, `document_sets` will probably be replaced
    # by an optional `PersonaSnapshot` object. Keeping it like this
    # for now for simplicity / speed of development
    document_sets: list[DocumentSet]
    channel_config: ChannelConfig
