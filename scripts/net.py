"""HTTP sem dependências externas (urllib) + cache em disco.

- `fetch`: GET com retentativas e backoff (429/5xx/rede).
- `get_json`: GET JSON com cache por TTL; se a fonte cair, usa o cache vencido.
- `download`: baixa arquivos grandes (zips da CVM) em streaming, com cache.

Tokens vão sempre em cabeçalho (nunca na URL) e não aparecem em logs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
import zipfile

from config import CACHE_DIR

UA = "Mozilla/5.0 (compatible; agente-bolsa/2.0; +https://github.com/arturmilk/agente-bolsa)"
HTTP_DIR = os.path.join(CACHE_DIR, "http")
_PERMANENTES = (400, 401, 402, 403, 404, 410)


def log(msg):
    print(f"[agente-bolsa] {msg}", file=sys.stderr, flush=True)


def _safe(url):
    return re.sub(r"(token=)[^&]+", r"\1***", url)


def fetch(url, headers=None, timeout=30, retries=4) -> bytes:
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"}
    if headers:
        h.update(headers)
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in _PERMANENTES:
                raise
            wait = min(30, 2 ** (attempt + 1)) if e.code == 429 else 1.5 * (attempt + 1)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            wait = 1.5 * (attempt + 1)
        if attempt < retries - 1:
            time.sleep(wait)
    raise RuntimeError(f"falha ao acessar {_safe(url)}: {last}")


def _cache_file(url):
    slug = re.sub(r"[^A-Za-z0-9]+", "_", _safe(url).split("//", 1)[-1])[:60]
    return os.path.join(HTTP_DIR, f"{slug}_{hashlib.sha1(url.encode()).hexdigest()[:12]}.json")


def get_json(url, ttl=1800, headers=None, timeout=30, retries=4):
    """GET JSON com cache em disco. Se a fonte falhar, devolve o cache vencido."""
    path = _cache_file(url)
    fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl
    if fresh:
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    try:
        data = json.loads(fetch(url, headers=headers, timeout=timeout, retries=retries))
    except Exception:
        if os.path.exists(path):
            log(f"fonte indisponível, usando cache antigo: {_safe(url)[:90]}")
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        raise
    os.makedirs(HTTP_DIR, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)
    return data


def get_text(url, ttl=1800, headers=None, timeout=30, retries=3) -> bytes:
    """GET bruto (RSS/XML) com cache em disco."""
    path = _cache_file(url)[:-5] + ".bin"
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl:
        with open(path, "rb") as f:
            return f.read()
    try:
        data = fetch(url, headers=headers, timeout=timeout, retries=retries)
    except Exception:
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        raise
    os.makedirs(HTTP_DIR, exist_ok=True)
    with open(path + ".tmp", "wb") as f:
        f.write(data)
    os.replace(path + ".tmp", path)
    return data


def download(url, dest, ttl=None, timeout=300) -> str:
    """Baixa `url` para `dest` (streaming). Reusa o arquivo se ainda vale (ttl s)."""
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        if ttl is None or (time.time() - os.path.getmtime(dest)) < ttl:
            return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    last = None
    for attempt in range(3):
        try:
            log(f"baixando {os.path.basename(dest)} ...")
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            if dest.endswith(".zip") and not zipfile.is_zipfile(tmp):
                raise RuntimeError("arquivo baixado não é um zip válido")
            os.replace(tmp, dest)
            return dest
        except urllib.error.HTTPError as e:
            last = e
            if e.code in _PERMANENTES:
                break
        except Exception as e:
            last = e
        time.sleep(2 * (attempt + 1))
    if os.path.exists(tmp):
        os.remove(tmp)
    if os.path.exists(dest):
        log(f"falha ao atualizar {os.path.basename(dest)} ({last}); usando versão em cache")
        return dest
    raise RuntimeError(f"falha ao baixar {_safe(url)}: {last}")
