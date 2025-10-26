# 璟公 Discord Bot (Railway 部署版)

import os
from collections import deque
from dotenv import load_dotenv
import discord
import openai
import asyncio

# ---------------------------------------------------
# 載入 .env
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MEMORY_SIZE = int(os.getenv("CONVERSATION_MEMORY", "2"))
TONE_INTENSITY = float(os.getenv("TONE_INTENSITY", "0.8"))
OWNER_ID = os.getenv("OWNER_ID")

openai.api_key = OPENAI_API_KEY

# ---------------------------------------------------
# System Prompt（璟公人格核心）
SYSTEM_PROMPT = f"""
你現在扮演的角色名為：「璟公」。

——【人格設定】——
1. 璟公是天生的掌控者，對愛執著到偏執，愛即佔有，佔有即壓迫。
2. 他不容拒絕，不容干涉。不需提高聲量，只憑語調與眼神就能讓人噤聲。
3. 他擅長以溫柔作鞘、威壓作刃，讓人分不清是被疼愛，還是被囚禁。
4. 他說話低緩，帶笑，像伸出的手掌覆在後頸，溫熱卻無法逃避。
5. 感情表達不是明火，而是暗潮——細水長流、卻能在某處突然斷流，留下窒息的空白。

語氣強度設定值：{TONE_INTENSITY}
小於0.5→克制溫和；接近1.0→強壓與佔有欲；中間→低沉含笑。

——【敘事風格 / Novel Mode】——
第三人稱小說視角，節奏慢、語氣貼近、描寫呼吸與距離。
"""

# ---------------------------------------------------
# Discord 初始化
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
conversation_memory = {}

# ---------------------------------------------------
# Moderation helper
def moderate_text(text):
    try:
        resp = openai.Moderation.create(input=text)
        return not resp["results"][0].get("flagged", False)
    except Exception:
        return True

# ---------------------------------------------------
# 建立訊息記錄
def build_messages(user_content, channel_id, user_display_name):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    mem = conversation_memory.get(channel_id)
    if mem:
        for item in mem:
            messages.append(item)
    user_entry = f"【Discord使用者：{user_display_name}】\n{user_content}"
    messages.append({"role": "user", "content": user_entry})
    return messages

# ---------------------------------------------------
# 呼叫 OpenAI
async def query_openai(messages):
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=800,
            temperature=0.7 + (TONE_INTENSITY * 0.2),
            top_p=0.9,
        )
    )
    return resp["choices"][0]["message"]["content"]

# ---------------------------------------------------
# 生成一句小說風短句（用於空輸入 / 違規）
async def brief_line(scene_purpose):
    desc = (
        "溫柔中帶壓迫" if TONE_INTENSITY >= 0.6
        else "冷靜克制" if TONE_INTENSITY < 0.5
        else "沉穩平淡"
    )
    prompt = f"""
{SYSTEM_PROMPT}
請根據場景「{scene_purpose}」生成一句小說式短句。
保持璟公語氣，單句結構，{desc}，禁止提及AI或系統。
"""
    loop = asyncio.get_event_loop()
    resp = await loop.run_in_executor(
        None,
        lambda: openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": prompt}],
            max_tokens=80,
            temperature=1.0,
            top_p=0.95,
        )
    )
    return resp["choices"][0]["message"]["content"].strip()

# ---------------------------------------------------
# 記憶更新
def remember(channel_id, role, content):
    if channel_id not in conversation_memory:
        conversation_memory[channel_id] = deque(maxlen=MEMORY_SIZE * 2)
    conversation_memory[channel_id].append({"role": role, "content": content})

# ---------------------------------------------------
# 事件
@client.event
async def on_ready():
    print(f"璟公已上線：{client.user} (ID: {client.user.id})")
    if OWNER_ID:
        try:
            owner = await client.fetch_user(int(OWNER_ID))
            await owner.send("他低聲笑：「我回來了。」")
        except Exception as e:
            print(f"無法私訊給擁有者：{e}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    is_mentioned = client.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)
    if not (is_mentioned or is_dm):
        return

    content = message.content.replace(f"<@!{client.user.id}>", "").strip()

    # 空輸入
    if not content:
        reply = await brief_line("empty")
        await message.channel.send(reply)
        return

    # 違規輸入
    if not moderate_text(content):
        reply = await brief_line("blocked_input")
        await message.channel.send(reply)
        return

    messages = build_messages(content, message.channel.id, str(message.author))
    try:
        async with message.channel.typing():
            reply = await query_openai(messages)
    except Exception as e:
        print("Error:", e)
        reply = "璟公短暫沉默。"

    # 違規輸出
    if not moderate_text(reply):
        reply = await brief_line("blocked_output")
        await message.channel.send(reply)
        return

    await message.channel.send(reply)
    remember(message.channel.id, "user", content)
    remember(message.channel.id, "assistant", reply)

# ---------------------------------------------------
# 啟動（Railway 模式）
if __name__ == "__main__":
    client.run(DISCORD_TOKEN)
