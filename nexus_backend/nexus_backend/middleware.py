import logging

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Log avant le traitement
        if "/client/orders/checkout/" in request.path:
            logger.info(f"=== MIDDLEWARE: {request.method} {request.path} ===")
            logger.info(f"User: {request.user}")
            logger.info(f"Content-Type: {request.content_type}")

            if request.method == "POST":
                logger.info(f"POST keys: {list(request.POST.keys())}")

        response = self.get_response(request)

        # Log après le traitement si erreur
        if "/client/orders/checkout/" in request.path and response.status_code >= 400:
            logger.error(f"=== MIDDLEWARE ERROR: {response.status_code} ===")
            logger.error(f"Response content: {response.content[:500]}")

        return response
