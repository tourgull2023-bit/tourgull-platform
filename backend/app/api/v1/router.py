
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/meta", tags=["system"])
def platform_metadata():
    return {
        "platform": "tourgull",
        "api_version": "v1"
    }
