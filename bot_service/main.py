from fastapi import FastAPI

from bot_service.api.live import router as live_router


app = FastAPI(title="Livestream Bot Service")
app.include_router(live_router)
