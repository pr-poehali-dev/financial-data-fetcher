"""
Загрузка документа (PDF или XLSX) по URL и извлечение финансовых показателей.
PDF парсится через pdfminer.six — точное извлечение текста с сохранением структуры страниц.
XLSX парсится через openpyxl — читаем ячейки с сохранением связи «метка строки — значение».
"""
import json
import re
import io
import http.cookiejar
import urllib.request
import urllib.error


CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ


def handler(event: dict, context) -> dict:
    """Скачивает документ по URL и извлекает запрошенные финансовые показатели."""

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        body = {}

    # Режим поиска документов через headless-браузер
    if body.get("action") == "browse":
        inn     = body.get("inn", "").strip()
        company = body.get("company", "").strip()
        year    = body.get("year", "2023").strip()
        if not inn:
            return _err(400, "Параметр inn обязателен для action=browse")
        try:
            import browser as br
            result = br.browse_edisclosure(inn, company, year)
            result.update({"inn": inn, "company": company, "year": year})
            return {"statusCode": 200, "headers": CORS_HEADERS,
                    "body": json.dumps(result, ensure_ascii=False)}
        except Exception as e:
            return _err(500, f"Браузер: {str(e)[:300]}")

    doc_url = body.get("url", "").strip()
    metrics  = body.get("metrics", [])
    company  = body.get("company", "")
    year     = body.get("year", "")

    if not doc_url:
        return _err(400, "URL документа обязателен")
    if not metrics:
        return _err(400, "Список показателей пуст")

    metrics = [str(m).strip() for m in metrics[:20] if str(m).strip()]

    # Тип файла по расширению в URL
    url_clean = doc_url.lower().split("?")[0]
    if url_clean.endswith((".xlsx", ".xls")):
        file_type = "xlsx"
    elif url_clean.endswith((".zip", ".rar")):
        file_type = "archive"
    else:
        file_type = "pdf"

    file_data, error = _download_file(doc_url)
    if error:
        return _err(422, error)

    # Извлекаем структурированный текст
    if file_type == "xlsx":
        pages = _extract_xlsx(file_data)
    elif file_type == "pdf":
        pages = _extract_pdf(file_data)
    else:
        pages = []

    if not pages:
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "metrics": [],
                "raw_text_length": 0,
                "warning": "Не удалось извлечь текст. Возможно, PDF является сканом без текстового слоя.",
                "file_type": file_type,
            }, ensure_ascii=False),
        }

    full_text = "\n".join(pages)
    results = _find_metrics(full_text, pages, metrics, year)

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "company": company,
            "year": year,
            "doc_url": doc_url,
            "file_type": file_type,
            "raw_text_length": len(full_text),
            "pages": len(pages),
            "metrics": results,
        }, ensure_ascii=False),
    }


# ─── Скачивание ────────────────────────────────────────────────────────────────

