"""Headless-браузер для поиска документов на e-disclosure.ru."""
import os, sys, re, glob, subprocess, json

BROWSERS_PATH = "/tmp/ms-playwright"
BASE = "https://www.e-disclosure.ru"


def chromium_exe():
    found = glob.glob(BROWSERS_PATH + "/chromium-*/chrome-linux/chrome")
    return found[0] if found else None


def ensure_chromium():
    exe = chromium_exe()
    if exe:
        return exe
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": BROWSERS_PATH}
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        env=env, check=True, timeout=240,
    )
    exe = chromium_exe()
    if not exe:
        raise RuntimeError("Chromium не найден после установки")
    return exe


def browse_edisclosure(inn, company_name, year):
    chrome = ensure_chromium()
    from playwright.sync_api import sync_playwright

    docs, errors, company_page_url = [], [], ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chrome, headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu",
                  "--single-process", "--no-zygote"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900}, locale="ru-RU",
        )
        page = ctx.new_page()
        try:
            page.goto(f"{BASE}/poisk-po-kompaniyam?innNumber={inn}&onlyMatches=1",
                      wait_until="networkidle", timeout=25000)
            try:
                page.wait_for_selector("a[href*='company.aspx']", timeout=10000)
                href = page.locator("a[href*='company.aspx']").first.get_attribute("href") or ""
                if href:
                    company_page_url = (BASE + href) if href.startswith("/") else href
                    page.goto(company_page_url, wait_until="networkidle", timeout=25000)
            except Exception as e:
                errors.append(f"nav: {str(e)[:80]}")

            for text in ["МСФО", "Финансовая отчётность", "Годовой отчёт", "Отчетность"]:
                try:
                    page.get_by_text(text, exact=False).first.click(timeout=2000)
                    page.wait_for_load_state("networkidle", timeout=8000)
                    break
                except Exception:
                    continue

            html = page.content()
            docs = parse_file_links(html, year, "e-disclosure.ru", BASE)
            if not docs:
                docs = parse_file_links(html, "", "e-disclosure.ru", BASE)
        except Exception as e:
            errors.append(f"browse: {str(e)[:150]}")
        finally:
            browser.close()

    return {"company_page": company_page_url, "documents": docs[:10], "errors": errors}


def parse_file_links(html, year, source, base):
    import re
    pat = re.compile(r'href=["\']([^"\']*\.(pdf|xlsx?|zip|rar)(?:\?[^"\']*)?)["\']', re.IGNORECASE)
    docs, seen = [], set()
    for m in pat.finditer(html):
        url = m.group(1)
        ext = m.group(2).upper()
        if not url.startswith("http"):
            url = base + url if url.startswith("/") else base + "/" + url
        if url in seen:
            continue
        seen.add(url)
        ctx = html[max(0, m.start()-200): m.end()+200]
        names = re.findall(r'>([^<]{4,100})<', ctx)
        name = next((n.strip() for n in names if len(n.strip()) > 4),
                    url.split("/")[-1].split("?")[0])
        name = re.sub(r'\s+', ' ', name).strip()[:150]
        ym = (not year) or (year in url) or (year in ctx)
        docs.append({"name": name, "type": ext, "url": url, "source": source, "size": "", "_ym": ym})
    docs.sort(key=lambda d: not d.pop("_ym"))
    return docs[:10]
