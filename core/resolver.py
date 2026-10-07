"""core/resolver.py — Universal Three-Layer Element Resolver for Muse 3.0."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from core.interfaces import BaseBrowserBackend, BaseElementResolver
from core.types import ElementBounds, ElementQuery, ResolutionMethod, ResolvedElement

# Single-roundtrip browser script for Layer 1 (Deterministic) and Layer 2 (Semantic)
INPAGE_RESOLVER_SCRIPT = r"""
(query) => {
    function getBounds(el) {
        const r = el.getBoundingClientRect();
        return {
            x: Math.round(r.x),
            y: Math.round(r.y),
            w: Math.round(r.width),
            h: Math.round(r.height),
            visible: r.width > 0 && r.height > 0
        };
    }

    function isVisible(el) {
        if (!el) return false;
        if (typeof el.checkVisibility === 'function') {
            return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
        }
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
    }

    function getImplicitRole(el) {
        const tag = el.tagName.toLowerCase();
        if (tag === 'button') return 'button';
        if (tag === 'a' && el.hasAttribute('href')) return 'link';
        if (tag === 'input') {
            const t = el.type ? el.type.toLowerCase() : 'text';
            if (['button', 'submit', 'reset'].includes(t)) return 'button';
            if (['checkbox', 'radio'].includes(t)) return t;
            return 'textbox';
        }
        if (tag === 'textarea') return 'textbox';
        if (tag === 'select') return 'combobox';
        return el.getAttribute('role') || '';
    }

    function getAccessibleName(el) {
        let name = el.getAttribute('aria-label') || '';
        if (!name && el.getAttribute('aria-labelledby')) {
            const labelEl = document.getElementById(el.getAttribute('aria-labelledby'));
            if (labelEl) name = labelEl.textContent || '';
        }
        if (!name && el.labels && el.labels.length > 0) {
            name = el.labels[0].textContent || '';
        }
        if (!name) {
            name = el.placeholder || el.value || el.title || el.textContent || '';
        }
        return name.replace(/\s+/g, ' ').trim();
    }

    // Traverse DOM including open shadow roots
    function collectInteractive(root) {
        const results = [];
        const sel = 'a, button, input, select, textarea, [role], [onclick], [tabindex]:not([tabindex="-1"])';
        const els = root.querySelectorAll(sel);
        for (const el of els) {
            results.push(el);
            if (el.shadowRoot) {
                results.push(...collectInteractive(el.shadowRoot));
            }
        }
        // Also check if root itself has child elements with shadowRoot
        for (const child of root.querySelectorAll('*')) {
            if (child.shadowRoot && !child.matches(sel)) {
                results.push(...collectInteractive(child.shadowRoot));
            }
        }
        return results;
    }

    // ── LAYER 1: DETERMINISTIC ──────────────────────────────────────
    if (query.selector) {
        try {
            const el = document.querySelector(query.selector);
            if (el && isVisible(el)) {
                const b = getBounds(el);
                return {
                    found: true,
                    method: 'deterministic',
                    confidence: 1.0,
                    tag: el.tagName.toLowerCase(),
                    role: getImplicitRole(el),
                    name: getAccessibleName(el),
                    selector: query.selector,
                    bounds: b,
                    in_shadow_dom: false
                };
            }
        } catch (_) {}
    }

    // Check data-testid or exact ID if provided in query
    if (query.name && (query.name.startsWith('#') || query.name.startsWith('.'))) {
        try {
            const el = document.querySelector(query.name);
            if (el && isVisible(el)) {
                const b = getBounds(el);
                return {
                    found: true,
                    method: 'deterministic',
                    confidence: 1.0,
                    tag: el.tagName.toLowerCase(),
                    role: getImplicitRole(el),
                    name: getAccessibleName(el),
                    selector: query.name,
                    bounds: b,
                    in_shadow_dom: false
                };
            }
        } catch (_) {}
    }

    // ── LAYER 2: SEMANTIC & ACCESSIBILITY ───────────────────────────
    const all = collectInteractive(document);
    let bestMatch = null;
    let highestScore = 0;

    const targetRole = (query.role || '').toLowerCase();
    const targetText = (query.text || query.name || query.aria_label || '').toLowerCase().trim();

    for (const el of all) {
        if (!isVisible(el)) continue;
        const b = getBounds(el);
        if (!b.visible) continue;

        const role = getImplicitRole(el).toLowerCase();
        const accName = getAccessibleName(el).toLowerCase();

        let score = 0;

        // Role match bonus
        if (targetRole && role === targetRole) {
            score += 0.35;
        }

        // Text / Name match
        if (targetText && accName) {
            if (accName === targetText) {
                score += 0.65; // Exact name match
            } else if (accName.includes(targetText) || targetText.includes(accName)) {
                score += 0.50; // Substring match
            } else {
                // Word-level overlap
                const targetWords = targetText.split(/\s+/);
                const matchedWords = targetWords.filter(w => accName.includes(w));
                if (matchedWords.length > 0) {
                    score += 0.25 * (matchedWords.length / targetWords.length);
                }
            }
        }

        // Tag matching if query tag specified
        if (query.tag && el.tagName.toLowerCase() === query.tag.toLowerCase()) {
            score += 0.15;
        }

        if (score > highestScore) {
            highestScore = score;
            const inShadow = el.getRootNode() instanceof ShadowRoot;
            bestMatch = {
                found: true,
                method: 'semantic',
                confidence: Math.min(1.0, Math.round(score * 100) / 100),
                tag: el.tagName.toLowerCase(),
                role: role,
                name: getAccessibleName(el),
                selector: el.id ? '#' + el.id : el.tagName.toLowerCase(),
                bounds: b,
                in_shadow_dom: inShadow
            };
        }
    }

    if (bestMatch && highestScore >= 0.50) {
        return bestMatch;
    }

    // Not found deterministically or semantically
    return { found: false, candidate_count: all.length };
}
"""


import urllib.parse
from core.interfaces import BaseBrowserBackend, BaseElementResolver, BaseSelectorCache


class ElementResolver(BaseElementResolver):
    """Three-layer resolver implementing Learned Cache -> Deterministic -> Semantic -> Vision."""

    def __init__(
        self,
        vision_fallback_enabled: bool = False,
        cache: Optional[BaseSelectorCache] = None,
    ):
        self.vision_fallback_enabled = vision_fallback_enabled
        self.cache = cache

    async def resolve(
        self, backend: BaseBrowserBackend, tab_id: str, query: ElementQuery
    ) -> Optional[ResolvedElement]:
        """Resolves target element using Cache -> Layer 1 -> Layer 2 -> Layer 3."""
        url = ""
        domain = "local"
        path = "/"
        try:
            url = await backend.get_url(tab_id)
            if url:
                parsed = urllib.parse.urlparse(url)
                domain = parsed.netloc or "local"
                path = parsed.path or "/"
        except Exception:
            pass

        intent = query.description or query.name or query.text or query.aria_label or query.selector

        # Layer 0: Learned Cache Lookup
        if self.cache and intent:
            cached_sel = self.cache.get(domain, path, intent)
            if cached_sel:
                try:
                    check_expr = f"""(() => {{
                        const el = document.querySelector({json.dumps(cached_sel)});
                        if (!el) return null;
                        const r = el.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) return null;
                        return {{
                            found: true,
                            tag: el.tagName.toLowerCase(),
                            role: el.getAttribute('role') || '',
                            name: (el.getAttribute('aria-label') || el.innerText || el.textContent || '').trim().slice(0, 80),
                            bounds: {{x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}},
                            selector: {json.dumps(cached_sel)}
                        }};
                    }})()"""
                    c_res = await backend.evaluate(tab_id, check_expr)
                    if isinstance(c_res, dict) and c_res.get("found"):
                        b = c_res["bounds"]
                        bounds = ElementBounds(x=b["x"], y=b["y"], w=b["w"], h=b["h"])
                        # Boost success counter
                        self.cache.put(domain, path, intent, cached_sel, "cache", 1.0)
                        return ResolvedElement(
                            ref=cached_sel,
                            tag=c_res.get("tag", ""),
                            role=c_res.get("role", ""),
                            name=c_res.get("name", ""),
                            bounds=bounds,
                            selector=cached_sel,
                            method=ResolutionMethod.CACHE,
                            confidence=1.0,
                        )
                    else:
                        # Cached selector failed, record failure to decay / trigger self-healing
                        self.cache.record_failure(domain, path, intent)
                except Exception:
                    self.cache.record_failure(domain, path, intent)

        # 1. Prepare query payload
        query_dict = {
            "selector": query.selector or "",
            "role": query.role or "",
            "name": query.name or query.description or "",
            "text": query.text or "",
            "aria_label": query.aria_label or "",
        }

        # 2. Execute in-page resolver script for Layer 1 & Layer 2 in a single evaluation
        expr = f"({INPAGE_RESOLVER_SCRIPT})({json.dumps(query_dict)})"
        res = await backend.evaluate(tab_id, expr)
        print("Resolver JS result:", res)

        if isinstance(res, dict) and res.get("found"):
            b = res["bounds"]
            bounds = ElementBounds(x=b["x"], y=b["y"], w=b["w"], h=b["h"])
            method = ResolutionMethod.DETERMINISTIC if res["method"] == "deterministic" else ResolutionMethod.SEMANTIC
            resolved_sel = res.get("selector", "")

            # Self-healing / Cache storage
            if self.cache and intent and resolved_sel:
                self.cache.put(domain, path, intent, resolved_sel, method.value, float(res.get("confidence", 0.9)))

            return ResolvedElement(
                ref=resolved_sel or "el",
                tag=res.get("tag", ""),
                role=res.get("role", ""),
                name=res.get("name", ""),
                bounds=bounds,
                selector=resolved_sel,
                method=method,
                confidence=float(res.get("confidence", 0.9)),
                in_shadow_dom=bool(res.get("in_shadow_dom", False)),
            )

        # 3. Layer 3: Vision / Set-of-Marks Fallback (only if enabled and L1/L2 failed)
        if self.vision_fallback_enabled:
            return await self._resolve_via_vision(backend, tab_id, query)

        return None

    async def _resolve_via_vision(
        self, backend: BaseBrowserBackend, tab_id: str, query: ElementQuery
    ) -> Optional[ResolvedElement]:
        """Layer 3: Vision / SoM overlay fallback when DOM and A11y matching fail."""
        try:
            # Check if backend supports som_mark
            marks_res = await backend.evaluate(
                tab_id,
                """
                () => {
                    const marks = [];
                    let i = 0;
                    for (const el of document.querySelectorAll('button, a, input, select, [role]')) {
                        const r = el.getBoundingClientRect();
                        if (r.width > 2 && r.height > 2) {
                            marks.push({
                                mark: i++,
                                x: Math.round(r.x + r.width / 2),
                                y: Math.round(r.y + r.height / 2),
                                w: Math.round(r.width),
                                h: Math.round(r.height),
                                tag: el.tagName.toLowerCase(),
                                name: (el.textContent || el.value || '').trim().slice(0, 40)
                            });
                        }
                        if (i >= 50) break;
                    }
                    return marks;
                }
                """
            )
            if marks_res and isinstance(marks_res, list) and len(marks_res) > 0:
                # Pick best mark matching query text
                target_str = (query.text or query.name or "").lower()
                for m in marks_res:
                    if target_str and target_str in m.get("name", "").lower():
                        bounds = ElementBounds(
                            x=m["x"] - (m["w"] // 2),
                            y=m["y"] - (m["h"] // 2),
                            w=m["w"],
                            h=m["h"],
                        )
                        return ResolvedElement(
                            ref=f"som_{m['mark']}",
                            tag=m.get("tag", "div"),
                            role="mark",
                            name=m.get("name", ""),
                            bounds=bounds,
                            selector=f"[som-mark='{m['mark']}']",
                            method=ResolutionMethod.VISION,
                            confidence=0.75,
                        )
        except Exception:
            pass
        return None
