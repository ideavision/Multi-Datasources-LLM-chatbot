from collections.abc import Callable
from collections.abc import Iterator
from functools import partial
from typing import cast

from sqlalchemy.orm import Session

from payserai.configs.app_configs import DISABLE_GENERATIVE_AI
from payserai.configs.app_configs import QA_TIMEOUT
from payserai.configs.constants import QUERY_EVENT_ID
from payserai.db.feedback import update_query_event_llm_answer
from payserai.db.models import User
from payserai.direct_qa.factory import get_default_qa_model
from payserai.direct_qa.interfaces import payseraiAnswerPiece
from payserai.direct_qa.interfaces import StreamingError
from payserai.direct_qa.models import LLMMetricsContainer
from payserai.direct_qa.qa_utils import get_chunks_for_qa
from payserai.document_index.factory import get_default_document_index
from payserai.indexing.models import InferenceChunk
from payserai.search.payserai_helper import query_intent
from payserai.search.models import QueryFlow
from payserai.search.models import RerankMetricsContainer
from payserai.search.models import RetrievalMetricsContainer
from payserai.search.search_runner import chunks_to_search_docs
from payserai.search.search_runner import payserai_search
from payserai.search.search_runner import payserai_search_generator
from payserai.secondary_llm_flows.answer_validation import get_answer_validity
from payserai.secondary_llm_flows.source_filter import extract_question_source_filters
from payserai.secondary_llm_flows.time_filter import extract_question_time_filters
from payserai.server.models import LLMRelevanceFilterResponse
from payserai.server.models import QADocsResponse
from payserai.server.models import QAResponse
from payserai.server.models import QuestionRequest
from payserai.server.utils import get_json_line
from payserai.utils.logger import setup_logger
from payserai.utils.threadpool_concurrency import FunctionCall
from payserai.utils.threadpool_concurrency import run_functions_in_parallel
from payserai.utils.timing import log_function_time
from payserai.utils.timing import log_generator_function_time

logger = setup_logger()


@log_function_time()
def answer_qa_query(
    question: QuestionRequest,
    user: User | None,
    db_session: Session,
    disable_generative_answer: bool = DISABLE_GENERATIVE_AI,
    answer_generation_timeout: int = QA_TIMEOUT,
    enable_reflexion: bool = False,
    bypass_acl: bool = False,
    retrieval_metrics_callback: Callable[[RetrievalMetricsContainer], None]
    | None = None,
    rerank_metrics_callback: Callable[[RerankMetricsContainer], None] | None = None,
    llm_metrics_callback: Callable[[LLMMetricsContainer], None] | None = None,
) -> QAResponse:
    query = question.query
    offset_count = question.offset if question.offset is not None else 0
    logger.info(f"Received QA query: {query}")

    run_time_filters = FunctionCall(extract_question_time_filters, (question,), {})
    run_source_filters = FunctionCall(
        extract_question_source_filters, (question, db_session), {}
    )
    run_query_intent = FunctionCall(query_intent, (query,), {})

    parallel_results = run_functions_in_parallel(
        [
            run_time_filters,
            run_source_filters,
            run_query_intent,
        ]
    )

    time_cutoff, favor_recent = parallel_results[run_time_filters.result_id]
    source_filters = parallel_results[run_source_filters.result_id]
    predicted_search, predicted_flow = parallel_results[run_query_intent.result_id]

    # Set flow as search so frontend doesn't ask the user if they want to run QA over more docs
    if disable_generative_answer:
        predicted_flow = QueryFlow.SEARCH

    # Modifies the question object but nothing upstream uses it
    question.filters.time_cutoff = time_cutoff
    question.favor_recent = favor_recent
    question.filters.source_type = source_filters

    top_chunks, llm_chunk_selection, query_event_id = payserai_search(
        question=question,
        user=user,
        db_session=db_session,
        document_index=get_default_document_index(),
        bypass_acl=bypass_acl,
        retrieval_metrics_callback=retrieval_metrics_callback,
        rerank_metrics_callback=rerank_metrics_callback,
    )

    top_docs = chunks_to_search_docs(top_chunks)

    partial_response = partial(
        QAResponse,
        top_documents=chunks_to_search_docs(top_chunks),
        predicted_flow=predicted_flow,
        predicted_search=predicted_search,
        query_event_id=query_event_id,
        source_type=source_filters,
        time_cutoff=time_cutoff,
        favor_recent=favor_recent,
    )

    if disable_generative_answer or not top_docs:
        return partial_response(
            answer=None,
            quotes=None,
        )

    try:
        qa_model = get_default_qa_model(
            timeout=answer_generation_timeout, real_time_flow=question.real_time
        )
    except Exception as e:
        return partial_response(
            answer=None,
            quotes=None,
            error_msg=str(e),
        )

    llm_chunks_indices = get_chunks_for_qa(
        chunks=top_chunks,
        llm_chunk_selection=llm_chunk_selection,
        batch_offset=offset_count,
    )

    llm_chunks = [top_chunks[i] for i in llm_chunks_indices]

    logger.debug(
        f"Chunks fed to LLM: {[chunk.semantic_identifier for chunk in llm_chunks]}"
    )

    error_msg = None
    try:
        d_answer, quotes = qa_model.answer_question(
            query, llm_chunks, metrics_callback=llm_metrics_callback
        )
    except Exception as e:
        # exception is logged in the answer_question method, no need to re-log
        d_answer, quotes = None, None
        error_msg = f"Error occurred in call to LLM - {e}"  # Used in the QAResponse

    # update query event created by call to `payserai_search` with the LLM answer
    if d_answer and d_answer.answer is not None:
        update_query_event_llm_answer(
            db_session=db_session,
            llm_answer=d_answer.answer,
            query_id=query_event_id,
            user_id=None if user is None else user.id,
        )

    validity = None
    if not question.real_time and enable_reflexion and d_answer is not None:
        validity = False
        if d_answer.answer is not None:
            validity = get_answer_validity(query, d_answer.answer)

    return partial_response(
        answer=d_answer.answer if d_answer else None,
        quotes=quotes.quotes if quotes else None,
        eval_res_valid=validity,
        llm_chunks_indices=llm_chunks_indices,
        error_msg=error_msg,
    )


