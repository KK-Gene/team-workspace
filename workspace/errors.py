class WorkspaceError(Exception):
    """Base user-safe application exception."""


class ValidationError(WorkspaceError):
    pass


class DatabaseBusyError(WorkspaceError):
    pass


class MigrationError(WorkspaceError):
    pass

