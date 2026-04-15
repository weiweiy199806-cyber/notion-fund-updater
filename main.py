import os
import json
import requests
import time

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

NOTION_VERSION = "2022-06-28"

notion_headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}


def get_fund_value(code: str):
    """
    从东方财富接口获取基金净值和日期，增加了异常捕获
    """
    url = f"https://fundgz.1234567.com.cn/js/{code}.js?rt={int(time.time())}"
    try:
        # 增加 headers 模拟浏览器，减少被拦截风险
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "utf-8"
        text = resp.text

        if not text or "jsonpgz" not in text:
            print(f"[WARN] 基金 {code} 接口返回异常或无数据")
            return None

        # 格式解析：jsonpgz({...});
        content = text[text.find("{") : text.rfind("}") + 1]
        data = json.loads(content)

        value = data.get("dwjz")
        date = data.get("jzrq")
        name = data.get("name")

        if not value or not date:
            return None

        return {
            "code": code,
            "name": name,
            "value": float(value),
            "date": date
        }
    except Exception as e:
        print(f"[ERROR] 获取基金 {code} 发生错误: {e}")
        return None


def find_page_ids_by_code(code: str):
    """
    在 Notion 数据库中查找所有匹配“基金代码”的页面 ID
    """
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    payload = {
        "filter": {
            "property": "基金代码",
            "title": {
                "equals": code
            }
        }
    }
    resp = requests.post(url, headers=notion_headers, json=payload)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results", [])
    
    # 修复点：提取所有匹配的 ID，存入列表返回
    page_ids = [page["id"] for page in results]
    return page_ids


def create_page_for_fund(fund_info):
    """
    如果数据库里没有该基金，则新建一条记录
    """
    url = "https://api.notion.com/v1/pages"
    payload = {
        "parent": {"database_id": DATABASE_ID},
        "properties": {
            "基金代码": {
                "title": [
                    {"text": {"content": fund_info["code"]}}
                ]
            },
            "基金名称": {
                "rich_text": [
                    {"text": {"content": fund_info["name"] or ""}}
                ]
            },
            "最新净值": {
                "number": fund_info["value"]
            },
            "净值日期": {
                "date": {
                    "start": fund_info["date"]
                }
            }
        }
    }
    resp = requests.post(url, headers=notion_headers, json=payload)
    resp.raise_for_status()
    print(f"[CREATE] 已为基金 {fund_info['code']} 创建新页面")


def update_page_for_fund(page_id: str, fund_info):
    url = f"https://api.notion.com/v1/pages/{page_id}"
    payload = {
        "properties": {
            "基金名称": {
                "rich_text": [
                    {"text": {"content": fund_info["name"] or ""}}
                ]
            },
            "最新净值": {
                "number": fund_info["value"]
            },
            "净值日期": {
                "date": {
                    "start": fund_info["date"]
                }
            }
        }
    }
    print("DEBUG payload:", json.dumps(payload, ensure_ascii=False))
    resp = requests.patch(url, headers=notion_headers, json=payload)
    if not resp.ok:
        print("Status:", resp.status_code)
        print("Response:", resp.text)
        resp.raise_for_status()
    print(f"[UPDATE] 基金 {fund_info['code']} 已更新为 {fund_info['value']}（{fund_info['date']}）")


def print_database_schema():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}"
    resp = requests.get(url, headers=notion_headers)
    print("DB schema status:", resp.status_code)
    print(resp.text)

def main():
    if not NOTION_TOKEN or not DATABASE_ID:
        print("错误：请检查环境变量 NOTION_TOKEN 和 NOTION_DATABASE_ID 是否设置。")
        return

    try:
        with open("funds.json", "r", encoding="utf-8") as f:
            fund_codes = json.load(f)
    except FileNotFoundError:
        print("错误：找不到 funds.json 文件。")
        return

   for code in fund_codes:
        print(f"\n[INFO] 正在处理: {code}")
        
        fund_info = get_fund_value(code)
        if not fund_info:
            print(f"[SKIP] 无法获取基金 {code} 的数据，跳过")
            continue

        try:
            # 1. 获取所有匹配的页面 ID 列表
            page_ids = find_page_ids_by_code(code)
            
            if page_ids:
                # 2. 修复点：如果有多个页面，循环更新每一个
                print(f"[INFO] 发现 {len(page_ids)} 条记录，正在同步更新...")
                for pid in page_ids:
                    update_page_for_fund(pid, fund_info)
            else:
                # 3. 如果一条记录都没有，则新建
                create_page_for_fund(fund_info)
                
        except Exception as e:
            print(f"[ERROR] Notion 操作失败 ({code}): {e}")
        
        time.sleep(0.5)


if __name__ == "__main__":
    main()
