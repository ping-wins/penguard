from fastapi import APIRouter

from app.core.fixtures import load_fixture

router = APIRouter(tags=["providers"])


@router.get("/providers/fortigate/data-fields")
def get_fortigate_data_fields() -> dict:
    return load_fixture("data-fields")
