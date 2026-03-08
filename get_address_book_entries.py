"""
Test test test

BDB Task: List WxCC Address Books (and optionally entries for one book).

=============================================================================
HOW THIS TASK RUNS
=============================================================================

1. INVOCATION
   A client (e.g. Postman, curl, or a frontend) sends an HTTP POST to:
     https://scripts.cisco.com/api/v2/jobs/<your_task_name>
   with:
     - Header: Content-Type: application/json
     - Cookie: bdb_cookie=<value>  (from browser after logging into BDB)
     - Body: { "dev": true, "input": { "bearer_token": "...", "org_id": "..." } }

2. BDB PLATFORM
   - Validates that the task has declared inputs matching the keys in "input"
     (bearer_token, org_id, and optionally address_book_id). If not → 400.
   - Writes the request body to a file (e.g. /var/bdb/jobIO/inputs.json).
   - Calls the task function, passing env and the input values as keyword args:
     task(env, bearer_token="...", org_id="...", address_book_id="")

3. THIS SCRIPT
   - task(env, bearer_token, org_id, address_book_id="") receives the args.
   - If any required value is empty, it falls back to reading from the inputs
     file or from env (secrets/config) so the same code works with BDB UI or
     env-configured credentials.
   - If address_book_id is provided → GET .../v2/address-book/{id}/entry
     (entries for that one book).
   - If address_book_id is omitted → GET .../v3/address-book (all address
     books for the org).
   - Returns the API response as a JSON string (or an error payload).

4. WxCC API ENDPOINTS USED
   - List all address books: GET {base}/organization/{org_id}/v3/address-book
   - List entries in one book: GET {base}/organization/{org_id}/v2/address-book/{address_book_id}/entry

No credentials or IDs are hardcoded; they come from the request body or env.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    import bdblib

logger = logging.getLogger(__name__)

# WxCC API base URL (region-specific). Overridable via input wxcc_api_base or env WXCC_API_BASE.
WXCC_API_BASE = "https://api.wxcc-us1.cisco.com"
REQUEST_TIMEOUT_SEC = 30


def _str_or_none(val: Any) -> str | None:
    """Return a non-empty string, or None if empty/whitespace."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _get_from_env(env: Any, key: str, default: str | None = None) -> str | None:
    """
    Read a value from BDB env (secrets/config or attribute-style).
    Used as fallback when inputs are not passed as function arguments.
    """
    if env is None:
        return default
    if callable(getattr(env, "get", None)):
        v = env.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    secrets = getattr(env, "secrets", None) or getattr(env, "config", None)
    if secrets is not None and callable(getattr(secrets, "get", None)):
        v = secrets.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    attr = getattr(env, key, None) or getattr(env, key.replace(".", "_").upper(), None)
    if attr is not None and str(attr).strip():
        return str(attr).strip()
    return default


def _get_input(env: Any) -> dict[str, Any]:
    """
    Read the request body from BDB's input file (env.input_file → inputs.json).
    BDB writes the POST body there; we parse JSON and unwrap the "input" object
    so that {"input": {"bearer_token": "...", "org_id": "..."}} becomes a dict
    with bearer_token and org_id.
    """
    if env is None:
        return {}
    path = getattr(env, "input_file", None)
    if not isinstance(path, str) or not path.strip():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read().strip()
    except OSError:
        return {}
    if not content.startswith("{"):
        return {}
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    # Top-level has our keys (flat body)
    if any(k in data for k in ("bearer_token", "bearerToken", "org_id", "orgId")):
        return data
    # Unwrap {"input": {"bearer_token": "...", "org_id": "..."}}
    for key in ("input", "params", "data"):
        nested = data.get(key)
        if isinstance(nested, dict) and any(
            k in nested for k in ("bearer_token", "bearerToken", "org_id", "orgId")
        ):
            return nested
    return data


