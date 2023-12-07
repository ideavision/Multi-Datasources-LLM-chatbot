from slack_sdk import WebClient
from sqlalchemy.orm import Session

from payserai.configs.constants import QAFeedbackType
from payserai.configs.constants import SearchFeedbackType
from payserai.payseraibot.slack.constants import DISLIKE_BLOCK_ACTION_ID
from payserai.payseraibot.slack.constants import LIKE_BLOCK_ACTION_ID
from payserai.payseraibot.slack.utils import decompose_block_id
from payserai.db.engine import get_sqlalchemy_engine
from payserai.db.feedback import create_doc_retrieval_feedback
from payserai.db.feedback import update_query_event_feedback
from payserai.document_index.factory import get_default_document_index


def handle_slack_feedback(
    block_id: str,
    feedback_type: str,
    client: WebClient,
    user_id_to_post_confirmation: str,
    channel_id_to_post_confirmation: str,
    thread_ts_to_post_confirmation: str,
) -> None:
    engine = get_sqlalchemy_engine()

    query_id, doc_id, doc_rank = decompose_block_id(block_id)

    with Session(engine) as db_session:
        if feedback_type in [LIKE_BLOCK_ACTION_ID, DISLIKE_BLOCK_ACTION_ID]:
            update_query_event_feedback(
                feedback=QAFeedbackType.LIKE
                if feedback_type == LIKE_BLOCK_ACTION_ID
                else QAFeedbackType.DISLIKE,
                query_id=query_id,
                user_id=None,  # no "user" for S bot for now
                db_session=db_session,
            )
        if feedback_type in [
            SearchFeedbackType.ENDORSE.value,
            SearchFeedbackType.REJECT.value,
        ]:
            if doc_id is None or doc_rank is None:
                raise ValueError("Missing information for Document Feedback")

            create_doc_retrieval_feedback(
                qa_event_id=query_id,
                document_id=doc_id,
                document_rank=doc_rank,
                user_id=None,
                document_index=get_default_document_index(),
                db_session=db_session,
                clicked=False,  # Not tracking this for Slack
                feedback=SearchFeedbackType.ENDORSE
                if feedback_type == SearchFeedbackType.ENDORSE.value
                else SearchFeedbackType.REJECT,
            )

    # post message to slack confirming that feedback was received
    client.chat_postEphemeral(
        channel=channel_id_to_post_confirmation,
        user=user_id_to_post_confirmation,
        thread_ts=thread_ts_to_post_confirmation,
        text="Thanks for your feedback!",
    )
