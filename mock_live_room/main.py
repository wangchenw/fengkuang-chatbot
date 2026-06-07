from fastapi import FastAPI

from mock_live_room.api.pages import router as pages_router


app = FastAPI(title="Mock Live Room")
app.include_router(pages_router)
