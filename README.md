# BDB Task: WxCC Address Books

Python 3.13 BDB task that calls the Cisco WxCC Organization API to **list address books** or **list entries** for one address book. The script is invoked by the company hosting when a job is triggered from outside.

## How it is invoked from outside

BDB expects the request body to wrap parameters in **`input`**. Use this exact shape:

**List all address books:**

```bash
curl --request POST \
  --url https://scripts.cisco.com/api/v2/jobs/your_task_name \
  --header 'Content-Type: application/json' \
  --cookie bdb_cookie=your_bdb_cookie_value \
  --data '{
  "dev": true,
  "input": {
    "bearer_token": "YOUR_WXCC_BEARER_TOKEN",
    "org_id": "7c3733e0-ea21-4e66-9e73-b14c6ac91c27"
  }
}'
```

**List entries in one address book** (add `address_book_id` inside `input`):

```json
{
  "dev": true,
  "input": {
    "bearer_token": "YOUR_WXCC_BEARER_TOKEN",
    "org_id": "7c3733e0-ea21-4e66-9e73-b14c6ac91c27",
    "address_book_id": "YOUR_ADDRESS_BOOK_UUID"
  }
}
```

Important: the task function **must** accept `bearer_token` and `org_id` as parameters (see BDB Options → Inputs and the task signature below). That is what fixes the 400 "Missing or invalid argument(s): bearer_token, org_id".

## WxCC APIs used

| What you want | Request | URL |
|---------------|---------|-----|
| **List all address books** | `bearer_token` + `org_id` only (no address_book_id) | `GET .../organization/{orgId}/v3/address-book` |
| **List entries in one book** | `bearer_token` + `org_id` + `address_book_id` | `GET .../organization/{orgId}/v2/address-book/{addressBookId}/entry` |

Headers: `Authorization: Bearer <token>`, `Accept: application/json`.

## Configuration

| Source | Keys |
|--------|------|
| **Request body** | `bearer_token` / `bearerToken`, `org_id` / `orgId`; optional: `address_book_id` / `addressBookId` |
| **Secrets / env** | `BEARER_TOKEN` or `WXCC_BEARER_TOKEN`, `ORG_ID` or `WXCC_ORG_ID`; optional: `ADDRESS_BOOK_ID` or `WXCC_ADDRESS_BOOK_ID` |
| **Optional** | `wxcc_api_base` / `wxccApiBase` (default: `https://api.wxcc-us1.cisco.com`) |

## Setup

- Python 3.13
- Install dependencies: `pip install -r requirements.txt`
- Configure the task on the hosting platform with the required secrets/env and register the task name so that `POST …/jobs/<your_task_name>` runs this script.

### BDB: Declare input parameters and task signature

So that the API accepts the request and passes parameters into the task:

1. In BDB: open your task → **Dev mode** → **Options** → **Inputs**.
2. Add inputs with **exact** names and types:
   - **name:** `bearer_token`, **type:** text  
   - **name:** `org_id`, **type:** text  
   - **name:** `address_book_id`, **type:** text (optional)
3. **Save.**

The task function **must accept these as parameters** (BDB passes them from the `input` object):

```python
def task(env, bearer_token, org_id, address_book_id="") -> str:
```

If the signature is only `def task(env) -> str`, BDB returns **400 "Missing or invalid argument(s): bearer_token, org_id"** because it expects the task to declare the inputs. This repo’s task is already defined as `def task(env, bearer_token="", org_id="", address_book_id="") -> str`.

### If you get 400 "Missing or invalid argument(s): bearer_token, org_id"

1. **Request body must use the `input` wrapper** (per BDB full stack guide):
   ```json
   {
     "dev": true,
     "input": {
       "bearer_token": "YOUR_WXCC_BEARER_TOKEN",
       "org_id": "7c3733e0-ea21-4e66-9e73-b14c6ac91c27"
     }
   }
   ```
2. **BDB Options → Inputs:** add inputs with **name** exactly `bearer_token` and `org_id` (type text). Save.
3. **Task signature:** the Python task must accept them as parameters, e.g. `def task(env, bearer_token, org_id, address_book_id="") -> str`. This repo’s script already uses that signature.
4. **Postman:** Body → raw → JSON; Headers: `Content-Type: application/json`; Cookies: `bdb_cookie`.

## Task entrypoint

The script exposes the BDB entrypoint with inputs as parameters:

```python
def task(env, bearer_token="", org_id="", address_book_id="") -> str:
```

Return value is a JSON string: either the WxCC API response (address books or entries) or an object with `"error"` and `"message"` (and optional `"detail"`) on failure. How the task runs end-to-end is documented in the module docstring at the top of `get_address_book_entries.py`.
