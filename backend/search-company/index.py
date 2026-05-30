"""
Поиск компании на e-disclosure.ru и получение списка документов отчётности.
Обход антибот-защиты: реальные браузерные заголовки, сессионные куки, gzip, Referer-цепочка.
"""
import json
import re
import gzip
import time
import http.cookiejar
import urllib.request
import urllib.parse
import urllib.error


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}

BASE = "https://www.e-disclosure.ru"

# Заголовки реального браузера Chrome 124 Windows
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Upgrade-Insecure-Requests": "1",
    "Connection": "keep-alive",
}


def _make_opener() -> urllib.request.OpenerDirector:
    """Создаёт opener с куки-jar, редиректами и gzip."""
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPRedirectHandler(),
    )
    return opener


def _fetch(opener: urllib.request.OpenerDirector, url: str, referer: str = BASE, timeout: int = 12) -> str:
    """Загружает страницу с браузерными заголовками, возвращает HTML-строку."""
    headers = {**BROWSER_HEADERS, "Referer": referer}
    req = urllib.request.Request(url, headers=headers)
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read()
        enc = resp.headers.get("Content-Encoding", "")
        if enc == "gzip":
            raw = gzip.decompress(raw)
        elif enc == "br":
            # Если br недоступен — пробуем как есть
            try:
                import brotli
                raw = brotli.decompress(raw)
            except Exception:
                pass
        charset = _detect_charset(resp.headers.get("Content-Type", ""))
        return raw.decode(charset, errors="replace")


def _detect_charset(content_type: str) -> str:
    m = re.search(r'charset=([^\s;]+)', content_type, re.IGNORECASE)
    return m.group(1) if m else "utf-8"


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

    opener = _make_opener()

    # Шаг 1: «прогреваем» сессию — заходим на главную, получаем куки
    try:
        _fetch(opener, BASE + "/", referer=BASE, timeout=8)
    except Exception:
        pass

    # Шаг 2: ищем компании
    companies = _search_companies(opener, query)

    if not companies:
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"companies": [], "documents": [], "query": query}, ensure_ascii=False),
        }

    top = companies[0]
    documents = _fetch_documents(opener, top["id"], year) if top["id"] else []

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


def _search_companies(opener: urllib.request.OpenerDirector, query: str) -> list:
    """Поиск через внутренний Ajax-endpoint e-disclosure.ru."""

    # Вариант 1: Ajax-автодополнение (используется на сайте)
    ajax_url = (
        f"{BASE}/Search/Autocomplete"
        f"?term={urllib.parse.quote(query)}&searchType=1"
    )
    try:
        req = urllib.request.Request(
            ajax_url,
            headers={
                **BROWSER_HEADERS,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{BASE}/poisk-po-kompaniyam",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Dest": "empty",
            }
        )
        with opener.open(req, timeout=10) as resp:
            raw = resp.read()
            enc = resp.headers.get("Content-Encoding", "")
            if enc == "gzip":
                raw = gzip.decompress(raw)
            data = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(data, list) and data:
                return [_normalize_autocomplete(c) for c in data[:8] if c]
    except Exception:
        pass

    # Вариант 2: JSON-поиск
    for search_path in [
        f"/poisk-po-kompaniyam?query={urllib.parse.quote(query)}&format=json",
        f"/Search/Search?query={urllib.parse.quote(query)}&page=1&pageSize=10",
    ]:
        try:
            req = urllib.request.Request(
                BASE + search_path,
                headers={
                    **BROWSER_HEADERS,
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{BASE}/poisk-po-kompaniyam",
                }
            )
            with opener.open(req, timeout=10) as resp:
                raw = resp.read()
                enc = resp.headers.get("Content-Encoding", "")
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                data = json.loads(raw.decode("utf-8", errors="replace"))
                items = data.get("items") or data.get("companies") or data.get("results") or []
                if items:
                    return [_normalize_company(c) for c in items[:8] if c]
        except Exception:
            continue

    # Вариант 3: HTML-скрапинг страницы поиска
    return _search_html(opener, query)


def _search_html(opener: urllib.request.OpenerDirector, query: str) -> list:
    """Скрапинг HTML страницы поиска e-disclosure.ru."""
    url = f"{BASE}/poisk-po-kompaniyam?query={urllib.parse.quote(query)}"
    try:
        html = _fetch(opener, url, referer=BASE + "/")
        return _parse_companies_html(html)
    except Exception:
        return []


def _parse_companies_html(html: str) -> list:
    """Парсинг результатов поиска из HTML."""
    companies = []

    # Паттерн 1: ссылки на company.aspx
    pattern = re.compile(
        r'href="[^"]*company\.aspx\?id=(\d+)"[^>]*>\s*([^<]{3,150})</a>',
        re.IGNORECASE
    )
    seen_ids = set()
    for m in pattern.finditer(html):
        company_id = m.group(1)
        if company_id in seen_ids:
            continue
        seen_ids.add(company_id)
        name = re.sub(r'\s+', ' ', m.group(2)).strip()
        # Пропускаем служебные ссылки
        if len(name) < 4 or name.lower() in ("подробнее", "открыть", "перейти"):
            continue
        # Ищем ИНН рядом
        inn = _find_inn_near(html, m.start(), m.end())
        companies.append({
            "id": company_id,
            "name": name[:150],
            "inn": inn,
            "url": f"{BASE}/portal/company.aspx?id={company_id}",
        })
        if len(companies) >= 8:
            break

    return companies


