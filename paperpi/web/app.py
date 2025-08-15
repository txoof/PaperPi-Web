from fastapi import FastAPI, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings
import os
from pathlib import Path
from starlette.datastructures import FormData
import json

from paperpi.web.daemon_client import DaemonClient

# ---- Settings ---------------------------------------------------------------

class Settings(BaseSettings):
    daemon_url: str = os.getenv("DAEMON_URL", "http://localhost:2822")

def get_settings() -> Settings:
    return Settings()

def get_daemon(settings: Settings = Depends(get_settings)) -> DaemonClient:
    """
    Factory/dependency: returns a DaemonClient configured with the current daemon URL.
    Usage in a route:
      async def route(..., daemon: DaemonClient = Depends(get_daemon)): ...
    """
    return DaemonClient(settings.daemon_url)    

# ---- App & Templates --------------------------------------------------------

app = FastAPI(title="PaperPi Web")

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ---- Routes (minimal for Phase 1) ------------------------------------------


@app.get("/health")
async def health(settings: Settings = Depends(get_settings)):
    # Simple health info, plus what daemon URL we’re configured to use
    return JSONResponse({"status": "ok", "daemon_url": settings.daemon_url})

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # Temporary landing page; in Phase 2 we’ll redirect to /config/app
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "title": "PaperPi Web", "content": "UI scaffold is running. Phase 2 coming next."},
    )

@app.get("/config/app", response_class=HTMLResponse)
async def get_config_app(request: Request, daemon: DaemonClient=Depends(get_daemon)):
    # fetch current app configuration 
    current = await daemon.get_config("app")    # dict of main
    schema = await daemon.get_schema_app()      # rules keyed by field

    # build items for the template (key, value, description and default value)
    config_items = sorted(
        [
            {
                "key": k,
                "value": current.get(k),
                "description": (schema.get(k, {}) or {}).get("description", "No description available."),
                "default": (schema.get(k, {}) or {}).get("default", None),
            }
            for k in schema.keys()
        ],
        key=lambda x: x["key"],
    )

    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "title": "App Configuration",
            "config_items": config_items,
            "schema": schema,
            "result": None,
            "changed": False,
            "payload_json": "",
        },
    )

@app.post("/config/app/check", response_class=HTMLResponse)
async def post_config_app_check(request: Request, daemon: DaemonClient=Depends(get_daemon)):
    schema = await daemon.get_schema_app()
    form_values = await parse_form(request)
    submitted = coerce_by_schema(form_values, schema)

    # validate using the daemon
    check = await daemon.check("app", submitted)
    problems = check.get("problems") or {}

    # check changes versus current, if changes display write button
    current = await daemon.get_config("app")
    changes = diff_configs(current, submitted)
    changed = bool(changes) and len(problems) == 0

    # items for the template with submitted values
    config_items = sorted(
        [
            {
                "key": k,
                "value": submitted.get(k),
                "description": (schema.get(k, {}) or {}).get("description", "No description available."),
                "default": (schema.get(k, {}) or {}).get("default", None),
            }
            for k in schema.keys()
        ],
        key=lambda x: x["key"],
    )

    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "title": "App Configuration",
            "config_items": config_items,
            "schema": schema,
            "result": check,
            "changed": changed,
            "payload_json": json.dumps(submitted),
        },
    )


@app.post("/config/app/write", response_class=HTMLResponse)
async def post_config_app_write(
    request: Request,
    daemon: DaemonClient = Depends(get_daemon),
):
    form: FormData = await request.form()
    payload_json = form.get("payload_json")
    if not payload_json:
        raise HTTPException(status_code=400, detail="Missing payload_json")

    try:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise ValueError("payload_json must be an object")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload_json: {e}")

    write_resp = await daemon.write("app", payload)  # -> {written, diff, message}

    # fetch schema for rendering again with the same values
    schema = await daemon.get_schema_app()
    config_items = sorted(
        [
            {
                "key": k,
                "value": payload.get(k),
                "description": (schema.get(k, {}) or {}).get("description", "No description available."),
                "default": (schema.get(k, {}) or {}).get("default", None),
            }
            for k in schema.keys()
        ],
        key=lambda x: x["key"],
    )

    # shape result similar to the check path so template can use message/probs
    result = {"problems": {}, "message": write_resp.get("message", "Configuration written.")}

    return templates.TemplateResponse(
        "config.html",
        {
            "request": request,
            "title": "App Configuration",
            "config_items": config_items,
            "schema": schema,
            "result": result,
            "changed": False,
            "payload_json": json.dumps(payload),
        },
    )


# --- form & schema helpers ---------------------------------------------------

async def parse_form(request: Request) -> dict:
    """
    Convert submitted form fields to a plain dict:
    - checkboxes: treat 'on'/'true' as True, else False if key present;
      IMPORTANT: for unchecked checkboxes, include a hidden input value="false" in the template.
    - everything else: leave as strings (we'll coerce by schema later).
    """
    form: FormData = await request.form()
    data = {}
    for k, v in form.multi_items():
        if k in data:
            # if multiple values, keep the last one (simple forms) or make a list if needed
            pass
        # normalize booleans coming from inputs
        if isinstance(v, str) and v.lower() in ("true", "false", "on", "off"):
            data[k] = v.lower() in ("true", "on")
        else:
            data[k] = v
    return data

def coerce_by_schema(values: dict, schema: dict) -> dict:
    """
    Coerce flat values according to schema types/allowed.
    - str: keep as string
    - int: try int()
    - float: accept int or float; ints coerced to float
    - bool: already normalized by parse_form; also accept 'true'/'false' strings
    - allowed: if present and value not in allowed, leave as-is (daemon will report)
    """
    out = {}
    for key, val in values.items():
        rule = schema.get(key, {}) if isinstance(schema, dict) else {}
        typ = (rule.get("type") or "").lower()
        allowed = rule.get("allowed")

        # allowed list normalization: allow bools to be "true"/"false" strings in select
        if allowed is not None and val is not None:
            # do not auto-fix here; validation will flag problems
            pass

        if val is None:
            out[key] = None
            continue

        if typ in ("int", "integer"):
            try:
                out[key] = int(val)
            except Exception:
                out[key] = val  # let daemon flag
        elif typ in ("float",):
            try:
                if isinstance(val, bool):
                    out[key] = 1.0 if val else 0.0
                else:
                    f = float(val)
                    out[key] = f
            except Exception:
                out[key] = val
        elif typ in ("bool", "boolean"):
            if isinstance(val, bool):
                out[key] = val
            elif isinstance(val, str):
                out[key] = val.lower() in ("true", "on", "1", "yes")
            else:
                out[key] = bool(val)
        else:
            # default to string
            out[key] = str(val)
    return out



def diff_configs(old: dict, new: dict) -> dict:
    """Shallow diff: keys where values differ."""
    changes = {}
    if not isinstance(old, dict) or not isinstance(new, dict):
        return changes
    for k, v in new.items():
        if old.get(k) != v:
            changes[k] = {"from": old.get(k), "to": v}
    return changes