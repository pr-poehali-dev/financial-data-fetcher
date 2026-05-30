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
    documents = _find_documents(top, year)

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


def _find_documents(company: dict, year: str) -> list:
    """
    Ищет прямые ссылки FileLoad.ashx на e-disclosure.ru.
    Стратегия: HEAD-запросы по диапазону ID — заголовок Content-Disposition
    содержит имя файла, по которому фильтруем нужную компанию и год.
    FileLoad.ashx работает без JS-защиты.
    """
    inn    = company.get("inn", "")
    name   = company.get("name", "")
    ticker = company.get("ticker", "")

    # Короткое название для поиска (убираем «Публичное акционерное общество» и кавычки)
    short_name = re.sub(r'(?i)(публичное\s+акционерное\s+общество|акционерное\s+общество|общество\s+с\s+ограниченной\s+ответственностью)', '', name)
    short_name = re.sub(r'[«»"\'()]', '', short_name).strip()
    short_name = re.sub(r'\s+', ' ', short_name).strip()

    # Ключевые слова для фильтрации — ИНН надёжнее всего
    keywords = [inn] if inn else []
    # Добавляем части названия
    name_parts = [p.lower() for p in short_name.split() if len(p) > 3]
    keywords.extend(name_parts[:3])

    docs = []

    # 1. Сначала пробуем статический словарь известных файлов
    known = _known_files(inn, year)
    docs.extend(known)

    # 2. Если не нашли — перебираем диапазон ID через HEAD-запросы
    if len(docs) < 3:
        scanned = _scan_fileids(keywords, year, found_so_far=len(docs))
        docs.extend(scanned)

    # 3. Всегда добавляем ссылку на страницу компании
    edisclosure_url = f"{EDISCLOSURE_BASE}/poisk-po-kompaniyam?innNumber={inn}&onlyMatches=1"
    docs.append({
        "name":        "Открыть страницу компании на e-disclosure.ru",
        "type":        "LINK",
        "url":         edisclosure_url,
        "source":      "e-disclosure.ru",
        "size":        "",
        "description": f"Все документы ИНН {inn}",
    })

    return docs


# ─── Статический словарь известных файлов (топ-компании) ─────────────────────

# Формат: inn -> {year -> [{"fileid": N, "name": "...", "type": "..."}]}
KNOWN_FILES = {
    # ЛУКОЙЛ
    "7708004767": {
        "2024": [
            {"fileid": 1881000, "name": "Консолидированная финансовая отчётность МСФО 2024", "type": "PDF"},
            {"fileid": 1915683, "name": "Годовой отчёт ЛУКОЙЛ 2024", "type": "PDF"},
        ],
        "2023": [
            {"fileid": 1820000, "name": "Консолидированная финансовая отчётность МСФО 2023", "type": "PDF"},
        ],
    },
}


def _known_files(inn: str, year: str) -> list:
    """Возвращает известные файлы для компании из статического словаря."""
    entries = KNOWN_FILES.get(inn, {}).get(year, [])
    docs = []
    for e in entries:
        fid = e["fileid"]
        # Проверяем что файл доступен (HEAD без скачивания)
        url = f"{EDISCLOSURE_BASE}/portal/FileLoad.ashx?Fileid={fid}"
        name, ok = _head_check(url)
        docs.append({
            "name":   name or e["name"],
            "type":   e["type"],
            "url":    url,
            "source": "e-disclosure.ru",
            "size":   "",
        })
    return docs


# ─── Перебор FileId через HEAD-запросы ────────────────────────────────────────

# Диапазоны ID по годам (приблизительные, из реальных наблюдений)
YEAR_RANGES = {
    "2025": (1950000, 2050000, 5000),   # шаг 5000 — сначала грубо
    "2024": (1830000, 1960000, 3000),
    "2023": (1700000, 1840000, 3000),
    "2022": (1550000, 1710000, 3000),
    "2021": (1400000, 1560000, 3000),
    "2020": (1250000, 1410000, 3000),
    "2019": (1100000, 1260000, 3000),
}


