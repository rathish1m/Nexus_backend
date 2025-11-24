from __future__ import annotations

from django.dispatch import Signal

# Signal emitted when a feedback is submitted or updated by client.
feedback_submitted = Signal()
feedback_locked = Signal()
staff_replied = Signal()