def _find_inn_near(html: str, start: int, end: int) -> str:
    """Ищет ИНН в радиусе 500 символов вокруг найденного совпадения."""
    window = html[max(0, start - 200): min(len(html), end + 500)]
    m = re.search(r'ИНН[:\s]*(\d{10,12})', window)
    return m.group(1) if m else ""


def _normalize_autocomplete(c) -> dict:
    """Нормализация ответа автодополнения."""
    if isinstance(c, str):
        return {"id": "", "name": c, "inn": "", "url": ""}
    cid = str(c.get("id") or c.get("companyId") or c.get("Id") or "")
    return {
        "id": cid,
        "name": c.get("label") or c.get("value") or c.get("name") or c.get("Name") or "",
        "inn": c.get("inn") or c.get("INN") or c.get("Inn") or "",
        "url": f"{BASE}/portal/company.aspx?id={cid}" if cid else "",
    }


def _normalize_company(c: dict) -> dict:
    cid = str(c.get("id") or c.get("companyId") or "")
    return {
        "id": cid,
        "name": c.get("name") or c.get("companyName") or c.get("fullName") or "",
        "inn": c.get("inn") or c.get("INN") or "",
        "url": f"{BASE}/portal/company.aspx?id={cid}",
    }


def _fetch_documents(opener: urllib.request.OpenerDirector, company_id: str, year: str) -> list:
    """Получение документов со страницы компании."""
    if not company_id:
        return []

    # Сначала пробуем API раскрытия информации
    docs = _fetch_docs_via_api(opener, company_id, year)
    if docs:
        return docs

    # Fallback: скрапинг страницы компании
    url = f"{BASE}/portal/company.aspx?id={company_id}"
    try:
        html = _fetch(opener, url, referer=f"{BASE}/poisk-po-kompaniyam")
        return _parse_documents_html(html, year, company_id)
    except Exception:
        return []


def _fetch_docs_via_api(opener: urllib.request.OpenerDirector, company_id: str, year: str) -> list:
    """Запрос документов через Ajax API e-disclosure.ru."""
    # Эндпоинт раскрытия документов
    api_url = (
        f"{BASE}/portal/company.aspx?id={company_id}"
        f"&attempt=1"
    )
    # Пробуем Ajax-запрос за списком документов
    for endpoint in [
        f"{BASE}/GetCompanyReports?companyId={company_id}&year={year}",
        f"{BASE}/portal/getdisclosure.aspx?id={company_id}&year={year}",
    ]:
        try:
            req = urllib.request.Request(
                endpoint,
                headers={
                    **BROWSER_HEADERS,
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{BASE}/portal/company.aspx?id={company_id}",
                }
            )
            with opener.open(req, timeout=8) as resp:
                raw = resp.read()
                enc = resp.headers.get("Content-Encoding", "")
                if enc == "gzip":
                    raw = gzip.decompress(raw)
                data = json.loads(raw.decode("utf-8", errors="replace"))
                docs = _extract_docs_from_json(data, year)
                if docs:
                    return docs
        except Exception:
            continue
    return []


def _extract_docs_from_json(data, year: str) -> list:
    """Извлечение документов из JSON-ответа."""
    docs = []
    items = data if isinstance(data, list) else (
        data.get("documents") or data.get("files") or data.get("reports") or []
    )
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("fileUrl") or item.get("path") or ""
        name = item.get("name") or item.get("title") or item.get("fileName") or ""
        if not url:
            continue
        if year and year not in url and year not in name:
            continue
        ext = url.split(".")[-1].upper().split("?")[0] if "." in url else "PDF"
        if ext not in ("PDF", "XLS", "XLSX", "ZIP", "RAR"):
            ext = "PDF"
        if not url.startswith("http"):
            url = BASE + url
        docs.append({"name": name[:150] or url.split("/")[-1], "type": ext, "url": url, "source": "e-disclosure.ru", "size": ""})
        if len(docs) >= 10:
            break
    return docs


def _parse_documents_html(html: str, year: str, company_id: str) -> list:
    """Парсинг документов из HTML страницы компании."""
    docs = []

    # Ссылки на файлы
    file_pat = re.compile(
        r'href="(/[^"]*\.(pdf|xls|xlsx|zip|rar)(?:\?[^"]*)?)"[^>]*>([^<]{2,150})',
        re.IGNORECASE
    )
    for m in file_pat.finditer(html):
        path = m.group(1)
        ext = m.group(2).upper()
        name = re.sub(r'\s+', ' ', m.group(3)).strip()
        if not name or len(name) < 3:
            name = path.split("/")[-1].split("?")[0]
        if year and year not in path and year not in name and year not in html[max(0, m.start()-300):m.start()]:
            continue
        docs.append({
            "name": name[:150],
            "type": ext,
            "url": BASE + path if path.startswith("/") else path,
            "source": "e-disclosure.ru",
            "size": "",
        })
        if len(docs) >= 10:
            break

    # Если по году ничего — берём без фильтра (первые 5)
    if not docs:
        for m in file_pat.finditer(html):
            path = m.group(1)
            ext = m.group(2).upper()
            name = re.sub(r'\s+', ' ', m.group(3)).strip() or path.split("/")[-1]
            docs.append({
                "name": name[:150],
                "type": ext,
                "url": BASE + path if path.startswith("/") else path,
                "source": "e-disclosure.ru",
                "size": "",
            })
            if len(docs) >= 5:
                break

    return docs
