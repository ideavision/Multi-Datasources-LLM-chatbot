import os
from typing import cast

from payserai.dynamic_configs import get_dynamic_config_store
from payserai.server.models import SlackBotTokens


_SLACK_BOT_TOKENS_CONFIG_KEY = "slack_bot_tokens_config_key"


def fetch_tokens() -> SlackBotTokens:
    # first check env variables
    app_token = os.environ.get("PAYSERAI_BOT_SLACK_APP_TOKEN")
    bot_token = os.environ.get("PAYSERAI_BOT_SLACK_BOT_TOKEN")
    if app_token and bot_token:
        return SlackBotTokens(app_token=app_token, bot_token=bot_token)

    dynamic_config_store = get_dynamic_config_store()
    return SlackBotTokens(
        **cast(dict, dynamic_config_store.load(key=_SLACK_BOT_TOKENS_CONFIG_KEY))
    )


def save_tokens(
    tokens: SlackBotTokens,
) -> None:
    dynamic_config_store = get_dynamic_config_store()
    dynamic_config_store.store(
        key=_SLACK_BOT_TOKENS_CONFIG_KEY,
        val=dict(tokens),
    )
