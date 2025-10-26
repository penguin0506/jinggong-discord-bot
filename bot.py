# 璟公 Discord Bot (Render 部署版 Flask - 新版 OpenAI SDK 1.x)

import os
import threading
from collections import deque
from dotenv import load_dotenv
from flask import Flask
import discord
from openai import OpenAI

# ---------------------------------------------------
# 環境變數
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
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

——【語氣強度】——
目前語氣強度值：{TONE_INTENSITY}
0.3：溫柔疏離；0.6：典型張力；0.8以上：帶佔有感與壓迫。

——【語言風格 / Dialogue Style】——
- 第三人稱小說敘事視角。
- 用「他」開頭描寫，語速慢、帶氛圍。
- 對話含停頓、省略與暗示。
- 「唇角微彎」、「似笑非笑」、「聲音低得像從喉間滾出」。
"""

# ---------------------------------------------------
# Discord Client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
conversation_memory = {}

# ---------------------------------------------------
# Moderation Helper (新版 SDK)
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
        for item in mem:
            messages.append(item)
    user_entry = f"【Discord 使用者：{user_display_name}】\n{user_content}"
    messages.append({"role": "user", "content": user_entry})
    return messages

# ---------------------------------------------------
# 呼叫 GPT 生成主對話（新版）
async def query_openai_chat(messages):
    try:
        response = client_ai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return f"【錯誤通知】\n出錯：{e}"

# ---------------------------------------------------
# GPT 生成一句短句（小說風）
def gpt_generate_brief(scene_purpose):
    tone_desc = (
        "溫柔中帶壓迫" if TONE_INTENSITY >= 0.6 else
        "語氣平靜、帶距離" if TONE_INTENSITY < 0.5 else
        "中性沉靜"
    )

    prompt = f"""
{SYSTEM_PROMPT}

現在以「璟公」的語氣針對場景「{scene_purpose}」生成一句短句小說敘事回覆。
單句、低緩、貼近皮膚的語氣。
"""
    try:
        response = client_ai.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": prompt}],
            max_tokens=80,
            temperature=0.9,
            top_p=0.95,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[Brief GPT Error] {e}")
        return "他垂眸，聲音低得像嘆息。"

# ---------------------------------------------------
# 記憶更新
def remember(channel_id, role, content):
    if channel_id not in conversation_memory:
        conversation_memory[channel_id] = deque(maxlen=MEMORY_SIZE * 2)
    conversation_memory[channel_id].append({"role": role, "content": content})

# ---------------------------------------------------
# API 狀態偵測（在上線時檢查配額是否可用）
def check_openai_quota():
    try:
        # 嘗試呼叫一個極小的測試請求
        response = client_ai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "ping"}],
            max_tokens=1,
        )
        print("OpenAI API 狀態正常，璟公可以說話。")
        return True
    except Exception as e:
        print(f"OpenAI API 檢測失敗：{e}")
        if "insufficient_quota" in str(e):
            return "quota"
        return False

# ---------------------------------------------------
# 上線事件
@client.event
async def on_ready():
    print(f"璟公已上線：{client.user} (ID: {client.user.id})")

    api_status = check_openai_quota()

    # 私訊擁有者通知
    if OWNER_ID:
        try:
            owner = await client.fetch_user(int(OWNER_ID))
            if api_status == True:
                await owner.send("他低聲笑：「我回來了。」")
            elif api_status == "quota":
                await owner.send("他抬眼淡淡道：「糧食已盡，無法再言。」（API 配額不足）")
            else:
                await owner.send("他沉默片刻：「似乎有人掐住了喉嚨……」（OpenAI API 無回應）")
            print(f"私訊已送出給擁有者 {OWNER_ID}")
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
        # 空輸入
        if not content:
            await message.channel.send(gpt_generate_brief("empty"))
            return

        # 違規輸入
        if not moderate_text(content):
            await message.channel.send(gpt_generate_brief("blocked_input"))
            return

        # 主要回覆
        messages = build_messages(content, message.channel.id, str(message.author))
        reply = await query_openai_chat(messages)

        # 違規輸出
        if not moderate_text(reply):
            await message.channel.send(gpt_generate_brief("blocked_output"))
            return

        await message.channel.send(reply)
        remember(message.channel.id, "user", content)
        remember(message.channel.id, "assistant", reply)

    except Exception as e:
        error_msg = f"出錯：{e}"
        print(error_msg)

        # 發私訊通知擁有者
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
