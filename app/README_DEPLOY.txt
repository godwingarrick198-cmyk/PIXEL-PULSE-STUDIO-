PIXEL PULSE STUDIO APP PACKAGE

This ZIP contains the complete Python package under app/.

Render Start Command:
uvicorn app.main:app --host 0.0.0.0 --port $PORT

Do NOT use: uvicorn app:main:app
The Python entrypoint is app/main.py and the FastAPI object is app.main:app.
