"""
Compatibility layer for user model imports.

The actual custom User model for this project lives in ``main.models`` and is
configured via ``AUTH_USER_MODEL = "main.User"`` in settings.

Historically, some tests and modules import ``User`` from ``user.models``.
To keep those imports working without introducing a second user model,
we re-export the main.User model here.
"""

from main.models import User  # noqa: F401
