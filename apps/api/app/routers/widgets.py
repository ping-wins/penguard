from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import get_current_api_user
from app.auth.token_cipher import TokenCipher
from app.core.config import get_settings
from app.integrations.fortigate.store import SqlAlchemyFortiGateIntegrationStore
from app.integrations.fortigate.widgets import (
    FortiGateWidgetDataService,
    MockFortiGateWidgetDataService,
)

router = APIRouter(tags=["widgets"])
FortiGateWidgetService = FortiGateWidgetDataService | MockFortiGateWidgetDataService


@lru_cache
def get_fortigate_widget_service() -> FortiGateWidgetService:
    settings = get_settings()
    if settings.mock_mode:
        return MockFortiGateWidgetDataService()
    return FortiGateWidgetDataService(
        store=SqlAlchemyFortiGateIntegrationStore(
            database_url=settings.database_url,
            secret_cipher=TokenCipher.from_secret(
                settings.token_encryption_key or settings.secret_key
            ),
        )
    )


@router.get("/widgets/{widget_id}/data")
def get_widget_data(
    widget_id: str,
    integration_id: Annotated[str, Query(alias="integrationId")],
    service: Annotated[FortiGateWidgetService, Depends(get_fortigate_widget_service)],
    current_user: Annotated[dict, Depends(get_current_api_user)],
) -> dict:
    try:
        return service.get_widget_data(
            widget_id,
            integration_id,
            owner_user_id=str(current_user["id"]),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Widget data not found") from exc
