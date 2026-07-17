"""Minimal security middleware for MVP.

- AGENT_DEBUG_ENABLED: controls whether /agent/* routes are available
- AGENT_API_KEY: if set, agent-debug and trace endpoints require X-API-Key header
"""

from fastapi import HTTPException, Request, status

from app.core.config import AGENT_API_KEY, AGENT_DEBUG_ENABLED


async def agent_debug_middleware(request: Request, call_next):
    """Middleware to guard agent debug routes.

    - Production: disable debug routes entirely
    - Optional API key: if AGENT_API_KEY is set, require it for debug endpoints
    """
    path = request.url.path

    # Only apply to agent-related routes
    if not path.startswith("/api/agent/"):
        return await call_next(request)

    # Production mode: block all agent debug routes
    if not AGENT_DEBUG_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent debug panel is not available in production.",
        )

    # API key check (optional — only if key is configured)
    if AGENT_API_KEY:
        api_key = request.headers.get("X-API-Key", "")
        if api_key != AGENT_API_KEY:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key for agent debug endpoints.",
            )

    return await call_next(request)
