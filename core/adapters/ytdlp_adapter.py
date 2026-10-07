"""core/adapters/ytdlp_adapter.py — Safe yt-dlp Metadata Extraction & Media Downloader Adapter."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from typing import Any, Dict, Optional

from core.adapters.base import BaseToolAdapter
from core.fetch.normalizer import FetchResult

logger = logging.getLogger("muse.adapters.ytdlp")


class YtDlpAdapter(BaseToolAdapter):
    """Safe adapter for yt-dlp media extraction and downloading."""

    name = "yt-dlp"

    def __init__(self, binary: Optional[str] = None):
        self.binary = binary

    async def fetch(self, url: str, options: Optional[Dict[str, Any]] = None) -> FetchResult:
        """Extract metadata (title, description, duration, formats) without downloading video."""
        t0 = time.perf_counter()
        meta = await self.extract_metadata(url)
        t_total = (time.perf_counter() - t0) * 1000.0

        if meta.get("ok"):
            title = meta.get("title", "Media Metadata")
            desc = meta.get("description", "")
            summary = f"# {title}\nDuration: {meta.get('duration')}s | Uploader: {meta.get('uploader')}\n\n{desc}"
            return FetchResult(
                success=True,
                tool=self.name,
                url=url,
                title=title,
                content=summary,
                text=summary,
                metadata=meta,
                timing={"total_ms": round(t_total, 2)},
                status_code=200,
            )
        return FetchResult(
            success=False,
            tool=self.name,
            url=url,
            error=meta.get("error", "Metadata extraction failed"),
            timing={"total_ms": round(t_total, 2)},
        )

    async def extract_metadata(self, url: str) -> Dict[str, Any]:
        """Extract video metadata as structured dict."""
        try:
            # Check Python package first
            try:
                import yt_dlp
                ydl_opts = {"skip_download": True, "quiet": True, "no_warnings": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    return {
                        "ok": True,
                        "title": info.get("title"),
                        "description": info.get("description"),
                        "duration": info.get("duration"),
                        "uploader": info.get("uploader"),
                        "view_count": info.get("view_count"),
                        "thumbnail": info.get("thumbnail"),
                    }
            except ImportError:
                pass

            # Fallback to CLI binary
            bin_name = self.binary or "yt-dlp"
            cmd = [bin_name, "--dump-json", "--skip-download", url]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20.0)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                return {
                    "ok": True,
                    "title": data.get("title"),
                    "description": data.get("description"),
                    "duration": data.get("duration"),
                    "uploader": data.get("uploader"),
                    "view_count": data.get("view_count"),
                    "thumbnail": data.get("thumbnail"),
                }
            return {"ok": False, "error": res.stderr.strip()[:150] or "yt-dlp exited with error"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def execute_task(self, task_type: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute validated download task."""
        if task_type == "download":
            url = params.get("url")
            output_dir = params.get("output_dir") or os.path.join(os.path.expanduser("~"), "Downloads")
            os.makedirs(output_dir, exist_ok=True)
            out_tmpl = os.path.join(output_dir, "%(title)s.%(ext)s")

            try:
                try:
                    import yt_dlp
                    ydl_opts = {"outtmpl": out_tmpl, "quiet": True}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                        return {"ok": True, "output_dir": output_dir}
                except ImportError:
                    pass

                bin_name = self.binary or "yt-dlp"
                cmd = [bin_name, "-o", out_tmpl, url]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=120.0)
                return {"ok": res.returncode == 0, "output_dir": output_dir, "error": res.stderr if res.returncode != 0 else None}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        raise NotImplementedError(f"Task '{task_type}' not supported by YtDlpAdapter")
