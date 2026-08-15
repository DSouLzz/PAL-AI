import html
import re
import time
from urllib.parse import quote_plus, urlparse

import requests


TRUSTED_DOMAINS = (
    "palworldgame.com",
    "paldb.cc",
    "palworld.gg",
    "game8.co",
    "ign.com",
    "reddit.com",
)

RESEARCH_TRIGGERS = (
    "best pal", "best pals", "best team", "best combination", "best combinations",
    "best breeding", "breeding combination", "breeding combinations", "breed ",
    "best passive", "best passives", "best build", "best worker", "best workers",
    "boss counter", "counter for", "strongest pal", "meta", "current patch",
    "where can i find", "where do i find", "where to find", "best base pal",
)

_CACHE = {}


def should_research(text):
    q = str(text).lower().strip()
    return any(trigger in q for trigger in RESEARCH_TRIGGERS)


def _clean_html(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _allowed(url):
    try:
        host = urlparse(url).hostname or ""
        host = host.lower()
        return any(host == d or host.endswith("." + d) for d in TRUSTED_DOMAINS)
    except Exception:
        return False


def web_search(query, max_results=6, timeout=8):
    """Lightweight on-demand web search. No browser, no background polling."""
    key = query.strip().lower()
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < 900:
        return cached[1]

    headers = {"User-Agent": "Mozilla/5.0 PAL-AI/0.8.5"}
    url = "https://html.duckduckgo.com/html/?q=" + quote_plus("Palworld " + query)
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    page = response.text

    # DuckDuckGo HTML results expose result links and snippets without JavaScript.
    link_pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S
    )
    snippet_pattern = re.compile(
        r'class="result__snippet"[^>]*>(.*?)</(?:a|div)>', re.I | re.S
    )
    links = link_pattern.findall(page)
    snippets = snippet_pattern.findall(page)

    results = []
    for i, (href, title) in enumerate(links):
        # DDG redirect links contain the destination in uddg=.
        m = re.search(r"[?&]uddg=([^&]+)", href)
        if m:
            from urllib.parse import unquote
            href = unquote(m.group(1))
        if not href.startswith("http") or not _allowed(href):
            continue
        snippet = _clean_html(snippets[i]) if i < len(snippets) else ""
        results.append({
            "title": _clean_html(title)[:160],
            "url": href,
            "snippet": snippet[:500],
        })
        if len(results) >= max_results:
            break

    _CACHE[key] = (time.time(), results)
    return results


def format_research(results):
    if not results:
        return "No trusted current web results were found. Say that current online verification was unavailable."
    lines = ["CURRENT PALWORLD WEB RESEARCH (fresh search; use this over stale memory when they conflict):"]
    for n, item in enumerate(results, 1):
        lines.append(f"{n}. {item['title']}\n   {item['snippet']}\n   Source: {item['url']}")
    lines.append(
        "Compare the sources. Do not claim a single subjective 'best' without explaining the criterion. "
        "For breeding, prefer exact current combinations supported by the search results. "
        "Mention uncertainty when sources disagree. End with a short Sources section containing the URLs you actually used."
    )
    return "\n".join(lines)


def apply_online_research(pal_ai):
    old_ask = pal_ai.App.ask

    def ask(self, text):
        cfg = pal_ai.CONFIG.get("online_research", {})
        if not cfg.get("enabled", True) or not should_research(text):
            return old_ask(self, text)

        # Keep network lookup on a worker thread so the GUI never freezes.
        if self.busy:
            return
        self.busy = True
        self._say_ui("You", text)
        self.db.add_message("user", text)
        self.set_status("Researching current Palworld data online...")

        def worker():
            try:
                results = web_search(
                    text,
                    max_results=int(cfg.get("max_results", 6)),
                    timeout=int(cfg.get("timeout_seconds", 8)),
                )
                research = format_research(results)
                memories = self.db.search_memories(text, 4)
                knowledge = self.kb.search(text, pal_ai.CONFIG.get("knowledge_results", 5))
                context = []
                if memories:
                    context.append("PLAYER MEMORY:\n- " + "\n- ".join(memories))
                if knowledge:
                    context.append("LOCAL KNOWLEDGE:\n" + "\n".join(
                        f"[{fn}] {chunk}" for _, fn, chunk in knowledge
                    ))
                context.append(research)

                perf = pal_ai.CONFIG.get("gaming_performance", {})
                history_limit = int(perf.get("max_history_messages", 8)) if perf.get("enabled", True) else int(pal_ai.CONFIG.get("max_history_messages", 12))
                recent = self.db.recent_messages(history_limit)
                messages = [{"role": "system", "content": pal_ai.SYSTEM_PROMPT + "\n\n" + "\n\n".join(context)}]
                messages += recent
                answer = self.ollama.chat(pal_ai.CONFIG["model"], messages)
                self.db.add_message("assistant", answer)
                self.turn_count += 1
                self.root.after(0, lambda answer=answer: self._finish_answer(answer))
            except Exception as exc:
                msg = f"Online research failed: {exc}. I can still answer from local knowledge if you ask again with Online Research disabled."
                self.root.after(0, lambda msg=msg: self._finish_error(msg))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    pal_ai.App.ask = ask
