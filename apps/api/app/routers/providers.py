from copy import deepcopy

from fastapi import APIRouter, HTTPException

from app.core.fixtures import load_fixture

router = APIRouter(tags=["providers"])

PROVIDER_DATA_FIELD_FIXTURES = {
    "fortigate": "data-fields",
    "siem_kowalski": "data_fields_siem_kowalski",
    "xdr_rico": "data_fields_xdr_rico",
    "soar_skipper": "data_fields_soar_skipper",
    "fortiweb": "data_fields_fortiweb",
}


@router.get("/providers/fortigate/data-fields")
def get_fortigate_data_fields() -> dict:
    return load_fixture("data-fields")


@router.get("/providers/{provider}/data-fields")
def get_provider_data_fields(provider: str) -> dict:
    if provider == "soc":
        groups = []
        for source_provider in ("siem_kowalski", "xdr_rico", "soar_skipper"):
            payload = _provider_fields_payload(source_provider)
            for group in payload["groups"]:
                next_group = deepcopy(group)
                next_group["id"] = f"{source_provider}.{next_group['id']}"
                groups.append(next_group)
        return {"provider": "soc", "groups": groups}

    if provider not in PROVIDER_DATA_FIELD_FIXTURES:
        raise HTTPException(status_code=404, detail="Provider data fields not found")

    return _provider_fields_payload(provider)


def _provider_fields_payload(provider: str) -> dict:
    fixture = PROVIDER_DATA_FIELD_FIXTURES[provider]
    return load_fixture(fixture)
