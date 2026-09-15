"""Static /packages tree with directory listings install.bash can scrape.

Starlette ``StaticFiles(html=True)`` only serves ``index.html``. It does
**not** generate nginx-style autoindex. ``html=False`` therefore 404s
every ``GET .../openvox-agent/`` even when the .deb files exist.

install.bash historically walked those directories for hrefs. Listings
here are relative ``<a href="...">`` so the existing sed parser works.
"""
from __future__ import annotations

import html
import stat
from pathlib import Path
from typing import Iterable, List, Union
from urllib.parse import quote

import anyio
from fastapi.responses import HTMLResponse
from starlette.staticfiles import StaticFiles


def listing_html(names: Iterable[str]) -> str:
    """Minimal HTML directory index. Hrefs are relative and URL-encoded."""
    rows: List[str] = []
    for raw in names:
        name = str(raw)
        if not name or name in (".", "..") or "/" in name or "\\" in name:
            continue
        href = quote(name, safe="-_.")
        rows.append(f'<a href="{href}">{html.escape(name)}</a><br>\n')
    body = "".join(rows) if rows else "<!-- empty -->\n"
    return (
        "<!DOCTYPE html><html><head><title>Index</title></head><body>\n"
        f"{body}</body></html>\n"
    )


class PackageStaticFiles(StaticFiles):
    """StaticFiles plus autoindex for directories (no index.html required)."""

    async def get_response(self, path: str, scope):
        # Starlette 1.6 lookup_path is sync; get_response must not await it.
        full_path, stat_result = await anyio.to_thread.run_sync(self.lookup_path, path)
        if stat_result is not None and stat.S_ISDIR(stat_result.st_mode):
            names = await anyio.to_thread.run_sync(self._dir_names, full_path)
            return HTMLResponse(listing_html(names))
        return await super().get_response(path, scope)

    @staticmethod
    def _dir_names(full_path: Union[str, Path]) -> List[str]:
        try:
            return sorted(p.name for p in Path(full_path).iterdir())
        except OSError:
            return []
