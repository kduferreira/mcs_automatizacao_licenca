class DomainError(Exception):
    pass


class ExecutionConflict(DomainError):
    pass


class ExternalServiceUnavailable(DomainError):
    pass
