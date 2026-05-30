"""
Поиск компании на e-disclosure.ru и получение списка документов отчётности.
"""
import json
import os
import re
import urllib.request
import urllib.parse
import urllib.error


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}


def handler(event: dict, context) -> dict:
    """Поиск компании по названию/ИНН/тикеру на e-disclosure.ru, возвращает список документов."""

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    query = params.get("query", "").strip()
    year = params.get("year", "2023").strip()
    period = params.get("period", "annual").strip()

    if not query:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Параметр query обязателен"}, ensure_ascii=False),
        }

    companies = _search_companies(query)
    if not companies:
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"companies": [], "documents": [], "query": query}, ensure_ascii=False),
        }

    top = companies[0]
    documents = _fetch_documents(top["id"], year, period)

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "query": query,
            "companies": companies[:8],
            "selected": top,
            "documents": documents,
        }, ensure_ascii=False),
    }


def _search_companies(query: str) -> list:
    """Поиск компаний через e-disclosure.ru API."""
    url = "https://www.e-disclosure.ru/poisk-po-kompaniyam"
    search_url = f"https://www.e-disclosure.ru/api/search/v1?query={urllib.parse.quote(query)}&page=1&pageSize=10"

    req = urllib.request.Request(
        search_url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; FinReport/1.0)",
            "Accept": "application/json",
            "Referer": url,
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("items") or data.get("companies") or data.get("results") or []
            return [_normalize_company(c) for c in items if c]
    except Exception:
        pass

    # Fallback: поиск через HTML-страницу
    return _search_companies_html(query)


def _search_companies_html(query: str) -> list:
    """Резервный поиск через скрапинг HTML страницы e-disclosure.ru."""
    url = f"https://www.e-disclosure.ru/poisk-po-kompaniyam?query={urllib.parse.quote(query)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        return _parse_companies_from_html(html)
    except Exception:
        return []


def _parse_companies_from_html(html: str) -> list:
    """Извлечение компаний из HTML e-disclosure.ru."""
    companies = []

    # Паттерн для блоков компаний
    pattern = re.compile(
        r'href="/portal/company\.aspx\?id=(\d+)"[^>]*>\s*([^<]{3,120})</a>.*?'
        r'(?:ИНН[:\s]+(\d{10,12}))?',
        re.DOTALL
    )
    for m in pattern.finditer(html):
        company_id = m.group(1)
        name = re.sub(r'\s+', ' ', m.group(2)).strip()
        inn = m.group(3) or ""
        if name and len(name) > 3:
            companies.append({
                "id": company_id,
                "name": name,
                "inn": inn,
                "url": f"https://www.e-disclosure.ru/portal/company.aspx?id={company_id}",
            })
        if len(companies) >= 8:
            break

    return companies


def _normalize_company(c: dict) -> dict:
    return {
        "id": str(c.get("id") or c.get("companyId") or ""),
        "name": c.get("name") or c.get("companyName") or c.get("fullName") or "",
        "inn": c.get("inn") or c.get("INN") or "",
        "url": f"https://www.e-disclosure.ru/portal/company.aspx?id={c.get('id', '')}",
    }


def _fetch_documents(company_id: str, year: str, period: str) -> list:
    """Получение документов отчётности для компании с e-disclosure.ru."""
    if not company_id:
        return []

    url = f"https://www.e-disclosure.ru/portal/company.aspx?id={company_id}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        return _parse_documents_from_html(html, year, company_id)
    except Exception:
        return []


def _parse_documents_from_html(html: str, year: str, company_id: str) -> list:
    """Извлечение документов из страницы компании на e-disclosure.ru."""
    docs = []
    base = "https://www.e-disclosure.ru"

    # Ссылки на файлы (PDF, XLS, XLSX, ZIP)
    file_pattern = re.compile(
        r'href="(/[^"]*\.(pdf|xls|xlsx|zip|rar))"[^>]*>([^<]{3,120})',
        re.IGNORECASE
    )
    for m in file_pattern.finditer(html):
        path = m.group(1)
        ext = m.group(2).upper()
        name = re.sub(r'\s+', ' ', m.group(3)).strip()
        # Фильтр по году
        if year and year not in path and year not in name:
            continue
        if not name or len(name) < 4:
            continue
        docs.append({
            "name": name[:120],
            "type": ext,
            "url": base + path,
            "source": "e-disclosure.ru",
            "size": "",
        })
        if len(docs) >= 10:
            break

    # Ищем ссылки на страницы с отчётностью (МСФО, РСБУ)
    if len(docs) < 3:
        page_pattern = re.compile(
            r'href="(/portal/files/[^"]+)"[^>]*>([^<]{5,100})',
            re.IGNORECASE
        )
        for m in page_pattern.finditer(html):
            path = m.group(1)
            name = re.sub(r'\s+', ' ', m.group(2)).strip()
            if year in name or year in path:
                ext = path.split(".")[-1].upper() if "." in path.split("/")[-1] else "PDF"
                docs.append({
                    "name": name[:120],
                    "type": ext,
                    "url": base + path,
                    "source": "e-disclosure.ru",
                    "size": "",
                })
            if len(docs) >= 10:
                break

    return docs
