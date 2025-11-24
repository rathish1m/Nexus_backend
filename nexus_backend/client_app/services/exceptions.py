class BusinessError(Exception):
    """Erreur métier générique"""

    pass


class InventoryUnavailable(BusinessError):
    pass


class PlanOrKitNotFound(BusinessError):
    pass


class InvalidLocation(BusinessError):
    pass


class OrderError(BusinessError):
    """Order-related errors"""

    pass
