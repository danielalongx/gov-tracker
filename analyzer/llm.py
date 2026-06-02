import json
import logging
import sqlite3
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-4-5-20251001"

_ECONOMIC_KEYWORDS = {
    # English
    "tariff", "trade", "sanction", "tax", "economy", "market", "stock",
    "company", "companies", "business", "corp", "industry", "industries",
    "energy", "oil", "gas", "coal", "nuclear", "solar", "tech", "technology",
    "semiconductor", "chip", "ai", "pharma", "healthcare", "drug", "bank",
    "finance", "insurance", "auto", "defense", "agriculture", "retail",
    "media", "streaming", "deal", "regulation", "deregulation",
    "infrastructure", "jobs", "employment", "inflation", "gdp",
    "federal reserve", "interest rate", "import", "export", "investment",
    "earnings", "revenue", "merger", "acquisition", "ipo", "dividend",
    "china", "mexico", "canada", "europe", "russia", "opec",
    "amazon", "apple", "google", "microsoft", "tesla", "tiktok",
    # Chinese
    "经济", "股市", "贸易", "科技", "金融", "关税", "制裁", "通胀",
    "利率", "美联储", "能源", "半导体", "医药", "银行", "并购",
    "营收", "利润", "上市", "监管", "政策", "出口", "进口",
}

# Use <<CONTENT>> and <<SOURCE>> placeholders so embedded JSON examples
# don't need hundreds of escaped braces.
_PROMPT_TEMPLATE = """\
你是一位严格的投资信号分析师。来源类型: <<SOURCE>>

分析以下内容是否包含有价值的投资信号:
<<CONTENT>>

━━━ 评分标准（严格执行）━━━
0-2  政治/选举/社会/娱乐/体育——与市场无关
3-5  宏观经济评论，无具体公司或板块的直接影响
6-8  明确涉及特定公司或行业的政策/市场信号
9-10 直接市场催化剂：具体关税税率、公司并购协议、央行利率决定

⚠️  相关度 ≥ 6 仅当文章有清晰、具体的投资信号时才使用。

━━━ 公司提取规则 ━━━
- 仅列出上市公司（或有明确上市计划的公司）
- 对"石油巨头"等宽泛表述，列出具体前3家（埃克森美孚 XOM、雪佛龙 CVX、BP BP）
- 中国公司同时提供中英文名（腾讯/Tencent TCEHY、阿里巴巴/Alibaba BABA）
- 最多7家公司，ticker未知填 null

━━━ 参考示例 ━━━

【示例1 — 高度相关，评分8】
来源: reuters_news
内容: We are imposing 25% tariffs on all steel and aluminum imports from China effective next month. American steel producers will see immediate benefit. [Reuters]
输出:
{
  "is_relevant": true,
  "sentiment": "混合",
  "tickers": ["X", "NUE", "STLD"],
  "companies": [
    {"name": "美国钢铁 US Steel", "ticker": "X", "impact": "利多"},
    {"name": "纽柯钢铁 Nucor", "ticker": "NUE", "impact": "利多"},
    {"name": "Steel Dynamics", "ticker": "STLD", "impact": "利多"}
  ],
  "industries": ["钢铁", "铝业"],
  "relevance_score": 8,
  "summary": "美国对中国钢铝加征25%关税，直接利好美国本土钢铁生产商（US Steel、Nucor、Steel Dynamics），利空依赖进口钢材的制造业企业。",
  "source_name": "Reuters"
}

【示例2 — 边界相关，评分5】
来源: reuters_news
内容: Federal Reserve officials signal a cautious approach to rate cuts as inflation remains above target, according to meeting minutes. [AP]
输出:
{
  "is_relevant": true,
  "sentiment": "中性",
  "tickers": [],
  "companies": [],
  "industries": ["银行业", "房地产", "债券市场"],
  "relevance_score": 5,
  "summary": "美联储会议纪要显示官员对降息持谨慎态度，对利率敏感行业有潜在压力，但尚无具体政策行动。",
  "source_name": "AP"
}

【示例3 — 不相关，评分1】
来源: trump_news
内容: Trump criticizes mainstream media at campaign rally, says election was stolen and calls for major reforms. [CNN]
输出:
{
  "is_relevant": false,
  "sentiment": "中性",
  "tickers": [],
  "companies": [],
  "industries": [],
  "relevance_score": 1,
  "summary": "纯政治集会内容，无投资相关信号。",
  "source_name": "CNN"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

现在分析上面提供的内容。仅返回JSON对象，不加任何说明：
{
  "is_relevant": <true|false>,
  "sentiment": "<利多|利空|中性|混合>",
  "tickers": [...],
  "companies": [{"name": "...", "ticker": "...或null", "impact": "利多|利空"}],
  "industries": [...],
  "relevance_score": <0-10整数>,
  "summary": "<中文1-2句话>",
  "source_name": "<来源名称>"
}"""

_SOURCE_LABELS = {
    "truth_social":       "Trump Truth Social直接发帖",
    "trump_news":         "Trump相关新闻报道",
    "federal_register":   "美国联邦公报官方文件",
    "denmark_news":       "丹麦经济/商业新闻",
    "eu_news":            "欧盟经济/政策新闻",
    "china_news":         "中国金融/经济新闻",
    "reuters_news":       "路透社宏观金融新闻",
    "us_corporate_news":  "美国企业财报/并购新闻",
    "marketwatch_news":   "MarketWatch市场新闻",
    "ft_news":            "金融时报（FT）新闻",
    "cnbc_news":          "CNBC财经新闻",
    "bloomberg_news":     "彭博社财经新闻",
    "cls_news":           "财联社中国财经新闻",
    "sina_finance":       "新浪财经A股/港股/美股",
    "arkk_trade":         "ARK创新基金（ARKK）持仓变动公告",
    "arkw_trade":         "ARK下一代互联网ETF（ARKW）持仓变动公告",
    "guru_buffett":       "巴菲特（Berkshire Hathaway）SEC 13F持仓申报",
    "guru_burry":         "迈克尔·伯里（Scion）SEC 13F持仓申报",
    "guru_ackman":        "比尔·阿克曼（Pershing Square）SEC 13F持仓申报",
    "guru_dalio":         "瑞·达利欧（Bridgewater）SEC 13F持仓申报",
    "guru_druckenmiller": "斯坦利·德鲁肯米勒（Duquesne）SEC 13F持仓申报",
    "guru_tepper":        "戴维·泰珀（Appaloosa）SEC 13F持仓申报",
    "guru_other":         "机构投资者SEC 13F持仓申报",
}


def _build_prompt(content: str, source: str) -> str:
    label = _SOURCE_LABELS.get(source, source)
    return (
        _PROMPT_TEMPLATE
        .replace("<<CONTENT>>", content[:2000])
        .replace("<<SOURCE>>", label)
    )


def _keyword_prefilter(content: str) -> bool:
    """Return True if content has any economic keyword — saves LLM calls on pure noise."""
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


def _call_llm(client: anthropic.Anthropic, content: str, source: str) -> Optional[dict]:
    try:
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1536,
            messages=[
                {"role": "user", "content": _build_prompt(content, source)}
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
        source: str = post["source"] or ""

        try:
            if not _keyword_prefilter(content):
                logger.debug("Post %d skipped by keyword filter", post_db_id)
            else:
                result = _call_llm(client, content, source)
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
