from fastapi import APIRouter, Query

from app.core.fixtures import load_fixture

router = APIRouter(tags=["widget-catalog"])


@router.get("/widget-catalog")
def get_widget_catalog(
    integration_type: str = Query(alias="integrationType", default="fortigate"),
) -> dict:
    if integration_type == "fortigate":
        return load_fixture("widget_catalog_fortigate")
    if integration_type in {"soc", "siem_kowalski", "xdr_rico", "soar_skipper", "fortiweb"}:
        catalog = load_fixture("widget_catalog_soc")
        if integration_type == "soc":
            return catalog
        return {
            "items": [item for item in catalog["items"] if item.get("source") == integration_type]
        }
    return {"items": []}
