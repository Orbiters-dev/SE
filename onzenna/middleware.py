"""CORS middleware for onzenna API.

Handles CORS preflight (OPTIONS) and adds CORS headers to all responses.
This replaces the per-view _cors_headers() approach which doesn't work
reliably through nginx reverse proxy.
"""
from django.http import HttpResponse

ALLOWED_ORIGINS = {
    'https://orbiters-dev.github.io',
}


class CorsMiddleware:
    """Add CORS headers to all onzenna API responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Handle OPTIONS preflight immediately
        if request.method == 'OPTIONS':
            response = HttpResponse(status=204)
            self._add_cors(request, response)
            return response

        response = self.get_response(request)
        self._add_cors(request, response)
        return response

    def _add_cors(self, request, response):
        origin = request.META.get('HTTP_ORIGIN', '')
        if origin in ALLOWED_ORIGINS:
            response['Access-Control-Allow-Origin'] = origin
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
            response['Access-Control-Max-Age'] = '86400'
            response['Vary'] = 'Origin'
