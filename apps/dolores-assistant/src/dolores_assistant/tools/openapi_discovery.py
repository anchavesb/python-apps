"""Auto-discover tools from OpenAPI specs served by integration services.

At startup, fetches OpenAPI specs from configured URLs and generates
Tool instances that make HTTP calls to those services. The LLM sees
these as regular function-calling tools.

User auth is handled via JWT passthrough: the caller sets
``current_user_token`` before executing tools, and OpenAPITool forwards
it as a Bearer token to the downstream service.
"""

from __future__ import annotations

import json
import re
from contextvars import ContextVar

import httpx

from dolores_common.logging import get_logger

from .base import Tool

log = get_logger(__name__)

# Set by the caller (routes.py) before running the tool loop.
# OpenAPITool reads this to forward the user's JWT to downstream services.
current_user_token: ContextVar[str | None] = ContextVar("current_user_token", default=None)


class OpenAPITool(Tool):
    """A tool dynamically generated from an OpenAPI operation."""

    def __init__(
        self,
        *,
        op_name: str,
        op_description: str,
        op_parameters: dict,
        method: str,
        path_template: str,
        base_url: str,
        has_body: bool,
        auth_header: dict[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._name = op_name
        self._description = op_description
        self._parameters = op_parameters
        self._method = method
        self._path_template = path_template
        self._base_url = base_url.rstrip("/")
        self._has_body = has_body
        self._auth_header = auth_header or {}
        self._http_client = http_client

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, **kwargs) -> str:
        # Substitute path parameters
        path = self._path_template
        for key in re.findall(r"\{(\w+)\}", self._path_template):
            if key in kwargs:
                path = path.replace(f"{{{key}}}", str(kwargs.pop(key)))

        url = f"{self._base_url}{path}"
        client = self._http_client
        if not client:
            raise RuntimeError("HTTP client not set on OpenAPITool")

        # Build headers: static auth + user JWT passthrough
        headers = dict(self._auth_header)
        token = current_user_token.get()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        if self._has_body:
            resp = await client.request(
                self._method,
                url,
                json=kwargs if kwargs else None,
                headers=headers,
            )
        else:
            resp = await client.request(
                self._method,
                url,
                params=kwargs if kwargs else None,
                headers=headers,
            )

        if resp.status_code == 204:
            return "Done."
        try:
            data = resp.json()
        except Exception:
            data = resp.text

        if resp.status_code in (401, 403):
            raise PermissionError(f"Authentication failed ({resp.status_code}): token may be expired")

        if resp.status_code >= 400:
            return f"Error {resp.status_code}: {json.dumps(data) if isinstance(data, (dict, list)) else data}"

        if isinstance(data, list):
            if not data:
                return "No items found."
            return json.dumps(data, indent=2)
        if isinstance(data, dict):
            return json.dumps(data, indent=2)
        return str(data)


def _resolve_ref(spec: dict, ref: str) -> dict:
    """Resolve a $ref like '#/components/schemas/Todo' within the spec."""
    parts = ref.lstrip("#/").split("/")
    node = spec
    for p in parts:
        node = node[p]
    return node


def _schema_to_json_schema(spec: dict, schema: dict) -> dict:
    """Convert an OpenAPI schema (with $ref) to a flat JSON Schema for the LLM."""
    if "$ref" in schema:
        schema = _resolve_ref(spec, schema["$ref"])

    result: dict = {}
    schema_type = schema.get("type")

    if schema_type == "object" or "properties" in schema:
        result["type"] = "object"
        props = {}
        for prop_name, prop_schema in schema.get("properties", {}).items():
            props[prop_name] = _schema_to_json_schema(spec, prop_schema)
        result["properties"] = props
        if "required" in schema:
            result["required"] = schema["required"]
        if schema.get("additionalProperties"):
            result["additionalProperties"] = _schema_to_json_schema(
                spec, schema["additionalProperties"]
            ) if isinstance(schema["additionalProperties"], dict) else schema["additionalProperties"]
    elif schema_type == "array":
        result["type"] = "array"
        if "items" in schema:
            result["items"] = _schema_to_json_schema(spec, schema["items"])
    else:
        if schema_type:
            result["type"] = schema_type
        if "enum" in schema:
            result["enum"] = schema["enum"]
        if "default" in schema:
            result["default"] = schema["default"]

    if "description" in schema:
        result["description"] = schema["description"]

    return result


def _build_tools_from_spec(
    spec: dict,
    base_url: str,
    prefix: str,
    auth_header: dict[str, str] | None,
    http_client: httpx.AsyncClient | None = None,
) -> list[Tool]:
    """Parse an OpenAPI spec and return Tool instances for each operation."""
    tools: list[Tool] = []

    for path, path_item in spec.get("paths", {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not op:
                continue

            op_id = op.get("operationId")
            if not op_id:
                continue

            tool_name = f"{prefix}_{op_id}" if prefix else op_id
            description = op.get("summary", op_id)

            # Build JSON Schema for parameters
            properties: dict = {}
            required: list[str] = []

            # Path parameters
            for param in op.get("parameters", []):
                if param.get("in") == "path":
                    p_schema = param.get("schema", {"type": "string"})
                    properties[param["name"]] = _schema_to_json_schema(spec, p_schema)
                    if param.get("description"):
                        properties[param["name"]]["description"] = param["description"]
                    if param.get("required", True):
                        required.append(param["name"])

            # Request body
            has_body = False
            body = op.get("requestBody")
            if body:
                has_body = True
                content = body.get("content", {})
                json_content = content.get("application/json", {})
                body_schema = json_content.get("schema", {})
                if body_schema:
                    resolved = _schema_to_json_schema(spec, body_schema)
                    if resolved.get("type") == "object" and "properties" in resolved:
                        properties.update(resolved["properties"])
                        required.extend(resolved.get("required", []))

            parameters = {
                "type": "object",
                "properties": properties,
            }
            if required:
                parameters["required"] = required

            tools.append(
                OpenAPITool(
                    op_name=tool_name,
                    op_description=description,
                    op_parameters=parameters,
                    method=method.upper(),
                    path_template=path,
                    base_url=base_url,
                    has_body=has_body,
                    auth_header=auth_header,
                    http_client=http_client,
                )
            )

    return tools


async def discover_tools(
    integrations: list[dict],
    http_client: httpx.AsyncClient,
) -> list[Tool]:
    """Fetch OpenAPI specs from configured integration URLs and build tools.

    Uses the provided http_client for both spec fetching and tool execution
    (connection pooling).

    Each integration dict:
        {
            "name": "todo",              # prefix for tool names
            "url": "http://todo:5000",   # base URL of the service
            "spec_path": "/api/openapi.json",  # path to OpenAPI spec
            "auth": {"Authorization": "Bearer xxx"},  # optional auth headers
        }
    """
    all_tools: list[Tool] = []

    for integration in integrations:
        name = integration["name"]
        base_url = integration["url"].rstrip("/")
        spec_path = integration.get("spec_path", "/api/openapi.json")
        auth = integration.get("auth")

        try:
            resp = await http_client.get(
                f"{base_url}{spec_path}",
                headers=auth or {},
                timeout=10,
            )
            resp.raise_for_status()
            spec = resp.json()

            tools = _build_tools_from_spec(spec, base_url, name, auth, http_client)
            log.info("openapi_discovered", service=name, tools=len(tools),
                     tool_names=[t.name for t in tools])
            all_tools.extend(tools)

        except Exception as e:
            log.error("openapi_discovery_failed", service=name, error=str(e))

    return all_tools
