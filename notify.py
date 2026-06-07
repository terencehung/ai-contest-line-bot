import os
import requests
import google.generativeai as genai
from datetime import date
import time

# ── 設定 ──────────────────────────────────────────
LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]

SEARCH_QUERIES = [
    "台灣 AI 競賽 獎金   報名",
    "台灣 新創 競賽 獎金  ",
    "AI Hackathon Taiwan 獎金  ",
    "科技創新 AI競賽 台灣 獎金 報名中",
]

# ── Google 搜尋（免費，不需 API Key）─────────────
def google_search(query: str) -> str:
    """用 requests 模擬 Google 搜尋，取得摘要文字"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num=8&hl=zh-TW"
    resp = requests.get(url, headers=headers, timeout=10)
    
    # 簡單擷取搜尋結果中的文字（title + snippet）
    from html.parser import HTMLParser

    class SnippetParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.results = []
            self._current = ""
            self._in_h3 = False
            self._in_span = False

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            if tag == "h3":
                self._in_h3 = True
                self._current = ""
            if tag == "span" and attrs_dict.get("class") in ("aCOpRe", "lEBKkf", "st"):
                self._in_span = True
                self._current = ""

        def handle_endtag(self, tag):
            if tag == "h3" and self._in_h3:
                self._in_h3 = False
                if self._current.strip():
                    self.results.append(f"[標題] {self._current.strip()}")
            if tag == "span" and self._in_span:
                self._in_span = False
                if self._current.strip() and len(self._current.strip()) > 20:
                    self.results.append(f"[摘要] {self._current.strip()}")

        def handle_data(self, data):
            if self._in_h3 or self._in_span:
                self._current += data

    parser = SnippetParser()
    parser.feed(resp.text)
    return "\n".join(parser.results[:20])  # 最多取 20 條


def collect_search_data() -> str:
    """執行多個搜尋查詢，彙整原始資料"""
    all_data = []
    for query in SEARCH_QUERIES:
        print(f"搜尋中：{query}")
        try:
            result = google_search(query)
            if result.strip():
                all_data.append(f"=== 搜尋：{query} ===\n{result}")
        except Exception as e:
            print(f"搜尋失敗：{e}")
        time.sleep(2)  # 避免被 Google 擋
    return "\n\n".join(all_data)


# ── Gemini 整理摘要（免費）────────────────────────
def summarize_with_gemini(raw_data: str) -> str:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")  # 免費版

    today = date.today().strftime("%Y年%m月%d日")
    prompt = f"""今天是 {today}。

以下是從 Google 搜尋到的台灣 AI 競賽相關資訊：

{raw_data}

請從中整理出【目前報名中、有獎金、尚未截止】的 AI 競賽。
若資訊不足某欄位請填「待確認」。
若完全找不到任何比賽，請說明並建議查詢來源。

輸出格式（每場比賽）：
🏆 比賽名稱：
🏢 主辦單位：
📋 內容簡介：
👤 參賽資格：
💰 獎金：
📅 截止日期：
🔗 連結：

最後附上：📌 資料來源時間：{today}"""

    response = model.generate_content(prompt)
    return response.text


# ── LINE Messaging API 推播 ────────────────────────
def send_line_message(text: str):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}",
    }

    # LINE 單則訊息上限 5000 字，超過切分
    max_len = 4800
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]

    for i, chunk in enumerate(chunks):
        header = f"📢 AI競賽日報 {date.today()}"
        if len(chunks) > 1:
            header += f"（{i+1}/{len(chunks)}）"
        
        payload = {
            "to": LINE_USER_ID,
            "messages": [{
                "type": "text",
                "text": f"{header}\n{'─'*20}\n{chunk}"
            }]
        }
        resp = requests.post(url, headers=headers, json=payload)
        print(f"LINE 推播結果：{resp.status_code} {resp.text}")
        time.sleep(1)

print("LINE_TOKEN:", os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "沒有讀到")[:10] + "...")
print("LINE_USER_ID:", os.environ.get("LINE_USER_ID", "沒有讀到"))
print("GEMINI_KEY:", os.environ.get("GEMINI_API_KEY", "沒有讀到")[:10] + "...")
# ── 主程式 ────────────────────────────────────────
def main():
    print("【Step 1】收集 Google 搜尋資料...")
    raw = collect_search_data()

    if not raw.strip():
        send_line_message("⚠️ 今日 AI 競賽搜尋未取得任何資料，請手動確認。\n建議查詢：https://www.nchc.org.tw 或 https://tbrain.trendmicro.com")
        return

    print("【Step 2】Gemini 整理摘要...")
    summary = summarize_with_gemini(raw)

    print("【Step 3】LINE 推播...")
    send_line_message(summary)
    print("完成！")


if __name__ == "__main__":
    main()
