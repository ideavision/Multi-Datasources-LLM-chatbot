from fastapi import APIRouter

from payserai import __version__
from payserai.configs.app_configs import AUTH_TYPE
from payserai.server.models import AuthTypeResponse
from payserai.server.models import StatusResponse
from payserai.server.models import VersionResponse

router = APIRouter()


@router.get("/health")
def healthcheck() -> StatusResponse:
    return StatusResponse(success=True, message="ok")


@router.get("/auth/type")
def get_auth_type() -> AuthTypeResponse:
    return AuthTypeResponse(auth_type=AUTH_TYPE)


@router.get("/version")
def get_version() -> VersionResponse:
    return VersionResponse(backend_version=__version__)
