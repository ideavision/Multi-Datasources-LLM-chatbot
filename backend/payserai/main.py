import nltk  # type:ignore
import torch
import uvicorn
from fastapi import FastAPI
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from httpx_oauth.clients.google import GoogleOAuth2
from sqlalchemy.orm import Session

from payserai import __version__
from payserai.auth.schemas import UserCreate
from payserai.auth.schemas import UserRead
from payserai.auth.schemas import UserUpdate
from payserai.auth.users import auth_backend
from payserai.auth.users import fastapi_users
from payserai.chat.personas import load_personas_from_yaml
from payserai.configs.app_configs import APP_HOST
from payserai.configs.app_configs import APP_PORT
from payserai.configs.app_configs import AUTH_TYPE
from payserai.configs.app_configs import DISABLE_GENERATIVE_AI
from payserai.configs.app_configs import MODEL_SERVER_HOST
from payserai.configs.app_configs import MODEL_SERVER_PORT
from payserai.configs.app_configs import MULTILINGUAL_QUERY_EXPANSION
from payserai.configs.app_configs import OAUTH_CLIENT_ID
from payserai.configs.app_configs import OAUTH_CLIENT_SECRET
from payserai.configs.app_configs import SECRET
from payserai.configs.app_configs import WEB_DOMAIN
from payserai.configs.constants import AuthType
from payserai.configs.model_configs import ASYM_PASSAGE_PREFIX
from payserai.configs.model_configs import ASYM_QUERY_PREFIX
from payserai.configs.model_configs import DOCUMENT_ENCODER_MODEL
from payserai.configs.model_configs import ENABLE_RERANKING_REAL_TIME_FLOW
from payserai.configs.model_configs import FAST_GEN_AI_MODEL_VERSION
from payserai.configs.model_configs import GEN_AI_API_ENDPOINT
from payserai.configs.model_configs import GEN_AI_MODEL_PROVIDER
from payserai.configs.model_configs import GEN_AI_MODEL_VERSION
from payserai.db.connector import create_initial_default_connector
from payserai.db.connector_credential_pair import associate_default_cc_pair
from payserai.db.credentials import create_initial_public_credential
from payserai.db.engine import get_sqlalchemy_engine
from payserai.direct_qa.factory import get_default_qa_model
from payserai.document_index.factory import get_default_document_index
from payserai.llm.factory import get_default_llm
from payserai.search.search_nlp_models import warm_up_models
from payserai.server.cc_pair.api import router as cc_pair_router
from payserai.server.chat_backend import router as chat_router
from payserai.server.connector import router as connector_router
from payserai.server.credential import router as credential_router
# from payserai.server.payserai_api import get_payserai_api_key
# from payserai.server.payserai_api import router as payserai_api_router
from payserai.server.document_set import router as document_set_router
from payserai.server.manage import router as admin_router
from payserai.server.search_backend import router as backend_router
from payserai.server.slack_bot_management import router as slack_bot_management_router
from payserai.server.state import router as state_router
from payserai.server.users import router as user_router
from payserai.utils.logger import setup_logger
from payserai.utils.telemetry import optional_telemetry
from payserai.utils.telemetry import RecordType
from payserai.utils.variable_functionality import fetch_versioned_implementation


logger = setup_logger()


def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    exc_str = f"{exc}".replace("\n", " ").replace("   ", " ")
    logger.exception(f"{request}: {exc_str}")
    content = {"status_code": 422, "message": exc_str, "data": None}
    return JSONResponse(content=content, status_code=422)


def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    try:
        raise (exc)
    except Exception:
        # log stacktrace
        logger.exception("ValueError")
    return JSONResponse(
        status_code=400,
        content={"message": str(exc)},
    )


def get_application() -> FastAPI:
    application = FastAPI(title="payserai Backend", version=__version__)
    application.include_router(backend_router)
    application.include_router(chat_router)
    application.include_router(admin_router)
    application.include_router(user_router)
    application.include_router(connector_router)
    application.include_router(credential_router)
    application.include_router(cc_pair_router)
    application.include_router(document_set_router)
    application.include_router(slack_bot_management_router)
    application.include_router(state_router)
    # application.include_router(payserai_api_router)

    if AUTH_TYPE == AuthType.DISABLED:
        # Server logs this during auth setup verification step
        pass

    elif AUTH_TYPE == AuthType.BASIC:
        application.include_router(
            fastapi_users.get_auth_router(auth_backend),
            prefix="/auth",
            tags=["auth"],
        )
        application.include_router(
            fastapi_users.get_register_router(UserRead, UserCreate),
            prefix="/auth",
            tags=["auth"],
        )
        application.include_router(
            fastapi_users.get_reset_password_router(),
            prefix="/auth",
            tags=["auth"],
        )
        application.include_router(
            fastapi_users.get_verify_router(UserRead),
            prefix="/auth",
            tags=["auth"],
        )
        application.include_router(
            fastapi_users.get_users_router(UserRead, UserUpdate),
            prefix="/users",
            tags=["users"],
        )

    elif AUTH_TYPE == AuthType.GOOGLE_OAUTH:
        oauth_client = GoogleOAuth2(OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET)
        application.include_router(
            fastapi_users.get_oauth_router(
                oauth_client,
                auth_backend,
                SECRET,
                associate_by_email=True,
                is_verified_by_default=True,
                # points the user back to the login page
                redirect_url=f"{WEB_DOMAIN}/auth/oauth/callback",
            ),
            prefix="/auth/oauth",
            tags=["auth"],
        )
        # need basic auth router for `logout` endpoint
        application.include_router(
            fastapi_users.get_logout_router(auth_backend),
            prefix="/auth",
            tags=["auth"],
        )

    application.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )

    application.add_exception_handler(ValueError, value_error_handler)

    @application.on_event("startup")
    def startup_event() -> None:
        verify_auth = fetch_versioned_implementation(
            "payserai.auth.users", "verify_auth_setting"
        )
        # Will throw exception if an issue is found
        verify_auth()


        get_default_llm().log_model_configs()
        get_default_qa_model().warm_up_model()

        logger.info("Verifying query preprocessing (NLTK) data is downloaded")
        nltk.download("stopwords", quiet=True)
        nltk.download("wordnet", quiet=True)
        nltk.download("punkt", quiet=True)

        logger.info("Verifying default connector/credential exist.")
        with Session(get_sqlalchemy_engine(), expire_on_commit=False) as db_session:
            create_initial_public_credential(db_session)
            create_initial_default_connector(db_session)
            associate_default_cc_pair(db_session)

        logger.info("Loading default Chat Personas")
        load_personas_from_yaml()

        logger.info("Verifying Document Index(s) is/are available.")
        get_default_document_index().ensure_indices_exist()

        optional_telemetry(
            record_type=RecordType.VERSION, data={"version": __version__}
        )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Change this to the list of allowed origins if needed
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    return application


app = get_application()


if __name__ == "__main__":
    logger.info(
        f"Starting payserai Backend version {__version__} on http://{APP_HOST}:{str(APP_PORT)}/"
    )
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