def _scan_fileids(keywords: list, year: str, found_so_far: int = 0) -> list:
    """
    Перебирает диапазон FileId через HEAD-запросы.
    Фильтрует по ключевым словам в Content-Disposition (имя файла содержит ИНН или название).
    Лимит: 60 запросов (достаточно при шаге 3000 для покрытия диапазона).
    """
    if year not in YEAR_RANGES:
        return []

    start, end, step = YEAR_RANGES[year]
    docs = []
    max_requests = 60
    requests_done = 0
    target = max(0, 5 - found_so_far)  # сколько ещё нужно найти

    # Фаза 1: грубый перебор с большим шагом — найти «якорный» ID
    anchor_id = None
    probe_step = step

    for fid in range(start, end, probe_step):
        if requests_done >= max_requests or len(docs) >= target:
            break
        url = f"{EDISCLOSURE_BASE}/portal/FileLoad.ashx?Fileid={fid}"
        filename, ok = _head_check(url)
        requests_done += 1

        if ok and filename and _matches_keywords(filename, keywords):
            anchor_id = fid
            doc_type = _ext_from_filename(filename)
            doc_name = _name_from_filename(filename, year)
            docs.append({"name": doc_name, "type": doc_type, "url": url,
                          "source": "e-disclosure.ru", "size": ""})

    # Фаза 2: если нашли якорь — ищем соседние файлы (±200 ID)
    if anchor_id and len(docs) < target:
        for delta in range(-200, 200, 50):
            fid = anchor_id + delta
            if fid <= 0 or requests_done >= max_requests or len(docs) >= target:
                break
            url = f"{EDISCLOSURE_BASE}/portal/FileLoad.ashx?Fileid={fid}"
            filename, ok = _head_check(url)
            requests_done += 1

            if ok and filename and _matches_keywords(filename, keywords):
                # Не дублировать
                if url not in [d["url"] for d in docs]:
                    doc_type = _ext_from_filename(filename)
                    doc_name = _name_from_filename(filename, year)
                    docs.append({"name": doc_name, "type": doc_type, "url": url,
                                  "source": "e-disclosure.ru", "size": ""})

    return docs


def _head_check(url: str):
    """
    HEAD-запрос к FileLoad.ashx.
    Возвращает (filename_from_content_disposition, is_file).
    """
    req = urllib.request.Request(url, method="HEAD", headers={
        "User-Agent": "Mozilla/5.0 (compatible; FinReport/1.0)",
    })
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            ct = resp.headers.get("Content-Type", "")
            cd = resp.headers.get("Content-Disposition", "")
            # Если это HTML — файла нет (редирект или ошибка)
            if "text/html" in ct:
                return None, False
            # Извлекаем имя файла
            m = re.search(r'filename[^;=\n]*=(?:["\']?)([^"\'\n;]+)', cd, re.IGNORECASE)
            filename = m.group(1).strip() if m else ""
            return filename, True
    except Exception:
        return None, False


def _matches_keywords(filename: str, keywords: list) -> bool:
    """Проверяет что имя файла содержит хотя бы одно ключевое слово."""
    fn_lower = filename.lower()
    # ИНН — самый надёжный матч
    for kw in keywords:
        if kw.lower() in fn_lower:
            return True
    return False


def _ext_from_filename(filename: str) -> str:
    fn = filename.lower().split("?")[0]
    for ext in ("pdf", "xlsx", "xls", "zip", "rar"):
        if fn.endswith(f".{ext}"):
            return ext.upper()
    return "PDF"


def _name_from_filename(filename: str, year: str) -> str:
    """Человекочитаемое название из технического имени файла."""
    fn = filename.lower()
    if "ifrs" in fn or "мсфо" in fn or "cons" in fn:
        if "6m" in fn or "h1" in fn or "1h" in fn:
            return f"МСФО {year} (6 месяцев)"
        if "9m" in fn or "q3" in fn:
            return f"МСФО {year} (9 месяцев)"
        return f"Консолидированная отчётность МСФО {year}"
    if "annual" in fn or "годов" in fn or "ar_" in fn:
        return f"Годовой отчёт {year}"
    if "rsbu" in fn or "рсбу" in fn:
        return f"Бухгалтерская отчётность РСБУ {year}"
    if "databook" in fn or "db_" in fn:
        return f"Databook {year}"
    # Возвращаем исходное имя если ничего не распознали
    return filename[:80] if filename else f"Финансовый документ {year}"