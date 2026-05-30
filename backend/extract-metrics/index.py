"""
Загрузка документа (PDF или XLSX) по URL и извлечение финансовых показателей.
Поддерживает: PDF (текстовый), XLSX/XLS.
"""
import json
import os
import re
import io
import urllib.request
import urllib.parse
import base64


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

    doc_url = body.get("url", "").strip()
    metrics = body.get("metrics", [])
    company = body.get("company", "")
    year = body.get("year", "")

    if not doc_url:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "URL документа обязателен"}, ensure_ascii=False),
        }

    if not metrics:
        return {
            "statusCode": 400,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Список показателей пуст"}, ensure_ascii=False),
        }

    metrics = metrics[:20]

    # Определяем тип файла
    url_lower = doc_url.lower().split("?")[0]
    if url_lower.endswith(".xlsx") or url_lower.endswith(".xls"):
        file_type = "xlsx"
    elif url_lower.endswith(".zip") or url_lower.endswith(".rar"):
        file_type = "archive"
    else:
        file_type = "pdf"

    # Скачиваем файл
    file_data, error = _download_file(doc_url)
    if error:
        return {
            "statusCode": 422,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": error}, ensure_ascii=False),
        }

    # Извлекаем текст
    if file_type == "xlsx":
        text = _extract_text_xlsx(file_data)
    elif file_type == "pdf":
        text = _extract_text_pdf(file_data)
    else:
        text = ""

    if not text:
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps({
                "metrics": [],
                "raw_text_length": 0,
                "warning": "Не удалось извлечь текст из документа. Возможно, PDF является сканом.",
            }, ensure_ascii=False),
        }

    # Ищем показатели в тексте
    results = _find_metrics_in_text(text, metrics, year)

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps({
            "company": company,
            "year": year,
            "doc_url": doc_url,
            "file_type": file_type,
            "raw_text_length": len(text),
            "metrics": results,
        }, ensure_ascii=False),
    }


