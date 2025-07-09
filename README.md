# FastAPI Backend

This backend provides a root endpoint and WebSocket based chat.

## Installation

```bash
pip install -r requirements.txt
```

Create a `.env` file by copying `.env.example` and replacing the OpenAI key:

```bash
cp .env.example .env
```
Edit `.env` and set `OPENAI_API_KEY` with your API key.

## Running the server

```bash
uvicorn main:app --reload
```

## WebSocket Chat

Connect to `/chat` with a WebSocket client. Text you send will be forwarded to the OpenAI API and the response will be returned.
Example using `websocat`:

```bash
websocat ws://localhost:8000/chat
```

