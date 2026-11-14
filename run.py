"""
Convenience launcher to run the FastAPI app directly via python.exe.
This bypasses Windows Device Guard / AppLocker restrictions on venv/Scripts/*.exe.
"""
import uvicorn

if __name__ == "__main__":
    print("Starting The Baker's Box FastAPI Backend on http://127.0.0.1:8000 ...")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
