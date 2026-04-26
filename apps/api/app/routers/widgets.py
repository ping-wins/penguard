from fastapi import APIRouter, HTTPException, Query

from app.core.fixtures import load_fixture

router = APIRouter(tags=["widgets"])


@router.get("/widgets/{widget_id}/data")
def get_widget_data(
    widget_id: str,
    integration_id: str = Query(alias="integrationId"),
) -> dict:
    data = load_fixture("widget_data_fortigate_system_status")
    if widget_id != data["widgetId"] or integration_id != data["integrationId"]:
        raise HTTPException(status_code=404, detail="Widget data not found")
    return data
