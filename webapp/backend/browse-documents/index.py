"""Диагностика окружения."""
import json
import sys
import os
import shutil
import glob
import subprocess

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Content-Type": "application/json",
}


def handler(event: dict, context) -> dict:
    """Проверяет что доступно в окружении функции."""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": CORS_HEADERS, "body": ""}

    info = {"python": sys.version, "tmp_free_mb": 0, "browsers": {}}

    try:
        st = os.statvfs("/tmp")
        info["tmp_free_mb"] = round(st.f_bavail * st.f_frsize / 1024 / 1024)
    except Exception:
        pass

    for b in ["chromium", "chromium-browser", "google-chrome", "chrome", "firefox"]:
        p = shutil.which(b)
        if p:
            info["browsers"][b] = p

    info["browsers_fs"] = (
        glob.glob("/usr/bin/chrom*") +
        glob.glob("/opt/google/*") +
        glob.glob("/tmp/ms-playwright/*/chrome-linux/chrome")
    )

    try:
        import playwright
        info["playwright"] = getattr(playwright, "__version__", "ok")
    except ImportError:
        info["playwright"] = "not installed"

    try:
        out = subprocess.check_output(
            [sys.executable, "-m", "pip", "list", "--format=columns"],
            timeout=5, stderr=subprocess.DEVNULL
        ).decode()
        info["packages"] = [l.split()[0] for l in out.splitlines()[2:] if l]
    except Exception as e:
        info["packages_error"] = str(e)

    return {
        "statusCode": 200,
        "headers": CORS_HEADERS,
        "body": json.dumps(info, ensure_ascii=False),
    }
