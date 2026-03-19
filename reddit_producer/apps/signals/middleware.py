"""
apps/signals/middleware.py
Tracks API key usage on every /api/v1/ request.
Logs token, endpoint, status, response time, IP to api_key_usage table.
Zero latency impact — writes happen in a background thread after response.
"""
import time
import threading
from django.db import connection as db_conn


def _log_usage(token, endpoint, method, status_code, response_ms, ip, ua):
    try:
        from django.db import connections
        conn = connections['default']
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO api_key_usage
                    (token, endpoint, method, status_code, response_ms, ip_address, user_agent, requested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, [token, endpoint, method, status_code, response_ms, ip, ua[:200] if ua else None])
        conn.close()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"usage log failed: {e}")


class ApiUsageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        t0 = time.monotonic()
        response = self.get_response(request)

        if not request.path.startswith("/api/v1/"):
            return response

        auth = request.META.get("HTTP_AUTHORIZATION", "")
        token = None
        if auth.startswith("Token "):
            token = auth[6:].strip()
        elif auth and len(auth) == 64 and all(c in "0123456789abcdef" for c in auth):
            token = auth.strip()

        if not token:
            return response

        ms   = int((time.monotonic() - t0) * 1000)
        ip   = request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", ""))
        ua   = request.META.get("HTTP_USER_AGENT", "")

        threading.Thread(
            target=_log_usage,
            args=(token, request.path, request.method, response.status_code, ms, ip, ua),
            daemon=True,
        ).start()

        return response
