from __future__ import annotations

import base64
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from openai import OpenAI
from dotenv import load_dotenv

"""
Simple local app to test GPT‑4o on basket images.

Run:
    export OPENAI_API_KEY="sk-..."
    uvicorn basket_vlm_app:app --reload

Then open:
    http://127.0.0.1:8000
"""

# Load environment variables from .env in the project root so OPENAI_API_KEY is available.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

client = OpenAI()

app = FastAPI(title="Basket VLM Test")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """Serve a tiny chat-like UI for uploading basket images."""
    # Kept inline for simplicity – no templating needed.
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Basket VLM Test (GPT‑4o)</title>
  <style>
    body {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      background: #0f172a;
      color: #e5e7eb;
      display: flex;
      flex-direction: column;
      height: 100vh;
    }
    header {
      padding: 12px 20px;
      background: #020617;
      border-bottom: 1px solid #1f2937;
      display: flex;
      align-items: baseline;
      gap: 12px;
    }
    header h1 {
      font-size: 16px;
      margin: 0;
      font-weight: 600;
    }
    header span {
      font-size: 12px;
      color: #9ca3af;
    }
    main {
      flex: 1;
      display: flex;
      flex-direction: column;
      max-width: 960px;
      width: 100%;
      margin: 0 auto;
      padding: 16px;
      box-sizing: border-box;
      gap: 12px;
    }
    .instructions {
      font-size: 13px;
      color: #9ca3af;
      background: #020617;
      border-radius: 8px;
      padding: 10px 12px;
      border: 1px solid #1f2937;
    }
    .chat-box {
      flex: 1;
      overflow-y: auto;
      border-radius: 8px;
      background: #020617;
      border: 1px solid #1f2937;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      font-size: 14px;
    }
    .msg {
      max-width: 80%;
      padding: 8px 10px;
      border-radius: 8px;
      line-height: 1.4;
      white-space: pre-wrap;
    }
    .msg.user {
      align-self: flex-end;
      background: #1d4ed8;
    }
    .msg.assistant {
      align-self: flex-start;
      background: #111827;
      border: 1px solid #1f2937;
    }
    .msg.system {
      align-self: center;
      background: transparent;
      color: #9ca3af;
      font-size: 12px;
      padding: 0;
    }
    .images-preview {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 4px;
    }
    .images-preview img {
      width: 72px;
      height: 72px;
      object-fit: cover;
      border-radius: 6px;
      border: 1px solid #1f2937;
    }
    form {
      margin-top: 4px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 12px;
      border-radius: 8px;
      background: #020617;
      border: 1px solid #1f2937;
    }
    textarea {
      width: 100%;
      min-height: 60px;
      resize: vertical;
      border-radius: 6px;
      border: 1px solid #1f2937;
      background: #020617;
      color: #e5e7eb;
      padding: 8px;
      font-size: 14px;
      font-family: inherit;
    }
    textarea:focus {
      outline: none;
      border-color: #3b82f6;
      box-shadow: 0 0 0 1px #3b82f6;
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
    }
    input[type="file"] {
      font-size: 12px;
      color: #e5e7eb;
    }
    button {
      border: none;
      border-radius: 999px;
      padding: 8px 16px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      background: #16a34a;
      color: white;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    button:disabled {
      opacity: 0.6;
      cursor: default;
    }
    .status {
      font-size: 12px;
      color: #9ca3af;
    }
  </style>
</head>
<body>
  <header>
    <h1>Basket VLM Test</h1>
    <span>GPT‑4o · local only · images never leave your machine except to OpenAI API</span>
  </header>
  <main>
    <div class="instructions">
      <strong>How to use:</strong>
      Upload 2–4 basket images, then type a prompt like
      <em>"Explain how the first basket differs from the others in shape, handles, and weave."</em>
      and hit Send.
      The server will call GPT‑4o with all images in one request.
    </div>

    <div id="chat" class="chat-box">
      <div class="msg system">No messages yet. Send a prompt to compare your baskets.</div>
    </div>

    <form id="chat-form">
      <textarea id="prompt" placeholder="Ask GPT‑4o to compare the baskets..."></textarea>
      <div class="controls">
        <div>
          <input id="images" type="file" accept="image/*" multiple />
          <div id="preview" class="images-preview"></div>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <span id="status" class="status"></span>
          <button type="submit" id="send-btn">Send</button>
        </div>
      </div>
    </form>
  </main>

  <script>
    const form = document.getElementById("chat-form");
    const promptEl = document.getElementById("prompt");
    const chatEl = document.getElementById("chat");
    const imagesInput = document.getElementById("images");
    const previewEl = document.getElementById("preview");
    const statusEl = document.getElementById("status");
    const sendBtn = document.getElementById("send-btn");

    imagesInput.addEventListener("change", () => {
      previewEl.innerHTML = "";
      const files = Array.from(imagesInput.files || []);
      files.forEach((file, idx) => {
        const img = document.createElement("img");
        img.alt = `basket-${idx + 1}`;
        img.dataset.index = String(idx + 1);
        img.title = `Basket ${idx + 1}`;
        img.src = URL.createObjectURL(file);
        previewEl.appendChild(img);
      });
    });

    function addMessage(role, text) {
      const div = document.createElement("div");
      div.className = "msg " + role;
      div.textContent = text;
      chatEl.appendChild(div);
      chatEl.scrollTop = chatEl.scrollHeight;
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const prompt = promptEl.value.trim();
      const files = Array.from(imagesInput.files || []);
      if (!prompt) {
        alert("Please enter a prompt.");
        return;
      }
      if (files.length === 0) {
        if (!confirm("No images selected. Continue with a text-only query?")) {
          return;
        }
      }

      addMessage("user", prompt);
      statusEl.textContent = "Calling GPT‑4o...";
      sendBtn.disabled = true;

      const formData = new FormData();
      formData.append("prompt", prompt);
      files.forEach((file) => formData.append("images", file));

      try {
        const resp = await fetch("/analyze", {
          method: "POST",
          body: formData,
        });
        const data = await resp.json();
        if (!resp.ok) {
          throw new Error(data.detail || "Request failed");
        }
        addMessage("assistant", data.answer || "[No answer]");
      } catch (err) {
        console.error(err);
        addMessage("assistant", "Error: " + err.message);
      } finally {
        statusEl.textContent = "";
        sendBtn.disabled = false;
      }
    });
  </script>
