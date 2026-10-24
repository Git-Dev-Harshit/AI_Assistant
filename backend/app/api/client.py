import re

from fastapi import Request

CLIENT_ID_HEADER = "X-Client-Id"
_VALID_CLIENT_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def client_identity(request: Request) -> str:
    """Identify the caller for rate limiting and question history.

    There is no authentication in this exercise, so we use an opaque client id sent by
    the UI (one per browser), falling back to the remote IP. With real auth this would
    be the authenticated user/tenant id, which cannot be spoofed.
    """
    client_id = request.headers.get(CLIENT_ID_HEADER, "")
    if _VALID_CLIENT_ID.match(client_id):
        return f"cid:{client_id}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"
