"""core/page_model.py — Zero-Shot Structured Page Modeler for Muse 3.0.

Traverses DOM, open Shadow DOM roots, nested iframes, dialogs, forms,
and interactive controls without dumping raw HTML into AI agent contexts.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.types import ElementBounds, PageModel, ResolutionMethod, ResolvedElement

logger = logging.getLogger("muse.core.page_model")

# Universal JS evaluation script for fast single-roundtrip DOM extraction
PAGE_MODEL_SCRIPT = r"""
(() => {
    const MAX_ELEMENTS = 300;
    const elements = [];
    const dialogs = [];
    const forms = [];
    const iframes = [];
    let refCounter = 0;

    function getBounds(el) {
        try {
            const r = el.getBoundingClientRect();
            return {
                x: Math.round(r.x),
                y: Math.round(r.y),
                w: Math.round(r.width),
                h: Math.round(r.height),
                top: Math.round(r.top),
                left: Math.round(r.left),
                bottom: Math.round(r.bottom),
                right: Math.round(r.right)
            };
        } catch (_) {
            return { x: 0, y: 0, w: 0, h: 0, top: 0, left: 0, bottom: 0, right: 0 };
        }
    }

    function isVisible(el, rect) {
        if (!rect || rect.w <= 0 || rect.h <= 0) return false;
        try {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                return false;
            }
        } catch (_) {}
        return true;
    }

    function getAccessibleName(el) {
        return (
            el.getAttribute('aria-label') ||
            el.getAttribute('title') ||
            el.getAttribute('placeholder') ||
            (el.labels && el.labels[0] ? el.labels[0].textContent : '') ||
            el.getAttribute('alt') ||
            (el.tagName === 'INPUT' && (el.type === 'submit' || el.type === 'button') ? el.value : '') ||
            el.innerText ||
            el.textContent ||
            el.value ||
            ''
        ).trim().replace(/\s+/g, ' ').slice(0, 100);
    }

    function walk(node, ctx) {
        if (!node || elements.length >= MAX_ELEMENTS) return;

        if (node.nodeType === Node.ELEMENT_NODE) {
            const tag = (node.tagName || '').toLowerCase();
            const role = (node.getAttribute ? node.getAttribute('role') : '') || '';

            // 1. Detect Dialogs & Modals
            if (tag === 'dialog' || role === 'dialog' || node.getAttribute('aria-modal') === 'true') {
                const isOpen = node.hasAttribute('open') || role === 'dialog';
                dialogs.push({
                    tag: tag,
                    id: node.id || '',
                    role: role,
                    open: isOpen,
                    name: getAccessibleName(node)
                });
            }

            // 2. Detect Forms
            if (tag === 'form') {
                forms.push({
                    id: node.id || '',
                    action: node.getAttribute('action') || '',
                    method: (node.getAttribute('method') || 'GET').toUpperCase()
                });
            }

            // 3. Detect Interactive Elements
            const isContentEditable = node.isContentEditable || node.getAttribute('contenteditable') === 'true';
            const isInteractive = (
                tag === 'button' ||
                tag === 'a' ||
                tag === 'input' ||
                tag === 'select' ||
                tag === 'textarea' ||
                tag === 'summary' ||
                isContentEditable ||
                ['button', 'link', 'checkbox', 'radio', 'tab', 'menuitem', 'switch', 'textbox', 'combobox'].includes(role) ||
                node.hasAttribute('onclick') ||
                (node.getAttribute('tabindex') && parseInt(node.getAttribute('tabindex'), 10) >= 0)
            );

            if (isInteractive) {
                const r = getBounds(node);
                if (isVisible(node, r)) {
                    refCounter++;
                    const prefix = ctx.framePrefix ? ctx.framePrefix + '_' : '';
                    const ref = prefix + 'e' + refCounter;

                    const finalX = r.x + ctx.offsetX;
                    const finalY = r.y + ctx.offsetY;
                    const inViewport = (
                        r.bottom > 0 && r.right > 0 &&
                        r.top < window.innerHeight && r.left < window.innerWidth
                    );

                    elements.push({
                        ref: ref,
                        tag: isContentEditable ? 'contenteditable' : tag,
                        role: role || (tag === 'button' ? 'button' : (tag === 'a' ? 'link' : (tag === 'input' ? (node.type || 'text') : ''))),
                        name: getAccessibleName(node),
                        value: (node.value !== undefined ? String(node.value) : (isContentEditable ? node.textContent.trim().slice(0, 100) : '')),
                        x: finalX,
                        y: finalY,
                        w: r.w,
                        h: r.h,
                        in_viewport: inViewport,
                        disabled: !!node.disabled || node.getAttribute('aria-disabled') === 'true',
                        in_shadow_dom: ctx.inShadow,
                        iframe_path: ctx.framePath.length ? ctx.framePath.join(' -> ') : null,
                        selector: node.id ? '#' + node.id : '',
                        attributes: {
                            id: node.id || '',
                            class: node.className && typeof node.className === 'string' ? node.className.trim() : '',
                            type: node.type || '',
                            placeholder: node.placeholder || '',
                            href: node.href || ''
                        }
                    });
                }
            }

            // 4. Traverse Iframes (if accessible)
            if (tag === 'iframe') {
                const r = getBounds(node);
                const iframeEntry = {
                    id: node.id || '',
                    name: node.name || '',
                    src: node.src || '',
                    bounds: r,
                    accessible: false
                };
                try {
                    if (node.contentDocument && node.contentDocument.body) {
                        iframeEntry.accessible = true;
                        iframes.push(iframeEntry);
                        const frameId = node.id || node.name || `iframe_${iframes.length}`;
                        const frameCtx = {
                            inShadow: ctx.inShadow,
                            framePath: [...ctx.framePath, frameId],
                            framePrefix: `f${iframes.length}`,
                            offsetX: ctx.offsetX + r.x,
                            offsetY: ctx.offsetY + r.y
                        };
                        walk(node.contentDocument.body, frameCtx);
                    } else {
                        iframes.push(iframeEntry);
                    }
                } catch (_) {
                    // Cross-origin iframe
                    iframes.push(iframeEntry);
                }
            }

            // 5. Traverse Open Shadow Roots
            if (node.shadowRoot) {
                const shadowCtx = {
                    ...ctx,
                    inShadow: true
                };
                walk(node.shadowRoot, shadowCtx);
            }
        }

        // Recursively traverse child elements
        let child = node.firstElementChild;
        while (child && elements.length < MAX_ELEMENTS) {
            walk(child, ctx);
            child = child.nextElementSibling;
        }
    }

    const root = document.body || document.documentElement;
    walk(root, {
        inShadow: false,
        framePath: [],
        framePrefix: '',
        offsetX: 0,
        offsetY: 0
    });

    const docEl = document.documentElement || {};
    return {
        url: location.href,
        title: document.title,
        viewport: {
            width: window.innerWidth || 0,
            height: window.innerHeight || 0
        },
        scroll: {
            x: window.scrollX || docEl.scrollLeft || 0,
            y: window.scrollY || docEl.scrollTop || 0,
            width: docEl.scrollWidth || 0,
            height: docEl.scrollHeight || 0
        },
        elements: elements,
        dialogs: dialogs,
        forms: forms,
        iframes: iframes
    };
})();
"""


class PageModeler:
    """Universal high-performance zero-shot DOM page modeler."""

    @classmethod
    async def build(cls, backend: Any, tab_id: str) -> PageModel:
        """Extract structured PageModel using universal injected JS walker."""
        start_time = time.perf_counter()

        script = PAGE_MODEL_SCRIPT.strip()
        try:
            raw = await backend.evaluate(tab_id, script)
        except Exception as exc:
            logger.warning("Failed evaluating PageModel script: %s", exc)
            return PageModel(
                url=await backend.get_url(tab_id),
                title=await backend.get_title(tab_id),
                summary=f"Page model extraction error: {exc}",
            )

        if not isinstance(raw, dict):
            return PageModel(
                url=await backend.get_url(tab_id),
                title=await backend.get_title(tab_id),
                summary="Invalid page model output from browser.",
            )

        elements: List[ResolvedElement] = []
        buttons: List[Dict[str, Any]] = []
        inputs: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []

        for e in raw.get("elements", []):
            bounds = ElementBounds(
                x=e.get("x", 0),
                y=e.get("y", 0),
                w=e.get("w", 0),
                h=e.get("h", 0),
            )
            attrs = e.get("attributes", {})
            if e.get("iframe_path"):
                attrs["iframe_path"] = e["iframe_path"]
            if e.get("value"):
                attrs["value"] = e["value"]

            tag = e.get("tag", "")
            role = e.get("role", "")
            name = e.get("name", "")

            re = ResolvedElement(
                ref=e.get("ref", ""),
                tag=tag,
                role=role,
                name=name,
                bounds=bounds,
                selector=e.get("selector") or f"[ref='{e.get('ref')}']",
                method=ResolutionMethod.DETERMINISTIC,
                confidence=1.0,
                attributes=attrs,
                in_shadow_dom=bool(e.get("in_shadow_dom")),
            )
            elements.append(re)

            if tag == "button" or role == "button":
                buttons.append({"ref": re.ref, "name": re.name, "id": attrs.get("id", "")})
            elif tag in ("input", "textarea", "select", "contenteditable") or role in ("textbox", "searchbox", "combobox"):
                inputs.append({"ref": re.ref, "name": re.name, "type": attrs.get("type", tag)})
            elif tag == "a" or role == "link":
                links.append({"ref": re.ref, "name": re.name, "href": attrs.get("href", "")})

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        model = PageModel(
            url=raw.get("url") or await backend.get_url(tab_id),
            title=raw.get("title") or await backend.get_title(tab_id),
            interactive_elements=elements,
            buttons=buttons,
            inputs=inputs,
            links=links,
            forms=raw.get("forms", []),
            iframes=raw.get("iframes", []),
            dialogs=raw.get("dialogs", []),
            viewport=raw.get("viewport", {}),
            scroll_info=raw.get("scroll", {}),
            summary=(
                f"{len(elements)} interactive elements "
                f"({len(buttons)} btns, {len(inputs)} inputs, {len(links)} links, "
                f"{len(raw.get('dialogs', []))} modals, {len(raw.get('iframes', []))} iframes) "
                f"in {duration_ms:.1f}ms"
            ),
        )
        return model
