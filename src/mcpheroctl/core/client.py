"""HTTP client for the MCPHero API.

Uses httpx with tenacity retry logic for transient failures.
"""

from __future__ import annotations

from typing import Any

import httpx
from httpx._client import Client
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from mcpheroctl.core.config import get_base_url, require_token

# Retry on transient network / 5xx errors
_RETRYABLE_STATUS_CODES = frozenset(range(500, 600))

# Default timeout for API calls (seconds)
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class APIError(Exception):
    """Raised when the API returns an error response."""

    def __init__(self, status_code: int, detail: str, body: Any = None) -> None:
        self.status_code: int = status_code
        self.detail: str = detail
        self.body: Any = body
        super().__init__(f"HTTP {status_code}: {detail}")


def _build_client(token: str, base_url: str) -> httpx.Client:
    return httpx.Client(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {token}",
        },
        timeout=_TIMEOUT,
        follow_redirects=True,
    )


def _handle_response(response: httpx.Response) -> Any:
    """Parse the response, raising APIError on non-2xx codes."""
    if response.is_success:
        if response.headers.get("content-type", "").startswith("application/json"):
            return response.json()
        return response.text
    # Try to extract detail from JSON body
    detail: str = response.text
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = body.get("detail", detail)
    except Exception:
        body = None
    raise APIError(response.status_code, detail, body)


class MCPHeroClient:
    """Synchronous HTTP client for the MCPHero backend API."""

    def __init__(
        self, *, token: str | None = None, base_url: str | None = None
    ) -> None:
        self._token: str = token or require_token()
        self._base_url: str = base_url or get_base_url()
        self._client: Client = _build_client(self._token, self._base_url)

    # ------------------------------------------------------------------
    # Low-level request helpers with retry
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, APIError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
        reraise=True,
    )
    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._client.request(method, path, **kwargs)
        return _handle_response(response)

    def get(self, path: str, **kwargs: Any) -> Any:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self._request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> Any:
        return self._request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self._request("DELETE", path, **kwargs)

    # ------------------------------------------------------------------
    # Server endpoints
    # ------------------------------------------------------------------

    def list_servers(self, customer_id: str | None = None) -> Any:
        """List MCP servers. When using org API key, customer_id is optional."""
        if customer_id is not None:
            return self.get(f"/servers/list/{customer_id}")
        return self.get("/servers/list")

    def get_server(self, server_id: str) -> Any:
        return self.get(f"/servers/{server_id}/details")

    def delete_server(self, server_id: str) -> Any:
        return self.delete(f"/servers/{server_id}")

    def update_server(
        self, server_id: str, *, name: str | None = None, description: str | None = None
    ) -> Any:
        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        return self.patch(f"/servers/{server_id}", json=body)

    def get_server_api_key(self, server_id: str) -> Any:
        return self.get(f"/servers/{server_id}/api-key")

    # ------------------------------------------------------------------
    # Wizard endpoints
    # ------------------------------------------------------------------

    def wizard_create_session(self, customer_id: str | None = None) -> Any:
        body: dict[str, Any] = {}
        if customer_id is not None:
            body["customer_id"] = customer_id
        return self.post("/wizard/sessions", json=body)

    def wizard_chat(self, server_id: str, message: str) -> Any:
        return self.post(
            f"/wizard/{server_id}/chat",
            json={"message": message, "stream": False},
        )

    def wizard_start(
        self,
        server_id: str,
        description: str | None = None,
        technical_details: list[str] | None = None,
    ) -> Any:
        body: dict[str, Any] = {"server_id": server_id}
        if description is not None:
            body["description"] = description
        if technical_details:
            body["technical_details"] = technical_details
        return self.post("/wizard/start", json=body)

    def wizard_get_tools(self, server_id: str) -> Any:
        return self.get(f"/wizard/{server_id}/tools")

    def wizard_refine_tools(
        self,
        server_id: str,
        feedback: str,
        tool_ids: list[str] | None = None,
    ) -> Any:
        body: dict[str, Any] = {"feedback": feedback}
        if tool_ids:
            body["tool_ids"] = tool_ids
        return self.post(f"/wizard/{server_id}/tools/refine", json=body)

    def wizard_submit_tools(self, server_id: str, selected_tool_ids: list[str]) -> Any:
        return self.post(
            f"/wizard/{server_id}/tools/submit",
            json={"selected_tool_ids": selected_tool_ids},
        )

    def wizard_suggest_env_vars(self, server_id: str) -> Any:
        return self.post(f"/wizard/{server_id}/env-vars/suggest")

    def wizard_get_env_vars(self, server_id: str) -> Any:
        return self.get(f"/wizard/{server_id}/env-vars")

    def wizard_refine_env_vars(self, server_id: str, feedback: str) -> Any:
        return self.post(
            f"/wizard/{server_id}/env-vars/refine",
            json={"feedback": feedback},
        )

    def wizard_submit_env_vars(self, server_id: str, values: dict[str, str]) -> Any:
        return self.post(
            f"/wizard/{server_id}/env-vars/submit",
            json={"values": values},
        )

    def wizard_set_auth(self, server_id: str) -> Any:
        return self.post(f"/wizard/{server_id}/auth")

    def wizard_generate_code(self, server_id: str) -> Any:
        return self.post(f"/wizard/{server_id}/generate-code")

    def wizard_regenerate_tool_code(self, server_id: str, tool_id: str) -> Any:
        return self.post(f"/wizard/{server_id}/tools/{tool_id}/regenerate-code")

    def wizard_deploy(self, server_id: str) -> Any:
        return self.post(f"/wizard/{server_id}/deploy")

    def wizard_get_state(self, server_id: str) -> Any:
        return self.get(f"/wizard/{server_id}/state")
