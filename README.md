# FastAPI Backend

This backend provides a root endpoint and a simple WebSocket chat.

## Installation

```bash
pip install -r requirements.txt
```

## Running the server

```bash
uvicorn main:app --reload
```

## WebSocket Chat

Connect to `/ws/chat` with a WebSocket client. Messages are broadcast to all connected clients. 
Example using `websocat`:

```bash
websocat ws://localhost:8000/ws/chat
```

Open several terminals with `websocat` to see messages from others.
