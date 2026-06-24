# Taglish AI Voice Insurance Agent

A real-time AI voice agent that speaks natural Taglish (Tagalog + English) to market insurance products to young Filipino professionals. Built with [Pipecat](https://github.com/pipecat-ai/pipecat), it joins a Daily video room, listens to callers via Cartesia STT, thinks with Qwen LLM, and responds with Cartesia TTS — all with support for voice interruptions.

## Products the agent covers

| Product | Target audience |
|---|---|
| **WanderSafe Travel Insurance** | Travelers (Korea, Japan, Europe) |
| **GadgetShield Plus** | Remote workers with expensive devices |
| **IncomeGuard Critical Illness** | Employees who want coverage beyond their HMO |
| **FurParent Vet Care** | Millennial/Gen Z pet owners |

## Architecture

```
Daily room (audio in/out)
    └── Cartesia STT  →  Qwen LLM  →  Cartesia TTS
              ↑                              ↓
         Silero VAD                 Daily room output
```

The pipeline runs inside [Pipecat](https://github.com/pipecat-ai/pipecat) and supports real-time interruptions via `allow_interruptions=True`.

## Prerequisites

- Python 3.9+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Accounts and API keys for:
  - [Daily](https://www.daily.co/) — video/audio room transport
  - [Cartesia](https://cartesia.ai/) — STT + TTS (`sonic-3.5` model, Tagalog voice)
  - [DashScope / Alibaba Cloud](https://dashscope.aliyuncs.com/) — Qwen LLM

## Setup

1. Clone the repo and install dependencies:

   ```bash
   uv sync
   ```

2. Copy the example env file and fill in your keys:

   ```bash
   cp .env.example .env
   ```

   | Variable | Description |
   |---|---|
   | `DAILY_ROOM_URL` | URL of the Daily room the bot should join |
   | `DAILY_API_KEY` | Daily API key |
   | `CARTESIA_API_KEY` | Cartesia API key (used for both STT and TTS) |
   | `CARTESIA_VOICE_ID` | Cartesia voice ID for Tagalog output |
   | `DASHSCOPE_API_KEY` | DashScope API key for Qwen LLM |
   | `OPENAI_API_KEY` | OpenAI API key (optional, for future use) |
   | `DEEPGRAM_API_KEY` | Deepgram API key (optional, for future use) |

## Running the bot

```bash
uv run python bot.py
```

The bot will connect to the Daily room specified in `DAILY_ROOM_URL` and wait for a participant to join. Once someone joins, it delivers an opening Taglish greeting and begins the conversation.

## Behavior

- Greets callers in natural Taglish and introduces all four products
- Answers questions about any of the four insurance products
- Gently redirects off-topic questions back to the products
- Never uses formal/deep Tagalog — keeps the tone casual and conversational
- Keeps responses to 1–3 sentences, optimized for voice
