"""
Clerk authentication for the Flask GUI (likarchive-ui only — the scraper Job
has no HTTP surface, so it never needs this).

Cloud Run keeps ingress public (`allUsers` retains `roles/run.invoker`);
this module is the actual auth boundary, enforced at the app layer instead.
Locking down Cloud Run's own IAM on top would mean nobody could even reach
the sign-in page, so unauthenticated requests are rejected here, not upstream.

Active in every environment (local dev included) — unlike cloud_auth.py/
db_sync.py, this isn't gated on K_SERVICE, since a logged-out browser should
see a sign-in screen locally too, not just in Cloud Run.
"""

import os
from functools import wraps

import httpx
from flask import jsonify, request

CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY")

# Origins the GUI is actually served from — the local dev server plus the
# live Cloud Run URL. Clerk rejects tokens whose origin isn't in this list.
AUTHORIZED_PARTIES = [
    p.strip() for p in os.getenv(
        "CLERK_AUTHORIZED_PARTIES",
        "http://localhost:5000,https://likarchive-ui-588295099118.europe-west2.run.app",
    ).split(",") if p.strip()
]

_clerk = None


def _client():
    global _clerk
    if _clerk is None:
        from clerk_backend_api import Clerk
        _clerk = Clerk(bearer_auth=CLERK_SECRET_KEY)
    return _clerk


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from clerk_backend_api.security.types import AuthenticateRequestOptions

        httpx_request = httpx.Request(
            method=request.method,
            url=request.url,
            headers=request.headers.items(),
        )
        request_state = _client().authenticate_request(
            httpx_request,
            AuthenticateRequestOptions(authorized_parties=AUTHORIZED_PARTIES),
        )
        if not request_state.is_signed_in:
            return jsonify({"error": "unauthorized"}), 401
        return view(*args, **kwargs)
    return wrapped
