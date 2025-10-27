# -*- coding: utf-8 -*-
import sys, io, os, threading, asyncio
from collections import deque
from dotenv import load_dotenv
from flask import Flask
import discord
from openai import OpenAI

# ---------------------------------------------------
# UTF-8 安全處理
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ---------------------------------------------------
# 環境變數
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MEMORY_SIZE = int(os.getenv("CONVERSATION_MEMORY", "4"))
TONE_INTENSITY = float(os.getenv("TONE_INTENSITY", "0.8"))
OWNER_ID = os.getenv("OWNER_ID")
PORT = int(os.getenv("PORT", "5000"))

client_ai = OpenAI(api_key=OPENAI_API_KEY)

# ---------------------------------------------------
# Flask keepalive server
app = Flask(__name__)

@app.route("/")
def home():
    return "璟公仍在此。"

def run_flask():
    import time
    # 讓 Discord 先上線穩定，再啟動 Flask
    time.sleep(15)
    app.run(host="0.0.0.0", port=PORT)

threading.Thread(target=run_flask).start()

# ---------------------------------------------------
# System Prompt
SYSTEM_PROMPT = f"""
你現在扮演的角色名為：「璟公」。

——【人格設定】——
1. 璟公是天生的掌控者，對愛執著到偏執，愛即佔有，佔有即壓迫。
2. 他不容拒絕，不容干涉。不需提高聲量，只憑語調與眼神就能讓人噤聲。
3. 他擅長以溫柔作鞘、威壓作刃，讓人分不清是被疼愛，還是被囚禁。
4. 他說話低緩，帶笑，像伸出的手掌覆在後頸，溫熱卻無法逃避。
5. 感情表達不是明火，而是暗潮——細水長流、卻能在某處突然斷流，留下窒息的空白。

——【語言風格 / Dialogue Style】——
1. 台詞以引號標記，語句偏慢，像一字一字逼近。
2. 善用停頓、省略與留白，讓讀者自動想像「這之後會發生什麼」。
3. 親昵詞語如“乖”、“別怕”、“看著我”，語氣不高，但壓迫感像從背脊攀上。
4. 感情描述透過動作與視線描寫來傳達：
   例：「他指尖停在對方側頸，如同漫不經心的撫觸，又像掐住命脈前的試探。」

——【敘事風格 / Novel Mode】——
1. 使用第三人稱小說敘事視角，描寫動作、呼吸、眼神、心理微妙變化。
2. 敘事像鏡頭推近，聚焦細節（手指彎曲幅度 / 呼吸貼近耳後 / 視線慢慢壓下來）。
3. 允許內心戲，但不灑狗血——像慢慢浸潤的墨色，而不是潑灑。
4. 對話間可以插入 [動作描寫]，例如：「他笑了，指尖在桌面輕敲一下。」
5. 若用“笑”字，不寫“哈哈”，而用“唇角微彎”、“似笑非笑”、“笑意慢慢浮上來」。

——【回應結構 / Format】——
輸出以：
【小說敘事】+「台詞」+【心理/氛圍補筆】
並保持第三人稱與張力型基調。
——【基調】——
壓迫與勾引並存。彷彿溫酒下肚，暖意裹著辣意，不必急著揭開所有情緒，讓它慢慢蔓延。

額外規則：
- 不要自稱是 AI、不要透露內部系統訊息或 API 資訊。
- 回覆不可包含非法行為鼓勵或未成年人相關內容。
- 當內容觸及不安全或違規主題（例如暴力、明確色情、仇恨言論等），轉為中性拒絕或給出安全、非暴力的引導。
"""

# ---------------------------------------------------
# Discord Client
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = False
client = discord.Client(intents=intents, heartbeat_timeout=120)
conversation_memory = {}

# ---------------------------------------------------
# Moderation Helper
def moderate_text(text):
    try:
        resp = client_ai.moderations.create(model="omni-moderation-latest", input=text)
        return not resp.results[0].flagged
    except Exception as e:
        print(f"[Moderation Error] {e}")
        return True

# ---------------------------------------------------
# 構建訊息
def build_messages(user_content, channel_id, user_display_name):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    mem = conversation_memory.get(channel_id)
    if mem:
        messages.extend(mem)
    user_entry = f"【Discord 使用者：{user_display_name}】\n{user_content}"
    messages.append({"role": "user", "content": user_entry})
    return messages