</body>
</html>
    """


@app.post("/analyze")
async def analyze(
    prompt: str = Form(...),
    images: List[UploadFile] | None = File(default=None),
) -> JSONResponse:
    """Send the prompt + all uploaded images to GPT‑4o for comparative description."""
    try:
        image_contents: List[str] = []
        if images:
            for img in images:
                content = await img.read()
                b64 = base64.b64encode(content).decode("utf-8")
                # Assume PNG/JPEG; browsers will send appropriate content-type, but
                # for the OpenAI data URL we can safely use image/png.
                image_contents.append(f"data:image/png;base64,{b64}")

        message_content: List[dict] = [
            {"type": "text", "text": prompt},
        ]

        for url in image_contents:
            message_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": url,
                    },
                }
            )

        completion = client.chat.completions.create(
            # model="gpt-5",
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a vision-language assistant helping a researcher study how people "
                        "describe baskets. When multiple basket images are provided, focus on "
                        "comparative descriptions: how the first basket differs from the others "
                        "in shape, size, color, handles, weave pattern, and any distinctive marks."
                    ),
                },
                {
                    "role": "user",
                    "content": message_content,
                },
            ],
            # temperature=0.2,
        )

        answer = completion.choices[0].message.content or ""
        return JSONResponse({"answer": answer})
    except Exception as exc:  # pragma: no cover - simple debug surface
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc)},
        )


