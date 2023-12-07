import abc
from collections.abc import Callable
from collections.abc import Iterator

from pydantic import BaseModel

from payserai.direct_qa.models import LLMMetricsContainer
from payserai.indexing.models import InferenceChunk


class StreamingError(BaseModel):
    error: str


class payseraiAnswer(BaseModel):
    answer: str | None


class payseraiChatModelOut(BaseModel):
    model_raw: str
    action: str
    action_input: str


class payseraiAnswerPiece(BaseModel):
    """A small piece of a complete answer. Used for streaming back answers."""

    answer_piece: str | None  # if None, specifies the end of an Answer


class payseraiQuote(BaseModel):
    # This is during inference so everything is a string by this point
    quote: str
    document_id: str
    link: str | None
    source_type: str
    semantic_identifier: str
    blurb: str


class payseraiQuotes(BaseModel):
    quotes: list[payseraiQuote]


# Final int is for number of output tokens
AnswerQuestionReturn = tuple[payseraiAnswer, payseraiQuotes]
AnswerQuestionStreamReturn = Iterator[payseraiAnswerPiece | payseraiQuotes]


class QAModel:
    @property
    def requires_api_key(self) -> bool:
        """Is this model protected by security features
        Does it need an api key to access the model for inference"""
        return True

    def warm_up_model(self) -> None:
        """This is called during server start up to load the models into memory
        pass if model is accessed via API"""

    @abc.abstractmethod
    def answer_question(
        self,
        query: str,
        context_docs: list[InferenceChunk],
        metrics_callback: Callable[[LLMMetricsContainer], None] | None = None,
    ) -> AnswerQuestionReturn:
        raise NotImplementedError

    @abc.abstractmethod
    def answer_question_stream(
        self,
        query: str,
        context_docs: list[InferenceChunk],
    ) -> AnswerQuestionStreamReturn:
        raise NotImplementedError