def fetch_address_books(
    *,
    org_id: str,
    bearer_token: str,
    api_base: str = WXCC_API_BASE,
    timeout: int = REQUEST_TIMEOUT_SEC,
) -> dict[str, Any]:
    """
    WxCC API: list all address books for an organization.
    GET {api_base}/organization/{org_id}/v3/address-book
    """
    if not org_id or not bearer_token:
        raise ValueError("org_id and bearer_token are required")
    url = f"{api_base.rstrip('/')}/organization/{org_id}/v3/address-book"
    headers = {"Authorization": f"Bearer {bearer_token}", "Accept": "application/json"}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_address_book_entries(
    *,
    org_id: str,
    address_book_id: str,
    bearer_token: str,
    api_base: str = WXCC_API_BASE,
    timeout: int = REQUEST_TIMEOUT_SEC,
) -> dict[str, Any]:
    """
    WxCC API: list entries for a single address book.
    GET {api_base}/organization/{org_id}/v2/address-book/{address_book_id}/entry
    """
    if not org_id or not address_book_id or not bearer_token:
        raise ValueError("org_id, address_book_id and bearer_token are required")
    url = f"{api_base.rstrip('/')}/organization/{org_id}/v2/address-book/{address_book_id}/entry"
    headers = {"Authorization": f"Bearer {bearer_token}", "Accept": "application/json"}
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.json()


def task(
    env: "bdblib.Env",
    bearer_token: str = "",
    org_id: str = "",
    address_book_id: str = "",
) -> str:
    """
    BDB task entrypoint. Must accept bearer_token and org_id as parameters so that
    BDB validates the request body and passes them in. Optional address_book_id
    selects "entries for one book" vs "list all books".

    Flow:
      1. Normalize args (empty string → None).
      2. If anything missing, read from inputs file or env.
      3. Resolve api_base (optional override).
      4. If address_book_id present → fetch entries for that book; else → fetch all books.
      5. Return JSON string of the response, or an error payload.
    """
    try:
        # --- 1. Normalize function arguments (BDB may pass empty string) ---
        token = _str_or_none(bearer_token)
        org = _str_or_none(org_id)
        book_id = _str_or_none(address_book_id)

        # --- 2. Fallback: inputs file or env (when not passed as args) ---
        if not token or not org:
            input_data = _get_input(env)
            token = token or _str_or_none(input_data.get("bearer_token") or input_data.get("bearerToken"))
            org = org or _str_or_none(input_data.get("org_id") or input_data.get("orgId"))
            book_id = book_id or _str_or_none(input_data.get("address_book_id") or input_data.get("addressBookId"))
        if not token:
            token = _get_from_env(env, "WXCC_BEARER_TOKEN") or _get_from_env(env, "BEARER_TOKEN")
        if not org:
            org = _get_from_env(env, "WXCC_ORG_ID") or _get_from_env(env, "ORG_ID")
        if not book_id:
            book_id = _get_from_env(env, "WXCC_ADDRESS_BOOK_ID") or _get_from_env(env, "ADDRESS_BOOK_ID")

        # --- 3. Optional api_base override (from input or env) ---
        input_data = _get_input(env) if not token or not org else {}
        api_base = (
            _str_or_none(input_data.get("wxcc_api_base") or input_data.get("wxccApiBase"))
            or _get_from_env(env, "WXCC_API_BASE")
            or WXCC_API_BASE
        )

        # --- 4. Validate required credentials ---
        if not token:
            return json.dumps({
                "error": "Missing credentials",
                "message": "Pass bearer_token in the request body (inside 'input') or set BEARER_TOKEN in task env/secrets.",
            })
        if not org:
            return json.dumps({
                "error": "Missing configuration",
                "message": "Pass org_id in the request body (inside 'input') or set ORG_ID in task env/secrets.",
            })

        # --- 5. Call WxCC and return result ---
        if book_id:
            data = fetch_address_book_entries(
                org_id=org,
                address_book_id=book_id,
                bearer_token=token,
                api_base=api_base,
            )
        else:
            data = fetch_address_books(
                org_id=org,
                bearer_token=token,
                api_base=api_base,
            )
        return json.dumps(data, indent=2)

    except ValueError as e:
        return json.dumps({"error": "Configuration error", "message": str(e)})
    except requests.RequestException as e:
        return json.dumps({
            "error": "API request failed",
            "message": str(e),
            "detail": getattr(e, "response", None) and getattr(e.response, "text", None),
        })
