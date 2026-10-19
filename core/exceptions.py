class HRApplicationError(Exception):
    pass


class ConfigurationError(HRApplicationError):
    pass


class PermissionDeniedError(HRApplicationError):
    pass


class ResourceNotFoundError(HRApplicationError):
    pass
