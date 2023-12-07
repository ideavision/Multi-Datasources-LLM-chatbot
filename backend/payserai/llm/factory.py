from payserai.configs.app_configs import QA_TIMEOUT
from payserai.configs.model_configs import FAST_GEN_AI_MODEL_VERSION
from payserai.configs.model_configs import GEN_AI_MODEL_PROVIDER
from payserai.configs.model_configs import GEN_AI_MODEL_VERSION
from payserai.llm.chat_llm import DefaultMultiLLM
from payserai.llm.custom_llm import CustomModelServer
from payserai.llm.gpt_4_all import payseraiGPT4All
from payserai.llm.interfaces import LLM
from payserai.llm.utils import get_gen_ai_api_key


def get_default_llm(
    gen_ai_model_provider: str = GEN_AI_MODEL_PROVIDER,
    api_key: str | None = None,
    timeout: int = QA_TIMEOUT,
    use_fast_llm: bool = False,
) -> LLM:
    """A single place to fetch the configured LLM for payserai
    Also allows overriding certain LLM defaults"""
    model_version = FAST_GEN_AI_MODEL_VERSION if use_fast_llm else GEN_AI_MODEL_VERSION
    if api_key is None:
        api_key = get_gen_ai_api_key()

    if gen_ai_model_provider.lower() == "custom":
        return CustomModelServer(api_key=api_key, timeout=timeout)

    if gen_ai_model_provider.lower() == "gpt4all":
        return payseraiGPT4All(model_version=model_version, timeout=timeout)

    return DefaultMultiLLM(
        model_version=model_version, api_key=api_key, timeout=timeout
    )
