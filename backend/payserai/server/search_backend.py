from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from payserai.auth.users import current_admin_user
from payserai.auth.users import current_user
from payserai.db.engine import get_session
from payserai.db.feedback import create_doc_retrieval_feedback
from payserai.db.feedback import update_query_event_feedback
from payserai.db.models import User
from payserai.direct_qa.answer_question import answer_qa_query
from payserai.direct_qa.answer_question import answer_qa_query_stream
from payserai.document_index.factory import get_default_document_index
from payserai.document_index.vespa.index import VespaIndex
from payserai.search.access_filters import build_access_filters_for_user
from payserai.search.payserai_helper import recommend_search_flow
from payserai.search.models import IndexFilters
from payserai.search.search_runner import chunks_to_search_docs
from payserai.search.search_runner import payserai_search
from payserai.secondary_llm_flows.query_validation import get_query_answerability
from payserai.secondary_llm_flows.query_validation import stream_query_answerability
from payserai.secondary_llm_flows.source_filter import extract_question_source_filters
from payserai.secondary_llm_flows.time_filter import extract_question_time_filters
from payserai.server.models import AdminSearchRequest
from payserai.server.models import AdminSearchResponse
from payserai.server.models import HelperResponse
from payserai.server.models import QAFeedbackRequest
from payserai.server.models import QAResponse
from payserai.server.models import QueryValidationResponse
from payserai.server.models import QuestionRequest
from payserai.server.models import SearchDoc
from payserai.server.models import SearchFeedbackRequest
from payserai.server.models import SearchResponse
from payserai.utils.logger import setup_logger
from payserai.utils.threadpool_concurrency import FunctionCall
from payserai.utils.threadpool_concurrency import run_functions_in_parallel

logger = setup_logger()

router = APIRouter()


"""Admin-only search endpoints"""


@router.post("/admin/search")
def admin_search(
    question: AdminSearchRequest,
    user: User | None = Depends(current_admin_user),
    db_session: Session = Depends(get_session),
) -> AdminSearchResponse:
    query = question.query
    logger.info(f"Received admin search query: {query}")

    user_acl_filters = build_access_filters_for_user(user, db_session)
    final_filters = IndexFilters(
        source_type=question.filters.source_type,
        document_set=question.filters.document_set,
        time_cutoff=question.filters.time_cutoff,
        access_control_list=user_acl_filters,
    )
    document_index = get_default_document_index()
    if not isinstance(document_index, VespaIndex):
        raise HTTPException(
            status_code=400,
            detail="Cannot use admin-search when using a non-Vespa document index",
        )

    matching_chunks = document_index.admin_retrieval(query=query, filters=final_filters)

    documents = chunks_to_search_docs(matching_chunks)

    # deduplicate documents by id
    deduplicated_documents: list[SearchDoc] = []
    seen_documents: set[str] = set()
    for document in documents:
        if document.document_id not in seen_documents:
            deduplicated_documents.append(document)
            seen_documents.add(document.document_id)
    return AdminSearchResponse(documents=deduplicated_documents)


"""Search endpoints for all"""


@router.post("/search-intent")
def get_search_type(
    question: QuestionRequest, _: User = Depends(current_user)
) -> HelperResponse:
    query = question.query
    return recommend_search_flow(query)


@router.post("/query-validation")
def query_validation(
    question: QuestionRequest, _: User = Depends(current_user)
) -> QueryValidationResponse:
    query = question.query
    reasoning, answerable = get_query_answerability(query)
    return QueryValidationResponse(reasoning=reasoning, answerable=answerable)


@router.post("/stream-query-validation")
def stream_query_validation(
    question: QuestionRequest, _: User = Depends(current_user)
) -> StreamingResponse:
    query = question.query
    return StreamingResponse(
        stream_query_answerability(query), media_type="application/json"
    )


@router.post("/document-search")
def handle_search_request(
    question: QuestionRequest,
    user: User | None = Depends(current_user),
    db_session: Session = Depends(get_session),
) -> SearchResponse:
    query = question.query
    logger.info(f"Received {question.search_type.value} " f"search query: {query}")

    functions_to_run = [
        FunctionCall(extract_question_time_filters, (question,), {}),
        FunctionCall(extract_question_source_filters, (question, db_session), {}),
    ]

    parallel_results = run_functions_in_parallel(functions_to_run)

    time_cutoff, favor_recent = parallel_results["extract_question_time_filters"]
    source_filters = parallel_results["extract_question_source_filters"]

    question.filters.time_cutoff = time_cutoff
    question.favor_recent = favor_recent
    question.filters.source_type = source_filters

    top_chunks, _, query_event_id = payserai_search(
        question=question,
        user=user,
        db_session=db_session,
        document_index=get_default_document_index(),
        skip_llm_chunk_filter=True,
    )

    top_docs = chunks_to_search_docs(top_chunks)

    return SearchResponse(
        top_documents=top_docs,
        query_event_id=query_event_id,
        source_type=source_filters,
        time_cutoff=time_cutoff,
        favor_recent=favor_recent,
    )


@router.post("/direct-qa")
def direct_qa(
    question: QuestionRequest,
    user: User | None = Depends(current_user),
    db_session: Session = Depends(get_session),
) -> QAResponse:
    # Everything handled via answer_qa_query which is also used by default
    # for the payseraiBot flow
    return answer_qa_query(question=question, user=user, db_session=db_session)


@router.post("/stream-direct-qa")
def stream_direct_qa(
    question: QuestionRequest,
    user: User | None = Depends(current_user),
    db_session: Session = Depends(get_session),
) -> StreamingResponse:
    packets = answer_qa_query_stream(
        question=question, user=user, db_session=db_session
    )
    return StreamingResponse(packets, media_type="application/json")


@router.post("/query-feedback")
def process_query_feedback(
    feedback: QAFeedbackRequest,
    user: User | None = Depends(current_user),
    db_session: Session = Depends(get_session),
) -> None:
    update_query_event_feedback(
        feedback=feedback.feedback,
        query_id=feedback.query_id,
        user_id=user.id if user is not None else None,
        db_session=db_session,
    )


@router.post("/doc-retrieval-feedback")
def process_doc_retrieval_feedback(
    feedback: SearchFeedbackRequest,
    user: User | None = Depends(current_user),
    db_session: Session = Depends(get_session),
) -> None:
    create_doc_retrieval_feedback(
        qa_event_id=feedback.query_id,
        document_id=feedback.document_id,
        document_rank=feedback.document_rank,
        clicked=feedback.click,
        feedback=feedback.search_feedback,
        user_id=user.id if user is not None else None,
        document_index=get_default_document_index(),
        db_session=db_session,
    )
