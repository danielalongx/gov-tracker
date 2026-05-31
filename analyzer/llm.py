import json
import logging
import sqlite3
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

_ECONOMIC_KEYWORDS = {
    "tariff", "trade", "sanction", "tax", "economy", "market", "stock",
    "company", "companies", "business", "corp", "industry", "industries",
    "energy", "oil", "gas", "coal", "nuclear", "solar", "tech", "technology",
    "semiconductor", "chip", "ai", "pharma", "healthcare", "drug", "bank",
    "finance", "insurance", "auto", "defense", "agriculture", "retail",
    "media", "streaming", "deal", "regulation", "deregulation",
    "infrastructure", "jobs", "employment", "inflation", "gdp",
    "federal reserve", "interest rate", "import", "export", "investment",
    "china", "mexico", "canada", "europe", "russia", "opec",
    "amazon", "apple", "google", "microsoft", "tesla", "tiktok",
}

_PROMPT = """\
你是一位投资信号分析师。请分析以下帖子或新闻文章中与投资相关的信号。

内容：
{content}

请仅返回一个有效的JSON对象——不要包含markdown格式或任何说明文字：
{{
  "is_relevant": <true|false>,
  "sentiment": "<利多|利空|中性|混合>",
  "tickers": [<被提及或强烈暗示的股票代码，例如 "TSLA">],
  "companies": [
    {{"name": "<公司名称>", "ticker": "<股票代码或null>", "impact": "<利多|利空>"}}
  ],
  "industries": [<受影响的行业，例如"半导体"、"医药"、"能源">],
  "relevance_score": <0到10的整数>,
  "summary": "<用中文写1-2句话的投资信号摘要>",
  "source_name": "<新闻来源或平台名称，例如 Reuters、AP、Politico、Truth Social>"
}}

规则：
- "companies"最多列出7家公司，股票代码未知时填null。
- 知名公司请使用中文名（英伟达、苹果、特斯拉、微软、谷歌、亚马逊、三星、台积电、英特尔、高通、Meta）；不确定的公司保留英文名或代码。
- "source_name"从文章内容中提取发布方名称（通常在方括号内）。

相关度评分：
  0-2  纯政治/个人内容，无经济影响
  3-5  模糊经济提及，市场影响不明确
  6-8  明确暗示对某板块或公司有影响
  9-10 直接影响市场的声明（具体股票、关税税率、政策变化）

请仅返回JSON对象。"""


def _keyword_prefilter(content: str) -> bool:
    """Return True if content has any economic keyword — saves LLM calls on pure rants."""
    text = content.lower()
    return any(kw in text for kw in _ECONOMIC_KEYWORDS)


def _parse_llm_response(raw: str) -> Optional[dict]:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("LLM JSON parse error: %s | raw: %.300s", e, raw)
        return None


def _call_llm(client: anthropic.Anthropic, content: str) -> Optional[dict]:
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[
                {"role": "user", "content": _PROMPT.format(content=content[:2000])}
            ],
        )
        return _parse_llm_response(msg.content[0].text)
    except Exception as e:
        logger.error("LLM API error: %s", e)
        return None


def _save_analysis(conn: sqlite3.Connection, post_db_id: int, result: dict) -> Optional[int]:
    try:
        cur = conn.execute(
            """
            INSERT INTO analysis
                (post_id, is_relevant, sentiment, tickers, companies,
                 industries, relevance_score, summary, source_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post_db_id,
                1 if result.get("is_relevant") else 0,
                result.get("sentiment", "中性"),
                json.dumps(result.get("tickers") or [], ensure_ascii=False),
                json.dumps(result.get("companies") or [], ensure_ascii=False),
                json.dumps(result.get("industries") or [], ensure_ascii=False),
                float(result.get("relevance_score") or 0),
                result.get("summary", ""),
                result.get("source_name", ""),
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.error("DB insert error for analysis of post %d: %s", post_db_id, e)
        return None


def analyze_unprocessed(conn: sqlite3.Connection, client: anthropic.Anthropic) -> list[int]:
    """Analyze all unprocessed posts. Returns analysis row IDs created."""
    posts = conn.execute(
        "SELECT id, content, source FROM posts WHERE processed = 0"
    ).fetchall()

    analysis_ids: list[int] = []

    for post in posts:
        post_db_id: int = post["id"]
        content: str = post["content"] or ""

        try:
            if not _keyword_prefilter(content):
                logger.debug("Post %d skipped by keyword filter", post_db_id)
            else:
                result = _call_llm(client, content)
                if result is not None:
                    aid = _save_analysis(conn, post_db_id, result)
                    if aid:
                        analysis_ids.append(aid)
        except Exception as e:
            logger.error("Unexpected error analyzing post %d: %s", post_db_id, e)
        finally:
            conn.execute("UPDATE posts SET processed = 1 WHERE id = ?", (post_db_id,))
            conn.commit()

    logger.info("Analyzed %d posts → %d analysis records", len(posts), len(analysis_ids))
    return analysis_ids
