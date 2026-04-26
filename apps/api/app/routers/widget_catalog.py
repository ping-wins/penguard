from fastapi import APIRouter, Query

from app.core.fixtures import load_fixture

router = APIRouter(tags=["widget-catalog"])


@router.get("/widget-catalog")
def get_widget_catalog(
    integration_type: str = Query(alias="integrationType", default="fortigate"),
) -> dict:
    catalog = load_fixture("widget_catalog_fortigate")
    if integration_type != "fortigate":
        return {"items": []}
    return catalog
