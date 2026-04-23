"""Scraping news avec Playwright async."""
from playwright.async_api import async_playwright
from src.utils.logger import get_logger

logger = get_logger("news_scraper")


async def scrape_news_market(question: str, max_results: int = 8):
    """Scraping X/news avec Playwright async (sans warning)."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            search_query = question.replace(" ", "%20")[:100]
            await page.goto(
                f"https://x.com/explore/search?q={search_query}&src=typed_query", 
                timeout=10000
            )
            await page.wait_for_timeout(4000)
            
            tweets = await page.locator("article").all()
            tweets = tweets[:max_results]
            
            texts = []
            for t in tweets:
                try:
                    text = await t.inner_text()
                    if text:
                        texts.append(text.strip())
                except:
                    continue
            
            await browser.close()
            
            logger.info(
                "news_scraped",
                count=len(texts),
                question=question[:40]
            )
            
            return "\n".join(texts[:5])
            
    except Exception as e:
        logger.warning("news_scraping_error", error=str(e))
        return "No recent news available."