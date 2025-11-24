from django.test import RequestFactory, TestCase

from nexus_backend.middleware import RequestLoggingMiddleware


class RequestLoggingMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        def get_response(request):
            from django.http import JsonResponse

            return JsonResponse({"ok": True}, status=200)

        self.middleware = RequestLoggingMiddleware(get_response)

    def test_middleware_passes_through_non_checkout_paths(self):
        request = self.factory.get("/some/other/path/")
        resp = self.middleware(request)
        self.assertEqual(resp.status_code, 200)

    def test_middleware_logs_for_checkout_post(self):
        # Smoke test: ensure middleware executes without error on checkout POST
        request = self.factory.post("/client/orders/checkout/", data={"foo": "bar"})
        resp = self.middleware(request)
        self.assertEqual(resp.status_code, 200)
