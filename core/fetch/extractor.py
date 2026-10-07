"""core/fetch/extractor.py — Clean Text, Markdown & Link Extractor without DOM Bloat."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin


class SimpleContentExtractor(HTMLParser):
    """Zero-dependency HTML to structured markdown/text and link extractor."""

    def __init__(self, base_url: str = ""):
        super().__init__()
        self.base_url = base_url
        self.title = ""
        self._in_title = False
        self._in_script_or_style = False
        self.text_chunks: List[str] = []
        self.links: List[Dict[str, str]] = []
        self.images: List[Dict[str, str]] = []
        self._curr_link_href = ""
        self._curr_link_text: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag.lower() in ("script", "style", "noscript", "svg"):
            self._in_script_or_style = True
        elif tag.lower() == "title":
            self._in_title = True
        elif tag.lower() == "a":
            href = attr_dict.get("href", "")
            if href and not href.startswith(("javascript:", "#")):
                full_href = urljoin(self.base_url, href) if self.base_url else href
                self._curr_link_href = full_href
                self._curr_link_text = []
        elif tag.lower() == "img":
            src = attr_dict.get("src", "")
            alt = attr_dict.get("alt", "")
            if src:
                full_src = urljoin(self.base_url, src) if self.base_url else src
                self.images.append({"src": full_src, "alt": alt})
        elif tag.lower() in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.text_chunks.append("\n")

    def handle_endtag(self, tag: str):
        if tag.lower() in ("script", "style", "noscript", "svg"):
            self._in_script_or_style = False
        elif tag.lower() == "title":
            self._in_title = False
        elif tag.lower() == "a":
            if self._curr_link_href:
                link_text = " ".join("".join(self._curr_link_text).split()).strip()
                if link_text:
                    self.links.append({"text": link_text, "href": self._curr_link_href})
            self._curr_link_href = ""
            self._curr_link_text = []
        elif tag.lower() in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"):
            self.text_chunks.append("\n")

    def handle_data(self, data: str):
        if self._in_script_or_style:
            return
        if self._in_title:
            self.title += data.strip()
            return

        text = unescape(data)
        if self._curr_link_href:
            self._curr_link_text.append(text)
        self.text_chunks.append(text)

    @classmethod
    def extract(cls, html: str, base_url: str = "") -> Dict[str, Any]:
        """Extract title, clean text, links, and images from HTML."""
        parser = cls(base_url=base_url)
        try:
            parser.feed(html)
        except Exception:
            pass

        raw_text = "".join(parser.text_chunks)
        # Normalize whitespace
        cleaned = re.sub(r"[ \t]+", " ", raw_text)
        cleaned = re.sub(r"\n\s*\n+", "\n\n", cleaned).strip()

        # Deduplicate links preserving order
        seen_links = set()
        unique_links = []
        for l in parser.links:
            key = (l["text"], l["href"])
            if key not in seen_links:
                seen_links.add(key)
                unique_links.append(l)

        return {
            "title": parser.title.strip(),
            "text": cleaned,
            "links": unique_links[:100],  # top 100 relevant links
            "images": parser.images[:50],
        }
