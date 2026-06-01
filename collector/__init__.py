from collector.federal_register import fetch_new_documents
from collector.international import (
    fetch_china_news,
    fetch_denmark_news,
    fetch_eu_news,
    fetch_reuters_news,
    fetch_us_corporate_news,
)
from collector.truth_social import fetch_new_posts

__all__ = [
    "fetch_new_posts",
    "fetch_new_documents",
    "fetch_denmark_news",
    "fetch_eu_news",
    "fetch_china_news",
    "fetch_reuters_news",
    "fetch_us_corporate_news",
]