def _download_file(url: str):
    """Скачивает файл по URL с поддержкой редиректов и куки."""
    opener = urllib.request.build_opener(
        urllib.request.HTTPRedirectHandler(),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/octet-stream,*/*",
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": "https://www.e-disclosure.ru/",
    })
    try:
        with opener.open(req, timeout=25) as resp:
            cl = int(resp.headers.get("Content-Length") or 0)
            if cl > MAX_FILE_SIZE:
                return None, f"Файл слишком большой ({cl // 1024 // 1024} МБ > 20 МБ)"
            data = resp.read(MAX_FILE_SIZE + 1)
            if len(data) > MAX_FILE_SIZE:
                return None, "Файл превышает лимит 20 МБ"
            return data, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: не удалось скачать документ"
    except Exception as e:
        return None, f"Ошибка загрузки: {str(e)}"


# ─── PDF через pdfminer.six ────────────────────────────────────────────────────

def _extract_pdf(data: bytes) -> list:
    """
    Извлекает текст постранично через pdfminer.six.
    Возвращает список строк (одна строка = одна страница PDF).
    """
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer, LTAnno, LTChar, LTTextLine

    pages_text = []
    try:
        for page_layout in extract_pages(io.BytesIO(data)):
            page_lines = []
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    for text_line in element:
                        if isinstance(text_line, LTTextLine):
                            line_text = text_line.get_text().strip()
                            if line_text:
                                page_lines.append(line_text)
            if page_lines:
                pages_text.append("\n".join(page_lines))
    except Exception as e:
        # Фоллбэк: попробуем extract_text целиком
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(io.BytesIO(data))
            if text and text.strip():
                # Делим на страницы по символу \x0c (form feed)
                pages_text = [p.strip() for p in text.split("\x0c") if p.strip()]
        except Exception:
            pass

    return pages_text


# ─── XLSX через openpyxl ───────────────────────────────────────────────────────

def _extract_xlsx(data: bytes) -> list:
    """
    Читает XLSX через openpyxl.
    Возвращает список «страниц» (листов), каждый лист — строки вида «метка\tзначение».
    Сохраняем пространственную связь: текст в левой ячейке строки + число в правой.
    """
    import openpyxl

    pages = []
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        for sheet in wb.worksheets[:8]:
            rows_text = []
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c).strip() if c is not None else "" for c in row]
                # Убираем полностью пустые строки
                non_empty = [c for c in cells if c and c != "None"]
                if not non_empty:
                    continue
                rows_text.append("\t".join(cells))
            if rows_text:
                pages.append("\n".join(rows_text))
        wb.close()
    except Exception:
        pass

    return pages


# ─── Поиск показателей ─────────────────────────────────────────────────────────

def _find_metrics(full_text: str, pages: list, metrics: list, year: str) -> list:
    """Ищет каждый показатель в тексте, возвращает список результатов."""
    results = []
    full_lower = full_text.lower()

    for metric in metrics:
        value, unit, context = _search_one(full_text, full_lower, metric, year)
        results.append({
            "name": metric,
            "value": value,
            "unit": unit,
            "period": year,
            "source": "Документ" if value else "Не найдено",
            "context": context[:250] if context else "",
            "found": bool(value),
        })

    return results


def _search_one(text: str, text_lower: str, metric: str, year: str):
    """
    Ищет значение одного показателя.
    Стратегия:
      1. Ищем строку содержащую название (или синоним) показателя
      2. В этой строке и следующих 3 строках ищем число
      3. Определяем единицу измерения из контекста
    """
    metric_lower = metric.lower().strip()
    all_terms = [metric_lower] + _synonyms(metric_lower)

    lines = text.split("\n")
    lines_lower = text_lower.split("\n")

    for term in all_terms:
        for i, line_l in enumerate(lines_lower):
            if term not in line_l:
                continue

            # Окно: текущая строка + 3 следующих
            window_lines = lines[i: i + 4]
            window = "\n".join(window_lines)
            window_lower = window.lower()

            value = _extract_number(window)
            if value:
                unit = _detect_unit(window_lower, text_lower)
                context = window.strip()
                return value, unit, context

    # Фоллбэк: ищем в сплошном тексте по позиции
    for term in all_terms:
        idx = text_lower.find(term)
        if idx == -1:
            continue
        context_raw = text[max(0, idx - 30): idx + 300]
        value = _extract_number(context_raw)
        if value:
            unit = _detect_unit(context_raw.lower(), text_lower)
            return value, unit, context_raw.strip()

    return "", "", ""


def _extract_number(text: str) -> str:
    """
    Извлекает первое «финансовое» число из текста.
    Порядок приоритета: большие числа с разделителями → дробные → целые.
    """
    patterns = [
        r'(-?\d{1,3}(?:[\s\u00a0]\d{3})+(?:[,\.]\d+)?)',  # 1 234 567 или 1 234 567,8
        r'(-?\d{1,3}(?:[,]\d{3})+(?:\.\d+)?)',              # 1,234,567.8
        r'(-?\d+[,\.]\d+)',                                   # 27,4 или 27.4
        r'(-?\d{4,})',                                        # любое число ≥ 4 цифр
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip()
            # Убираем лишние пробелы-разделители тысяч
            normalized = re.sub(r'[\s\u00a0](?=\d{3})', '', raw)
            return normalized
    return ""


def _detect_unit(context_lower: str, full_lower: str = "") -> str:
    """Определяет единицу измерения из ближайшего контекста."""
    checks = [
        (["млрд руб", "billion rub", "млрд. руб"],      "млрд руб."),
        (["млн руб", "million rub", "тыс. руб", "млн."], "млн руб."),
        ([" % ", "процент", "percent", "margin"],        "%"),
        (["чел.", "человек", "сотрудник", "работник", "employee", "headcount"], "чел."),
        (["тонн", "тыс. тонн", "млн тонн", "баррел"],   "тонн"),
        (["долл", "usd", "$"],                            "USD"),
        (["евро", "eur", "€"],                            "EUR"),
        (["млн", "million"],                              "млн руб."),
        (["млрд", "billion"],                             "млрд руб."),
        (["руб.", "рублей", "rub"],                       "руб."),
        ([" x ", "раз"],                                  "x"),
    ]
    for keywords, unit in checks:
        if any(kw in context_lower for kw in keywords):
            return unit
    # Ищем единицу в шапке документа
    for keywords, unit in checks:
        if full_lower and any(kw in full_lower[:2000] for kw in keywords):
            return unit
    return "руб."


def _synonyms(term: str) -> list:
    """Словарь синонимов и английских эквивалентов финансовых показателей."""
    MAP = {
        "выручка":                    ["revenue", "revenues", "net revenue", "total revenue", "net sales", "продажи"],
        "ebitda":                     ["ebitda", "ebidta", "прибыль до вычета процентов"],
        "ebit":                       ["ebit", "operating profit", "operating income", "операционная прибыль", "прибыль от операций"],
        "операционная прибыль":       ["operating profit", "operating income", "ebit", "прибыль от операционной деятельности"],
        "чистая прибыль":             ["net income", "net profit", "net earnings", "profit for the year", "profit for the period", "прибыль за период", "прибыль за год"],
        "валовая прибыль":            ["gross profit", "gross margin"],
        "совокупные активы":          ["total assets", "assets", "итого активы", "активы всего"],
        "собственный капитал":        ["equity", "shareholders equity", "shareholders' equity", "total equity", "капитал акционеров", "итого капитал"],
        "долгосрочный долг":          ["long-term debt", "long term borrowings", "non-current borrowings", "долгосрочные займы", "долгосрочные кредиты"],
        "краткосрочный долг":         ["short-term debt", "current borrowings", "краткосрочные займы"],
        "чистый долг":                ["net debt", "чистая задолженность"],
        "капитальные затраты":        ["capex", "capital expenditure", "capital expenditures", "purchases of property", "приобретение основных средств", "капитальные вложения"],
        "capex":                      ["capital expenditure", "capital expenditures", "capex", "капитальные затраты", "капитальные вложения"],
        "операционный денежный поток":["operating cash flow", "cash from operations", "net cash from operating", "денежные средства от операционной деятельности"],
        "свободный денежный поток":   ["free cash flow", "fcf"],
        "рентабельность":             ["margin", "profitability", "return"],
        "долг ebitda":                ["net debt/ebitda", "debt/ebitda", "leverage"],
        "чистый долг ebitda":         ["net debt/ebitda", "net debt to ebitda"],
        "дивиденды":                  ["dividends", "dividend", "дивиденды на акцию", "dps"],
        "численность":                ["employees", "headcount", "number of employees", "staff", "персонал", "сотрудников", "работников"],
        "добыча":                     ["production", "output", "объём добычи"],
    }

    result = []
    for key, vals in MAP.items():
        if key in term or term in key or any(v in term or term in v for v in vals):
            result.extend(vals)
            result.append(key)

    return list(dict.fromkeys(result))  # дедупликация с сохранением порядка


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _err(status: int, msg: str) -> dict:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS,
        "body": json.dumps({"error": msg}, ensure_ascii=False),
    }