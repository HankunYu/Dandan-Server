from typing import Optional

from fastapi import Request


def get_client_ip(request: Request) -> Optional[str]:
    """Client IP as set by the nginx reverse proxy, falling back to the peer address.

    Uvicorn only listens on localhost, so X-Real-IP always comes from nginx
    and cannot be spoofed by external clients.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    return request.client.host if request.client else None
