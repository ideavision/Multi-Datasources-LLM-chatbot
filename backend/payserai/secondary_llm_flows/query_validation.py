import re
from collections.abc import Iterator

from payserai.direct_qa.interfaces import payseraiAnswerPiece
from payserai.direct_qa.interfaces import StreamingError
from payserai.llm.factory import get_default_llm
from payserai.llm.utils import dict_based_prompt_to_langchain_prompt
from payserai.prompts.constants import ANSWERABLE_PAT
from payserai.prompts.constants import THOUGHT_PAT
from payserai.prompts.secondary_llm_flows import ANSWERABLE_PROMPT
from payserai.server.models import QueryValidationResponse
from payserai.server.utils import get_json_line
from payserai.utils.logger import setup_logger

logger = setup_logger()


def get_query_validation_messages(user_query: str) -> list[dict[str, str]]:
    messages = [
        {
            "role": "user",
            "content": ANSWERABLE_PROMPT.format(user_query=user_query),
        },
    ]

    return messages


def extract_answerability_reasoning(model_raw: str) -> str:
    reasoning_match = re.search(
        f"{THOUGHT_PAT.upper()}(.*?){ANSWERABLE_PAT.upper()}", model_raw, re.DOTALL
    )
    reasoning_text = reasoning_match.group(1).strip() if reasoning_match else ""
    return reasoning_text


def extract_answerability_bool(model_raw: str) -> bool:
    answerable_match = re.search(f"{ANSWERABLE_PAT.upper()}(.+)", model_raw)
    answerable_text = answerable_match.group(1).strip() if answerable_match else ""
    answerable = True if answerable_text.strip().lower() in ["true", "yes"] else False
    return answerable


def get_query_answerability(user_query: str) -> tuple[str, bool]:
    messages = get_query_validation_messages(user_query)
    filled_llm_prompt = dict_based_prompt_to_langchain_prompt(messages)
    model_output = get_default_llm().invoke(filled_llm_prompt)

    reasoning = extract_answerability_reasoning(model_output)
    answerable = extract_answerability_bool(model_output)

    return reasoning, answerable


def stream_query_answerability(user_query: str) -> Iterator[str]:
    messages = get_query_validation_messages(user_query)
    filled_llm_prompt = dict_based_prompt_to_langchain_prompt(messages)
    try:
        tokens = get_default_llm().stream(filled_llm_prompt)
        reasoning_pat_found = False
        model_output = ""
        hold_answerable = ""
        for token in tokens:
            model_output = model_output + token

            if ANSWERABLE_PAT.upper() in model_output:
                continue

            if not reasoning_pat_found and THOUGHT_PAT.upper() in model_output:
                reasoning_pat_found = True
                reason_ind = model_output.find(THOUGHT_PAT.upper())
                remaining = model_output[reason_ind + len(THOUGHT_PAT.upper()) :]
                if remaining:
                    yield get_json_line(
                        payseraiAnswerPiece(answer_piece=remaining).dict()
                    )
                continue

            if reasoning_pat_found:
                hold_answerable = hold_answerable + token
                if hold_answerable == ANSWERABLE_PAT.upper()[: len(hold_answerable)]:
                    continue
                yield get_json_line(
                    payseraiAnswerPiece(answer_piece=hold_answerable).dict()
                )
                hold_answerable = ""

        reasoning = extract_answerability_reasoning(model_output)
        answerable = extract_answerability_bool(model_output)

        yield get_json_line(
            QueryValidationResponse(reasoning=reasoning, answerable=answerable).dict()
        )
    except Exception as e:
        # exception is logged in the answer_question method, no need to re-log
        error = StreamingError(error=str(e))
        yield get_json_line(error.dict())
        logger.exception("Failed to validate Query")
    return