@log_generator_function_time()
def answer_qa_query_stream(
    question: QuestionRequest,
    user: User | None,
    db_session: Session,
    disable_generative_answer: bool = DISABLE_GENERATIVE_AI,
) -> Iterator[str]:
    logger.debug(
        f"Received QA query ({question.search_type.value} search): {question.query}"
    )
    logger.debug(f"Query filters: {question.filters}")

    answer_so_far: str = ""
    query = question.query
    offset_count = question.offset if question.offset is not None else 0

    run_time_filters = FunctionCall(extract_question_time_filters, (question,), {})
    run_source_filters = FunctionCall(
        extract_question_source_filters, (question, db_session), {}
    )
    run_query_intent = FunctionCall(query_intent, (query,), {})

    parallel_results = run_functions_in_parallel(
        [
            run_time_filters,
            run_source_filters,
            run_query_intent,
        ]
    )

    time_cutoff, favor_recent = parallel_results[run_time_filters.result_id]
    source_filters = parallel_results[run_source_filters.result_id]
    predicted_search, predicted_flow = parallel_results[run_query_intent.result_id]

    # Modifies the question object but nothing upstream uses it
    question.filters.time_cutoff = time_cutoff
    question.favor_recent = favor_recent
    question.filters.source_type = source_filters

    search_generator = payserai_search_generator(
        question=question,
        user=user,
        db_session=db_session,
        document_index=get_default_document_index(),
    )

    # first fetch and return to the UI the top chunks so the user can
    # immediately see some results
    top_chunks = cast(list[InferenceChunk], next(search_generator))
    top_docs = chunks_to_search_docs(top_chunks)
    initial_response = QADocsResponse(
        top_documents=top_docs,
        # if generative AI is disabled, set flow as search so frontend
        # doesn't ask the user if they want to run QA over more documents
        predicted_flow=QueryFlow.SEARCH
        if disable_generative_answer
        else predicted_flow,
        predicted_search=predicted_search,
        time_cutoff=time_cutoff,
        favor_recent=favor_recent,
    ).dict()
    yield get_json_line(initial_response)

    if not top_chunks:
        logger.debug("No Documents Found")
        return

    # next apply the LLM filtering
    llm_chunk_selection = cast(list[bool], next(search_generator))
    llm_chunks_indices = get_chunks_for_qa(
        chunks=top_chunks,
        llm_chunk_selection=llm_chunk_selection,
        batch_offset=offset_count,
    )
    llm_relevance_filtering_response = LLMRelevanceFilterResponse(
        relevant_chunk_indices=[
            index for index, value in enumerate(llm_chunk_selection) if value
        ]
    ).dict()
    yield get_json_line(llm_relevance_filtering_response)

    # finally get the query ID from the search generator for updating the
    # row in Postgres. This is the end of the `search_generator` - any future
    # calls to `next` will raise StopIteration
    query_event_id = cast(int, next(search_generator))

    if disable_generative_answer:
        logger.debug("Skipping QA because generative AI is disabled")
        return

    try:
        qa_model = get_default_qa_model()
    except Exception as e:
        logger.exception("Unable to get QA model")
        error = StreamingError(error=str(e))
        yield get_json_line(error.dict())
        return

    llm_chunks = [top_chunks[i] for i in llm_chunks_indices]
    logger.debug(
        f"Chunks fed to LLM: {[chunk.semantic_identifier for chunk in llm_chunks]}"
    )

    try:
        for response_packet in qa_model.answer_question_stream(query, llm_chunks):
            if response_packet is None:
                continue
            if (
                isinstance(response_packet, payseraiAnswerPiece)
                and response_packet.answer_piece
            ):
                answer_so_far = answer_so_far + response_packet.answer_piece
            logger.debug(f"Sending packet: {response_packet}")
            yield get_json_line(response_packet.dict())
    except Exception:
        # exception is logged in the answer_question method, no need to re-log
        logger.exception("Failed to run QA")
        error = StreamingError(error="The LLM failed to produce a useable response")
        yield get_json_line(error.dict())

    # update query event created by call to `payserai_search` with the LLM answer
    update_query_event_llm_answer(
        db_session=db_session,
        llm_answer=answer_so_far,
        query_id=query_event_id,
        user_id=None if user is None else user.id,
    )

    yield get_json_line({QUERY_EVENT_ID: query_event_id})
