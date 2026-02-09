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
        # 数据存储目录
        self.CACHE_DIR = "data_news"
        if not os.path.exists(self.CACHE_DIR):
            os.makedirs(self.CACHE_DIR)
        
        # 按日期分文件存储，例如: data_news/news_2026-02-09.jsonl
        # 使用北京时间确保日期准确
        self.today_str = get_beijing_time().strftime("%Y-%m-%d")
        self.file_path = os.path.join(self.CACHE_DIR, f"news_{self.today_str}.jsonl")

    def _load_existing_titles(self):
        """
        读取已存在的新闻标题，用于增量去重
        """
        titles = set()
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        try:
                            data = json.loads(line)
                            titles.add(data.get('title', '').strip())
                        except: 
                            continue
            except Exception as e:
                logger.warning(f"读取历史新闻文件出错: {e}")
        return titles

    def fetch_and_save(self):
        """
        核心逻辑：抓取 -> 去重 -> 追加写入
        """
        existing_titles = self._load_existing_titles()
        new_items = []
        
        logger.info(f"📡 [NewsLoader] 开始增量抓取新闻 ({self.today_str})...")
        
        # --- 数据源: 东财财经导读 ---
        try:
            # 随机延时防反爬
            time.sleep(random.uniform(2.0, 5.0))
            
            # 获取最新的财经要闻
            df = ak.stock_news_em(symbol="要闻")
            
            # 兼容列名
            title_col = '新闻标题' if '新闻标题' in df.columns else 'title'
            time_col = '发布时间' if '发布时间' in df.columns else 'public_time'
            content_col = '新闻内容' if '新闻内容' in df.columns else 'content'
            
            count = 0
            for _, row in df.iterrows():
                title = str(row.get(title_col, '')).strip()
                pub_time = str(row.get(time_col, ''))
                content = str(row.get(content_col, '')).strip()
                
                # 简单清洗：去除无效标题
                if not title or title == 'nan': continue
                if len(title) < 5: continue
                
                # 去重检查
                if title not in existing_titles:
                    new_items.append({
                        "source": "EastMoney",
                        "time": pub_time,
                        "title": title,
                        "content": content[:200] # 只存摘要，节省空间，主要靠标题
                    })
                    existing_titles.add(title)
                    count += 1
            
            logger.info(f"✅ 从东财获取到 {count} 条新消息")
            
        except Exception as e:
            logger.warning(f"⚠️ 东财新闻抓取受阻: {e}")

        # --- (可选) 在这里添加其他数据源 ---
        
        # --- 保存入库 ---
        if new_items:
            # 按发布时间排序，保证文件内有序
            new_items.sort(key=lambda x: x['time'])
            
            try:
                with open(self.file_path, 'a', encoding='utf-8') as f:
                    for item in new_items:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
                
                logger.info(f"💾 [NewsLoader] 成功入库 {len(new_items)} 条新闻 -> {self.file_path}")
            except Exception as e:
                logger.error(f"❌ 写入文件失败: {e}")
        else:
            logger.info("💤 [NewsLoader] 暂无新消息，文件未更新。")

if __name__ == "__main__":
    loader = NewsLoader()
    loader.fetch_and_save()
