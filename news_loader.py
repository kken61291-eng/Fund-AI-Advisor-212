import akshare as ak
import pandas as pd
import os
import json
import time
import random
from datetime import datetime
from utils import logger, get_beijing_time

class NewsLoader:
    def __init__(self):
        self.CACHE_DIR = "data_news"
        if not os.path.exists(self.CACHE_DIR):
            os.makedirs(self.CACHE_DIR)
        
        # 定义新闻文件，按日期存储，如 news_2026-02-09.jsonl
        self.today_str = get_beijing_time().strftime("%Y-%m-%d")
        self.file_path = os.path.join(self.CACHE_DIR, f"news_{self.today_str}.jsonl")

    def _load_existing_titles(self):
        """读取已存新闻的标题，用于去重"""
        titles = set()
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        titles.add(data.get('title', '').strip())
                    except: pass
        return titles

    def fetch_and_save(self):
        """
        获取新闻并追加保存
        """
        existing_titles = self._load_existing_titles()
        new_items = []
        
        logger.info(f"📡 [NewsLoader] 开始增量抓取新闻...")
        
        # --- 源1: 东财财经导读 ---
        try:
            df = ak.stock_news_em(symbol="要闻")
            for _, row in df.iterrows():
                title = str(row.get('新闻标题') or row.get('title')).strip()
                pub_time = str(row.get('发布时间') or row.get('public_time'))
                content = str(row.get('新闻内容') or row.get('content') or title)
                
                # 简单去重和过滤
                if title not in existing_titles and len(title) > 5:
                    new_items.append({
                        "source": "EastMoney",
                        "time": pub_time,
                        "title": title,
                        "content": content[:500] # 只存摘要，节省空间
                    })
                    existing_titles.add(title)
            time.sleep(2)
        except Exception as e:
            logger.warning(f"东财新闻抓取受阻: {e}")

        # --- 源2: 财联社电报 (模拟) ---
        # 这里可以使用您的 requests 代码逻辑，此处简化演示
        # ...

        # --- 保存入库 ---
        if new_items:
            # 按时间排序（可选，尽量保持有序）
            new_items.sort(key=lambda x: x['time'])
            
            with open(self.file_path, 'a', encoding='utf-8') as f:
                for item in new_items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
            
            logger.info(f"💾 [NewsLoader] 新增入库 {len(new_items)} 条新闻。")
        else:
            logger.info("💤 [NewsLoader] 暂无新消息。")

if __name__ == "__main__":
    loader = NewsLoader()
    loader.fetch_and_save()
