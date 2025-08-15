import httpx

class DaemonClient:
    """
    Tiny wrapper for the PaperPi daemon. Phase 1: defined; Phase 2: used.
    """
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")

    async def get_config(self, name: str):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{self.base}/config/{name}")
            r.raise_for_status()
            return r.json()["data"]

    async def get_schema_app(self):
        async with httpx.AsyncClient() as c:
            r = await c.get(f"{self.base}/schema/app")
            r.raise_for_status()
            return r.json()["data"]["schema"]

    async def check(self, name: str, config: dict):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{self.base}/config/check/{name}", json={"config": config})
            r.raise_for_status()
            return r.json()["data"]

    async def write(self, name: str, config: dict):
        async with httpx.AsyncClient() as c:
            r = await c.post(f"{self.base}/config/write/{name}", json={"config": config})
            r.raise_for_status()
            return r.json()["data"]