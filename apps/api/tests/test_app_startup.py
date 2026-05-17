from fastapi import FastAPI


def test_api_application_imports_in_mock_mode() -> None:
    from app.main import app

    assert isinstance(app, FastAPI)
