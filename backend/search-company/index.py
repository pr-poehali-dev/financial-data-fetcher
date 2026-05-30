"""
Поиск компании через MOEX ISS API (Московская биржа) — официальный, бесплатный, без защиты.
Возвращает ИНН, полное название, тикер и прямую ссылку на страницу компании на e-disclosure.ru.
"""
import json
import re
import gzip
import urllib.request
import urllib.parse
import urllib.error


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}

MOEX_BASE = "https://iss.moex.com/iss"
EDISCLOSURE_BASE = "https://www.e-disclosure.ru"


def handler(event: dict, context) -> dict:
    """Поиск компании по названию/ИНН/тикеру через MOEX ISS API. Возвращает список компаний и документы на e-disclosure.ru."""

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    params = event.get("queryStringParameters") or {}
    query = params.get("query", "").strip()
    year = params.get("year", "2023").strip()

    if not query:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Параметр query обязателен"}, ensure_ascii=False),
        }

    companies = _search_moex(query)

    if not companies:
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({"companies": [], "documents": [], "query": query}, ensure_ascii=False),
        }

    top = companies[0]
    documents = _build_edisclosure_links(top, year)

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "query": query,
            "companies": companies,
            "selected": top,
            "documents": documents,
        }, ensure_ascii=False),
    }


def _fetch_json(url: str) -> dict:
    """GET-запрос к MOEX ISS API, возвращает распарсенный JSON."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; FinReport/1.0)",
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
        }
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))


def _search_moex(query: str) -> list:
    """
    Поиск через MOEX ISS /iss/securities.json.
    Возвращает дедуплицированный список эмитентов (не бумаг).
    """
    url = (
        f"{MOEX_BASE}/securities.json"
        f"?q={urllib.parse.quote(query)}&limit=50&iss.meta=off"
        f"&securities.columns=secid,shortname,name,emitent_id,emitent_title,emitent_inn,is_traded"
    )

    data = _fetch_json(url)
    rows = data.get("securities", {}).get("data", [])
    cols = data.get("securities", {}).get("columns", [])

    if not rows:
        return []

    idx = {c: i for i, c in enumerate(cols)}
    seen_inns = set()
    companies = []

    for row in rows:
        secid        = row[idx.get("secid", -1)] or ""
        emitent_id   = row[idx.get("emitent_id", -1)]
        emitent_inn  = row[idx.get("emitent_inn", -1)] or ""
        emitent_name = row[idx.get("emitent_title", -1)] or row[idx.get("name", -1)] or ""

        if not emitent_inn or not emitent_name:
            continue
        key = emitent_inn or str(emitent_id)
        if key in seen_inns:
            continue
        seen_inns.add(key)

        companies.append({
            "id":     str(emitent_id or ""),
            "name":   emitent_name.strip(),
            "inn":    emitent_inn,
            "ticker": secid,
            "url":    f"{EDISCLOSURE_BASE}/poisk-po-kompaniyam?innNumber={emitent_inn}&onlyMatches=1",
            "source": "moex",
        })
        if len(companies) >= 8:
            break

    return companies


def _build_edisclosure_links(company: dict, year: str) -> list:
    inn  = company.get("inn", "")
    name = company.get("name", "")
    docs = []

    if inn:
        docs.append({
            "name":        f"Поиск отчётности {name} ({year}) на e-disclosure.ru",
            "type":        "LINK",
            "url":         f"{EDISCLOSURE_BASE}/poisk-po-kompaniyam?innNumber={inn}&onlyMatches=1",
            "source":      "e-disclosure.ru",
            "size":        "",
            "description": f"Все документы компании с ИНН {inn}",
        })
        docs.append({
            "name":        f"Раскрытие информации {name} — e-disclosure.ru",
            "type":        "LINK",
            "url":         f"{EDISCLOSURE_BASE}/poisk-po-kompaniyam?innNumber={inn}&onlyMatches=1&year={year}",
            "source":      "e-disclosure.ru",
            "size":        "",
            "description": f"Документы за {year} год",
        })

    moex_docs = _fetch_moex_filings(company, year)
    docs.extend(moex_docs)
    return docs


def _fetch_moex_filings(company: dict, year: str) -> list:
    ticker = company.get("ticker", "")
    if not ticker:
        return []
    docs = []
    try:
        data = _fetch_json(f"{MOEX_BASE}/securities/{ticker}/disclosure.json?iss.meta=off&limit=20")
        for section_key in ("disclosure", "filings", "reports"):
            section = data.get(section_key, {})
            rows    = section.get("data", [])
            cols    = section.get("columns", [])
            if not rows:
                continue
            idx = {c: i for i, c in enumerate(cols)}
            for row in rows:
                title = _get(row, idx, "title") or _get(row, idx, "name") or ""
                url   = _get(row, idx, "url") or _get(row, idx, "fileUrl") or ""
                ftype = _get(row, idx, "type") or ""
                date  = _get(row, idx, "date") or _get(row, idx, "publishedDate") or ""
                if not url or not title:
                    continue
                if year and year not in str(date) and year not in title and year not in url:
                    continue
                ext = _guess_ext(url, ftype)
                if not url.startswith("http"):
                    url = MOEX_BASE + url
                docs.append({"name": title[:150], "type": ext, "url": url, "source": "moex.com", "size": ""})
                if len(docs) >= 8:
                    return docs
    except Exception:
        pass
    return docs


def _get(row, idx, key):
    i = idx.get(key, -1)
    return row[i] if 0 <= i < len(row) else None


def _guess_ext(url, ftype):
    for ext in ("pdf", "xlsx", "xls", "zip", "rar"):
        if url.split("?")[0].lower().endswith(f".{ext}"):
            return ext.upper()
    if "pdf" in ftype.lower():
        return "PDF"
    if "xls" in ftype.lower():
        return "XLSX"
    return "PDF"