def _download_file(url: str):
    """Скачивает файл по URL с поддержкой редиректов. Возвращает (bytes, error_string)."""
    import http.cookiejar
    opener = urllib.request.build_opener(
        urllib.request.HTTPRedirectHandler(),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/pdf,application/octet-stream,*/*",
            "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
            "Referer": "https://www.e-disclosure.ru/",
        }
    )
    try:
        with opener.open(req, timeout=25) as resp:
            size = int(resp.headers.get("Content-Length") or 0)
            if size > MAX_FILE_SIZE:
                return None, f"Файл слишком большой ({size // 1024 // 1024} МБ > 20 МБ)"
            data = resp.read(MAX_FILE_SIZE + 1)
            if len(data) > MAX_FILE_SIZE:
                return None, "Файл превышает лимит 20 МБ"
            return data, None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: не удалось скачать документ"
    except Exception as e:
        return None, f"Ошибка загрузки: {str(e)}"


def _extract_text_pdf(data: bytes) -> str:
    """Извлечение текста из PDF без сторонних библиотек (базовый парсер)."""
    try:
        # Пробуем через встроенные средства — ищем потоки текста в PDF
        text_parts = []
        content = data.decode("latin-1", errors="replace")

        # Извлекаем содержимое BT...ET блоков
        bt_et = re.findall(r'BT(.*?)ET', content, re.DOTALL)
        for block in bt_et:
            # Ищем строки в скобках (PDF text strings)
            strings = re.findall(r'\(([^)]{1,300})\)', block)
            for s in strings:
                cleaned = _clean_pdf_string(s)
                if cleaned:
                    text_parts.append(cleaned)

        # Также ищем Unicode-строки
        unicode_strings = re.findall(r'<([0-9A-Fa-f]{4,})>', content)
        for hex_str in unicode_strings[:500]:
            try:
                if len(hex_str) % 4 == 0:
                    chars = [chr(int(hex_str[i:i+4], 16)) for i in range(0, len(hex_str), 4)]
                    decoded = "".join(chars)
                    if any(c.isalpha() for c in decoded):
                        text_parts.append(decoded)
            except Exception:
                pass

        return " ".join(text_parts)
    except Exception:
        return ""


def _clean_pdf_string(s: str) -> str:
    """Очистка PDF строки от служебных символов."""
    s = s.replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
    s = re.sub(r'\\[0-9]{3}', ' ', s)
    s = re.sub(r'\\(.)', r'\1', s)
    s = re.sub(r'[^\x20-\x7E\u0400-\u04FF\u0020]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s if len(s) > 1 else ""


def _extract_text_xlsx(data: bytes) -> str:
    """Извлечение текста из XLSX (ZIP с XML внутри)."""
    import zipfile
    text_parts = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Читаем shared strings
            shared_strings = []
            if "xl/sharedStrings.xml" in zf.namelist():
                ss_xml = zf.read("xl/sharedStrings.xml").decode("utf-8", errors="replace")
                shared_strings = re.findall(r'<t[^>]*>([^<]+)</t>', ss_xml)

            # Читаем листы
            sheets = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet")]
            for sheet_name in sheets[:5]:
                sheet_xml = zf.read(sheet_name).decode("utf-8", errors="replace")
                # Ячейки с индексами на shared strings
                cells_s = re.findall(r'<c[^>]+t="s"[^>]*><v>(\d+)</v>', sheet_xml)
                for idx in cells_s:
                    i = int(idx)
                    if i < len(shared_strings):
                        text_parts.append(shared_strings[i])
                # Inline строки
                inline = re.findall(r'<is><t>([^<]+)</t></is>', sheet_xml)
                text_parts.extend(inline)
                # Числовые значения
                nums = re.findall(r'<v>(\d[\d\s,\.]+)</v>', sheet_xml)
                text_parts.extend(nums[:2000])

        return " | ".join(text_parts)
    except Exception:
        return ""


def _find_metrics_in_text(text: str, metrics: list, year: str) -> list:
    """Поиск каждого показателя в тексте документа."""
    results = []
    text_lower = text.lower()
    lines = text.split("\n") if "\n" in text else text.split("|")

    for metric in metrics:
        metric_lower = metric.lower().strip()
        value, unit, found_context = _search_metric_value(text, text_lower, lines, metric_lower, year)
        results.append({
            "name": metric,
            "value": value,
            "unit": unit,
            "period": year,
            "source": "Документ",
            "context": found_context[:200] if found_context else "",
            "found": bool(value),
        })

    return results


def _search_metric_value(text: str, text_lower: str, lines: list, metric_lower: str, year: str):
    """Поиск значения показателя в тексте."""

    # Синонимы и аббревиатуры
    synonyms = _get_synonyms(metric_lower)
    all_terms = [metric_lower] + synonyms

    for term in all_terms:
        # Ищем строку содержащую термин
        idx = text_lower.find(term)
        if idx == -1:
            continue

        # Берём контекст вокруг найденного места
        start = max(0, idx - 50)
        end = min(len(text), idx + 300)
        context = text[start:end]

        # Ищем числа в контексте
        # Форматы: 1 234 567, 1,234,567, 1234567, 27.4, 1.8
        number_patterns = [
            r'(\d{1,3}(?:[\s\u00a0]\d{3})+(?:[,\.]\d+)?)',  # 1 234 567
            r'(\d{1,3}(?:,\d{3})+(?:\.\d+)?)',               # 1,234,567
            r'(\d+[,\.]\d+)',                                  # 27.4 или 27,4
            r'(\d{4,})',                                       # просто большое число
        ]

        for pat in number_patterns:
            nums = re.findall(pat, context)
            if nums:
                raw = nums[0].strip()
                # Нормализуем: пробелы-разделители тысяч убираем
                normalized = re.sub(r'[\s\u00a0]', '', raw)
                unit = _detect_unit(context)
                return normalized, unit, context.strip()

    return "", "", ""


def _detect_unit(context: str) -> str:
    """Определение единицы измерения из контекста."""
    ctx_lower = context.lower()
    if "млрд" in ctx_lower or "billion" in ctx_lower:
        return "млрд руб."
    if "млн" in ctx_lower or "million" in ctx_lower or "тыс." in ctx_lower:
        return "млн руб."
    if "%" in ctx_lower or "процент" in ctx_lower:
        return "%"
    if "чел." in ctx_lower or "сотрудник" in ctx_lower or "работник" in ctx_lower:
        return "чел."
    if "тонн" in ctx_lower:
        return "тонн"
    if "руб." in ctx_lower or "рублей" in ctx_lower:
        return "руб."
    return "руб."


def _get_synonyms(term: str) -> list:
    """Словарь синонимов финансовых показателей."""
    synonyms_map = {
        "выручка": ["revenue", "revenues", "net revenue", "total revenue", "продажи", "объём продаж"],
        "ebitda": ["ebitda", "ebit da", "прибыль до вычета"],
        "ebit": ["operating profit", "операционная прибыль", "прибыль от операционной деятельности"],
        "чистая прибыль": ["net income", "net profit", "profit for the year", "прибыль за период"],
        "активы": ["total assets", "совокупные активы", "итого активы"],
        "капитал": ["equity", "shareholders equity", "собственный капитал", "капитал акционеров"],
        "долг": ["debt", "borrowings", "long-term debt", "долгосрочный долг", "кредиты и займы"],
        "capex": ["capital expenditure", "капитальные затраты", "приобретение основных средств"],
        "денежный поток": ["cash flow", "operating cash flow", "операционный денежный поток"],
        "сотрудники": ["employees", "headcount", "численность", "персонал", "работников"],
        "дивиденды": ["dividends", "дивиденды на акцию"],
        "рентабельность": ["margin", "profitability", "доходность"],
    }

    result = []
    for key, vals in synonyms_map.items():
        if key in term or term in key:
            result.extend(vals)
        for v in vals:
            if v in term or term in v:
                result.extend(vals)
                break

    return list(set(result))