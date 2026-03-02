from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="GridMind Server",
    description="An Adaptive, Carbon-Aware Distributed Workstation Scheduling System",
    version="1.0.0"
)

@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok", "message": "GridMind Server is running"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
