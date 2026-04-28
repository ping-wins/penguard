class AuthProviderError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        audit_outcome: str = "failure",
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.audit_outcome = audit_outcome