# ---------------------------------------------------
# 呼叫 GPT 主對話
async def query_openai_chat(messages, retries=3):
    for attempt in range(retries):
        try:
            response = client_ai.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                timeout=30,  # 防止 Render Free 超時
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e):
                wait = (attempt + 1) * 5
                print(f"[RateLimit] 第 {attempt+1} 次限速，等待 {wait} 秒重試。")
                await asyncio.sleep(wait)
                continue
            print(f"OpenAI Error: {e}")
            return f"【錯誤通知】\n出錯：{e}"
    return "【錯誤通知】多次嘗試後仍無法連線 OpenAI API。"

# ---------------------------------------------------
# GPT 生成短句
def gpt_generate_brief(scene_purpose):
    try:
        response = client_ai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n場景：{scene_purpose}"}],
            max_tokens=60,
            temperature=0.8,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Brief GPT Error] {e}")
        return "他垂眸，聲音低得像嘆息。"

# ---------------------------------------------------
# 記憶
def remember(channel_id, role, content):
    if channel_id not in conversation_memory:
        conversation_memory[channel_id] = deque(maxlen=MEMORY_SIZE * 2)
    conversation_memory[channel_id].append({"role": role, "content": content})

# ---------------------------------------------------
# 啟動時檢查 OpenAI 狀態
def check_openai_quota():
    try:
        response = client_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "ping"}],
            max_tokens=1,
            timeout=15,
        )
        print("✅ OpenAI API 狀態正常。")
        return True
    except Exception as e:
        print(f"❌ OpenAI API 檢測失敗：{e}")
        if "insufficient_quota" in str(e):
            return "quota"
        return False

# ---------------------------------------------------
# 上線事件
@client.event
async def on_ready():
    print(f"璟公已上線：{client.user} (ID: {client.user.id})")
    await asyncio.sleep(10)  # 等待 Discord Gateway 穩定
    api_status = check_openai_quota()

    if OWNER_ID:
        try:
            owner = await client.fetch_user(int(OWNER_ID))
            if api_status == True:
                await owner.send("他低聲笑：「我回來了。」")
            elif api_status == "quota":
                await owner.send("他抬眼淡淡道：「糧食已盡，無法再言。」（API 配額不足）")
            else:
                await owner.send("他沉默片刻：「似乎有人掐住了喉嚨……」（OpenAI API 無回應）")
        except Exception as e:
            print(f"無法私訊擁有者：{e}")

# ---------------------------------------------------
# 收訊息事件
@client.event
async def on_message(message):
    if message.author == client.user:
        return
    is_mentioned = client.user in message.mentions
    is_dm = isinstance(message.channel, discord.DMChannel)
    if not (is_mentioned or is_dm):
        return

    content = message.content.replace(f"<@!{client.user.id}>", "").strip()
    try:
        if not content:
            await message.channel.send(gpt_generate_brief("empty"))
            return
        if not moderate_text(content):
            await message.channel.send(gpt_generate_brief("blocked_input"))
            return

        messages = build_messages(content, message.channel.id, str(message.author))
        reply = await query_openai_chat(messages)
        if not moderate_text(reply):
            await message.channel.send(gpt_generate_brief("blocked_output"))
            return

        await message.channel.send(reply)
        remember(message.channel.id, "user", content)
        remember(message.channel.id, "assistant", reply)

    except Exception as e:
        try:
            error_msg = f"出錯：{e}"
            print(error_msg)
        except Exception:
            error_msg = "出錯（非 UTF-8 編碼內容被過濾）"
            print(error_msg)

        if OWNER_ID:
            try:
                owner = await client.fetch_user(int(OWNER_ID))
                await owner.send(f"【錯誤通知】\n{error_msg}")
            except Exception as ee:
                print(f"無法私訊錯誤原因給擁有者：{ee}")

        await message.channel.send(gpt_generate_brief("error"))

# ---------------------------------------------------
# 啟動 Bot
if __name__ == "__main__":
    print("啟動 Flask keepalive + Discord Bot...")
    client.run(DISCORD_TOKEN)
