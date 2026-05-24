# confluence_kb.py
# ══════════════════════════════════════════════════════════════════════════════
#  KNOWLEDGE BASE MODULE  —  Confluence Cloud Integration
#  v11 Changes:
#   • Selectable/copyable text in all panels (SelectableText widget)
#   • Visible vertical scrollbars for keyboard/non-mouse navigation
#   • Wider Related Sources panel (280px), narrower reader to compensate
#   • Precise AI responses with author attribution ("According to [Author]...")
#   • No storytelling/padding in AI answers — concise, direct, cited
# ══════════════════════════════════════════════════════════════════════════════
import http.client
import json
import re
import ssl
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox
import urllib.parse
import base64
import datetime
from settings_store import load_settings

# ══════════════════════════════════════════════════════════════════════════════
#  CLEAN WHITE PALETTE
# ══════════════════════════════════════════════════════════════════════════════
BG              = "#FFFFFF"
BG_SUBTLE       = "#F8F8F8"
BG_PANEL        = "#F4F4F4"
BG_INPUT        = "#FFFFFF"

ACCENT          = "#A0522D"
ACCENT_HOVER    = "#7B3F22"
ACCENT_LIGHT    = "#FDF3EC"
ACCENT_MUTED    = "#D4956A"

TEXT_PRIMARY    = "#111111"
TEXT_SECONDARY  = "#555555"
TEXT_MUTED      = "#888888"
TEXT_GHOST      = "#BBBBBB"
TEXT_ON_ACCENT  = "#FFFFFF"

BORDER          = "#E5E5E5"
BORDER_MID      = "#CCCCCC"
BORDER_FOCUS    = "#A0522D"

SUCCESS         = "#16A34A"
WARNING         = "#D97706"
ERROR           = "#DC2626"
INFO            = "#2563EB"

# ── Typography ────────────────────────────────────────────────────────────────
FONT_DISPLAY      = ("Georgia",       13, "bold")
FONT_HEADING      = ("Georgia",       11, "bold")
FONT_SUBHEADING   = ("Segoe UI",      10, "bold")
FONT_BODY         = ("Segoe UI",       9)
FONT_BODY_LARGE   = ("Georgia",       10)
FONT_MONO         = ("Consolas",       9)
FONT_MONO_SM      = ("Consolas",       8)
FONT_LABEL        = ("Segoe UI",       7, "bold")
FONT_BADGE        = ("Segoe UI",       8, "italic")
FONT_BTN          = ("Segoe UI",       9, "bold")
FONT_BTN_SM       = ("Segoe UI",       8, "bold")
FONT_READER_TITLE = ("Georgia",       16, "bold")
FONT_READER_META  = ("Segoe UI",       8, "italic")
FONT_READER_BODY  = ("Georgia",       11)
FONT_READER_SEC   = ("Segoe UI",      10, "bold")
FONT_CHAT_USER    = ("Segoe UI",       9)
FONT_CHAT_AI      = ("Georgia",       10)
FONT_CHAT_META    = ("Segoe UI",       7, "italic")

SCOPED_TOKEN_MIN_LEN = 100

# ── Token budget constants ────────────────────────────────────────────────────
MAX_PAGES_IN_PROMPT   = 4
BODY_CHARS_PER_PAGE   = 800
SCENARIO_MAX_CHARS    = 600

# ── Chat-specific context constants ───────────────────────────────────────────
CHAT_BODY_CHARS       = 2500
CHAT_MAX_PAGES        = 6
CHAT_PASSAGE_CHARS    = 1800
CHAT_MAX_TOKENS       = 1000
CHAT_HISTORY_TURNS    = 6

# ── Three-column layout widths (pixels) ───────────────────────────────────────
#  LEFT  : KB reader — flexible, takes remaining space
#  CENTER: AI Chat   — fixed width
#  RIGHT : Related Sources — wider (was 200, now 280)
COL_CHAT_WIDTH    = 480
COL_SOURCES_WIDTH = 280   # widened from 200

# ── Stop-words ────────────────────────────────────────────────────────────────
_STOP = {
    "a","an","the","is","are","was","were","be","been","being",
    "have","has","had","do","does","did","will","would","could",
    "should","may","might","shall","can","need","dare","ought",
    "used","in","on","at","to","for","of","with","by","from",
    "up","about","into","through","during","what","which","who",
    "whom","this","that","these","those","am","and","or","but",
    "if","then","because","as","until","while","how","when",
    "where","why","all","both","each","few","more","most","other",
    "some","such","no","nor","not","only","own","same","so","than",
    "too","very","just","any","there","their","they","we","our",
    "i","my","me","us","you","your","he","she","his","her","it","its",
}


# ══════════════════════════════════════════════════════════════════════════════
#  URL PATTERN  — matches http/https URLs anywhere in text
# ══════════════════════════════════════════════════════════════════════════════
_URL_RE = re.compile(
    r'(https?://[^\s\]\)\'"<>]+)',
    re.IGNORECASE
)


# ══════════════════════════════════════════════════════════════════════════════
#  SELECTABLE TEXT WIDGET  — with automatic clickable hyperlinks
#
#  Any http/https URL found in the text is:
#    • Coloured ACCENT (brown) and underlined
#    • Cursor changes to "hand2" on hover
#    • Single-click opens the URL in the default browser
#    • Right-click menu gains "Open Link" when cursor is over a link
#  All non-URL text remains normally selectable and copyable.
# ══════════════════════════════════════════════════════════════════════════════
class SelectableText(tk.Text):
    """A read-only, selectable text widget that looks like a Label,
    with automatic clickable hyperlinks for any http/https URLs."""

    _LINK_TAG_PREFIX = "link_"

    def __init__(self, parent, text="", font=FONT_BODY, bg=BG,
                 fg=TEXT_PRIMARY, wraplength=None, justify="left",
                 anchor="nw", pady=0, padx=0, **kwargs):
        super().__init__(
            parent,
            font=font,
            bg=bg,
            fg=fg,
            bd=0,
            relief="flat",
            highlightthickness=0,
            wrap="word",
            cursor="xterm",
            padx=padx,
            pady=pady,
            state="normal",
            **kwargs
        )
        # Hyperlink style tag (shared across all instances)
        self.tag_configure(
            "hyperlink",
            foreground=ACCENT,
            underline=True,
        )
        self.tag_configure(
            "hyperlink_hover",
            foreground=ACCENT_HOVER,
            underline=True,
        )

        self._link_urls: dict = {}   # tag_name -> url

        if text:
            self._insert_with_links(text)
        self.config(state="disabled")

        # Right-click context menu
        self.bind("<Button-3>", self._show_context_menu)
        self._ctx_menu = tk.Menu(self, tearoff=0)
        self._open_link_item_idx = None   # dynamic menu item index

    # ── Insert text, tagging URLs as hyperlinks ────────────────────────────────
    def _insert_with_links(self, text: str):
        """Split text on URLs; insert plain runs normally, URLs with link tag."""
        parts = _URL_RE.split(text)   # odd indices are URL groups
        link_counter = getattr(self, "_link_counter", 0)
        for i, part in enumerate(parts):
            if not part:
                continue
            if i % 2 == 1:
                # This part is a URL
                tag_name = f"{self._LINK_TAG_PREFIX}{link_counter}"
                link_counter += 1
                url = part.strip()
                self._link_urls[tag_name] = url
                # Configure individual tag (needed for per-link hover binding)
                self.tag_configure(tag_name, foreground=ACCENT, underline=True)
                start_idx = self.index(tk.INSERT)
                self.insert(tk.INSERT, url, ("hyperlink", tag_name))
                end_idx = self.index(tk.INSERT)
                # Hover: darken on enter, restore on leave
                self.tag_bind(tag_name, "<Enter>",
                    lambda e, tn=tag_name: self._on_link_enter(tn))
                self.tag_bind(tag_name, "<Leave>",
                    lambda e, tn=tag_name: self._on_link_leave(tn))
                # Click: open browser
                self.tag_bind(tag_name, "<Button-1>",
                    lambda e, u=url: self._open_url(u))
                # Cursor change
                self.tag_bind(tag_name, "<Enter>",
                    lambda e, tn=tag_name: (
                        self._on_link_enter(tn),
                        self.config(cursor="hand2")
                    ), add=True)
                self.tag_bind(tag_name, "<Leave>",
                    lambda e, tn=tag_name: (
                        self._on_link_leave(tn),
                        self.config(cursor="xterm")
                    ), add=True)
            else:
                self.insert(tk.INSERT, part)
        self._link_counter = link_counter

    def _on_link_enter(self, tag_name: str):
        self.tag_configure(tag_name, foreground=ACCENT_HOVER)

    def _on_link_leave(self, tag_name: str):
        self.tag_configure(tag_name, foreground=ACCENT)

    @staticmethod
    def _open_url(url: str):
        try:
            webbrowser.open(url)
        except Exception:
            pass

    # ── Public API ─────────────────────────────────────────────────────────────
    def set_text(self, text: str):
        self.config(state="normal")
        self.delete("1.0", tk.END)
        self._link_urls.clear()
        self._link_counter = 0
        self._insert_with_links(text)
        self.config(state="disabled")

    # ── Context menu ───────────────────────────────────────────────────────────
    def _show_context_menu(self, event):
        menu = tk.Menu(self, tearoff=0)
        # Detect if cursor is over a link tag
        clicked_url = self._url_at(event.x, event.y)
        if clicked_url:
            menu.add_command(
                label=f"Open Link",
                command=lambda u=clicked_url: self._open_url(u))
            menu.add_command(
                label="Copy Link",
                command=lambda u=clicked_url: (
                    self.clipboard_clear(), self.clipboard_append(u)))
            menu.add_separator()
        try:
            menu.add_command(label="Copy Selection", command=self._copy_selection)
        except Exception:
            pass
        menu.add_command(label="Select All", command=self._select_all)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _url_at(self, x: int, y: int) -> str:
        """Return the URL under pixel (x, y), or empty string if none."""
        try:
            idx = self.index(f"@{x},{y}")
            tags = self.tag_names(idx)
            for t in tags:
                if t in self._link_urls:
                    return self._link_urls[t]
        except Exception:
            pass
        return ""

    def _copy_selection(self):
        try:
            sel = self.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.clipboard_clear()
            self.clipboard_append(sel)
        except tk.TclError:
            pass

    def _select_all(self):
        self.tag_add(tk.SEL, "1.0", tk.END)
        self.mark_set(tk.INSERT, "1.0")
        self.see(tk.INSERT)

    def auto_height(self):
        """Call after packing to shrink widget to content height."""
        self.update_idletasks()
        lines = int(self.index(tk.END).split(".")[0]) - 1
        self.config(height=max(1, lines))


# ══════════════════════════════════════════════════════════════════════════════
#  KEYWORD EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════
def _extract_keywords(query: str) -> list:
    words = re.findall(r"[A-Za-z0-9]+", query)
    normalised = []
    for w in words:
        normalised.append(w if (w.isupper() and len(w) >= 2) else w.lower())
    keywords = [w for w in normalised if w.lower() not in _STOP and len(w) >= 2]
    seen, unique = set(), []
    for k in keywords:
        if k.lower() not in seen:
            seen.add(k.lower())
            unique.append(k)
    return unique


# ══════════════════════════════════════════════════════════════════════════════
#  PASSAGE SCORING
# ══════════════════════════════════════════════════════════════════════════════
def _score_passage(passage: str, keywords: list) -> float:
    if not passage or not keywords:
        return 0.0
    lower = passage.lower()
    hits  = sum(1 for kw in keywords if kw.lower() in lower)
    return hits / len(keywords)


def _extract_best_passages(page_body: str, question: str,
                            max_chars: int = CHAT_PASSAGE_CHARS) -> str:
    keywords = _extract_keywords(question)
    if not keywords:
        return page_body[:max_chars]

    paragraphs = [p.strip() for p in re.split(r"\n{1,}", page_body) if p.strip()]
    if not paragraphs:
        return page_body[:max_chars]

    scored = [(p, _score_passage(p, keywords)) for p in paragraphs]
    scored.sort(key=lambda x: -x[1])

    collected, total = [], 0
    for para, score in scored:
        if score <= 0:
            break
        if total + len(para) > max_chars:
            remaining = max_chars - total
            if remaining > 80:
                collected.append(para[:remaining] + "…")
                total = max_chars
            break
        collected.append(para)
        total += len(para)
        if total >= max_chars:
            break

    if not collected:
        for para, _ in [(p, s) for p, s in scored]:
            if total + len(para) > max_chars:
                remaining = max_chars - total
                if remaining > 80:
                    collected.append(para[:remaining] + "…")
                break
            collected.append(para)
            total += len(para)
            if total >= max_chars:
                break

    return "\n\n".join(collected)


# ══════════════════════════════════════════════════════════════════════════════
#  HTML -> plain text
# ══════════════════════════════════════════════════════════════════════════════
def _strip_html(html: str) -> str:
    html = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<(p|br|div|li|h[1-6]|tr)[^>]*>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    for ent, ch in [("&amp;","&"),("&lt;","<"),("&gt;",">"),
                    ("&nbsp;"," "),("&quot;",'"'),("&#39;","'")]:
        html = html.replace(ent, ch)
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


# ══════════════════════════════════════════════════════════════════════════════
#  MARKDOWN TABLE PARSER
# ══════════════════════════════════════════════════════════════════════════════
def _parse_md_tables(text: str):
    table_re = re.compile(
        r'((?:\|[^\n]+\|\n)+\|[-| :]+\|\n(?:\|[^\n]+\|\n?)*)',
        re.MULTILINE
    )
    tables = []
    def replacer(m):
        raw   = m.group(0)
        lines = [l.strip() for l in raw.strip().split('\n') if l.strip()]
        if len(lines) < 2:
            return raw
        headers = [c.strip() for c in lines[0].strip('|').split('|')]
        rows    = [
            [c.strip() for c in line.strip('|').split('|')]
            for line in lines[2:]
        ]
        idx = len(tables)
        tables.append({'headers': headers, 'rows': rows})
        return f'\n<<TABLE_{idx}>>\n'
    cleaned = table_re.sub(replacer, text)
    return cleaned, tables


# ══════════════════════════════════════════════════════════════════════════════
#  LOW-LEVEL HTTPS
# ══════════════════════════════════════════════════════════════════════════════
def _https_get(host: str, path: str, headers: dict, params: dict = None) -> tuple:
    if params:
        path = path + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    ctx = ssl.create_default_context()
    try:
        conn = http.client.HTTPSConnection(host, timeout=25, context=ctx)
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        raw  = resp.read().decode("utf-8", errors="replace")
        return resp.status, raw
    except OSError as exc:
        raise ConnectionError(f"Cannot reach '{host}': {exc}")
    finally:
        try: conn.close()
        except Exception: pass


# ══════════════════════════════════════════════════════════════════════════════
#  CLOUD ID
# ══════════════════════════════════════════════════════════════════════════════
def _fetch_cloud_id(site_host: str, auth_hdr: dict) -> str:
    ctx = ssl.create_default_context()

    for attempt, (host, path, use_auth) in enumerate([
        (site_host,        "/wiki/rest/api/settings/systemInfo", True),
        (site_host,        "/wiki/rest/api/space?limit=1",       True),
        ("api.atlassian.com", "/oauth/token/accessible-resources", True),
        (site_host,        "/_edge/tenant_info",                 False),
    ]):
        try:
            conn = http.client.HTTPSConnection(host, timeout=25, context=ctx)
            hdrs = {**(auth_hdr if use_auth else {}), "Accept": "application/json"}
            conn.request("GET", path, headers=hdrs)
            resp = conn.getresponse()
            raw  = resp.read().decode("utf-8", errors="replace")
            conn.close()

            cid = resp.getheader("X-Confluence-Cloud-Id", "")
            if cid:
                return cid

            if resp.status == 200:
                data = json.loads(raw)
                if isinstance(data, list) and data:
                    for r in data:
                        if site_host in r.get("url", ""):
                            return r["id"]
                    return data[0]["id"]
                cid = data.get("cloudId", "") or data.get("cloud_id", "")
                if cid:
                    return cid
        except Exception:
            pass

    raise ConnectionError(
        f"Could not determine the Atlassian Cloud ID for '{site_host}'.\n\n"
        "Possible causes:\n"
        "  * Wrong Base URL\n"
        "  * Network / firewall blocking outbound HTTPS to atlassian.net\n"
        "  * The site requires VPN access\n"
        "  * Invalid or expired API token"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  CONFLUENCE CLIENT
# ══════════════════════════════════════════════════════════════════════════════
class ConfluenceClient:
    def __init__(self, base_url: str, username: str, api_token: str):
        parsed           = urllib.parse.urlparse(base_url.strip())
        self._site_host  = parsed.netloc
        self._origin     = f"https://{self._site_host}"
        m = re.search(r"/spaces/([^/?#]+)", parsed.path)
        self.space_key   = m.group(1) if m else None
        u = username.strip()
        t = api_token.strip()
        self._username   = u
        self._token_len  = len(t)
        self._token_prev = (t[:4] + "..." + t[-4:]) if len(t) >= 8 else "***"
        encoded          = base64.b64encode(f"{u}:{t}".encode()).decode("ascii")
        self._auth_hdr   = {"Authorization": f"Basic {encoded}",
                            "Accept": "application/json"}
        self._api_host   = None
        self._api_prefix = None
        self._token_type = None
        self._cloud_id   = None

    def _resolve_endpoint(self) -> None:
        if self._token_len >= SCOPED_TOKEN_MIN_LEN:
            cloud_id         = _fetch_cloud_id(self._site_host, self._auth_hdr)
            self._cloud_id   = cloud_id
            self._api_host   = "api.atlassian.com"
            self._api_prefix = f"/ex/confluence/{cloud_id}"
            self._token_type = "scoped"
        else:
            self._api_host   = self._site_host
            self._api_prefix = ""
            self._token_type = "classic"

    def _get(self, api_path: str, params: dict = None) -> dict:
        if self._api_host is None:
            self._resolve_endpoint()
        full_path = self._api_prefix + api_path
        status, raw = _https_get(self._api_host, full_path, self._auth_hdr, params)
        if status == 401:
            raise ConnectionError(
                f"401 Unauthorized\n\n"
                f"  Host       : {self._api_host}\n"
                f"  Token type : {self._token_type} ({self._token_len} chars)\n"
                f"  Username   : {self._username}\n"
                f"  Token      : {self._token_prev}\n\n"
                "Check your email, token, and that the token has Confluence read scopes."
            )
        if status == 403:
            raise ConnectionError(
                "403 Forbidden -- authenticated but no permission to read this space.\n"
                f"Ask your admin to grant 'Space Viewer' on {self.space_key or 'the space'}."
            )
        if status not in (200, 201):
            raise ConnectionError(f"Confluence API {status}: {raw[:300]}")
        return json.loads(raw)

    def test_connection(self) -> str:
        self._resolve_endpoint()
        data         = self._get("/wiki/rest/api/user/current")
        display_name = data.get("displayName", "Unknown")
        email        = data.get("email", self._username)
        return (
            f"Authenticated as: {display_name} ({email})\n"
            f"  Token type  : {self._token_type} ({self._token_len} chars)\n"
            + (f"  Cloud ID    : {self._cloud_id}\n" if self._cloud_id else "")
            + f"  Space key   : {self.space_key or 'NOT FOUND -- check Base URL'}"
        )

    def search_pages(self, query: str, limit: int = 10) -> list:
        space_clause = f' AND space.key="{self.space_key}"' if self.space_key else ""
        keywords     = _extract_keywords(query)
        collected: dict = {}
        hit_count: dict = {}

        def _run_cql(cql: str, lim: int = limit) -> list:
            try:
                data = self._get("/wiki/rest/api/search", {
                    "cql": cql, "limit": lim,
                    "expand": "content.body.storage,content.space,content.version,content.history.lastUpdated",
                    "includeArchivedSpaces": "false",
                })
                return data.get("results", [])
            except Exception:
                return []

        def _ingest(results: list):
            for item in results:
                content  = item.get("content", {})
                page_id  = content.get("id", "")
                if not page_id:
                    continue
                title    = content.get("title", "Untitled")
                sp_key   = content.get("space", {}).get("key") or self.space_key or ""
                url      = f"{self._origin}/wiki/spaces/{sp_key}/pages/{page_id}"
                raw_html = content.get("body", {}).get("storage", {}).get("value", "")
                body_text= _strip_html(raw_html)[:4000]
                excerpt  = _strip_html(item.get("excerpt", ""))
                author      = ""
                last_editor = ""
                last_edited = ""
                try:
                    history = content.get("history", {})
                    created_by = history.get("createdBy", {})
                    if created_by:
                        author = created_by.get("displayName", "") or created_by.get("username", "")
                    last_upd = history.get("lastUpdated", {})
                    if last_upd:
                        by = last_upd.get("by", {})
                        last_editor = by.get("displayName", "") or by.get("username", "")
                        when = last_upd.get("when", "")
                        if when:
                            try:
                                dt = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
                                last_edited = dt.strftime("%d %b %Y")
                            except Exception:
                                last_edited = when[:10]
                    if not last_editor:
                        ver = content.get("version", {})
                        if ver:
                            by = ver.get("by", {})
                            last_editor = by.get("displayName", "") or by.get("username", "")
                            when = ver.get("when", "")
                            if when and not last_edited:
                                try:
                                    dt = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
                                    last_edited = dt.strftime("%d %b %Y")
                                except Exception:
                                    last_edited = when[:10]
                except Exception:
                    pass
                if page_id not in collected:
                    collected[page_id] = {
                        "id": page_id, "title": title, "url": url,
                        "excerpt": excerpt, "body_text": body_text,
                        "author": author,
                        "last_editor": last_editor,
                        "last_edited": last_edited,
                    }
                hit_count[page_id] = hit_count.get(page_id, 0) + 1

        safe_q = query.replace('"', '')
        _ingest(_run_cql(
            f'type=page AND text~"{safe_q}"{space_clause} ORDER BY lastModified DESC'))
        for kw in keywords:
            safe_kw = kw.replace('"', '')
            _ingest(_run_cql(
                f'type=page AND title~"{safe_kw}"{space_clause} ORDER BY lastModified DESC',
                lim=15))
        if len(keywords) >= 2:
            for i in range(len(keywords) - 1):
                phrase  = f"{keywords[i]} {keywords[i+1]}"
                safe_p  = phrase.replace('"', '')
                _ingest(_run_cql(
                    f'type=page AND title~"{safe_p}"{space_clause} ORDER BY lastModified DESC',
                    lim=10))
        for kw in keywords:
            safe_kw = kw.replace('"', '')
            _ingest(_run_cql(
                f'type=page AND text~"{safe_kw}"{space_clause} ORDER BY score DESC',
                lim=10))

        ranked = sorted(
            collected.values(),
            key=lambda p: (-hit_count.get(p["id"], 0), p["title"].lower()),
        )
        return ranked[:limit]

    def get_page_body(self, page_id: str) -> str:
        data = self._get(
            f"/wiki/rest/api/content/{page_id}", {"expand": "body.storage"})
        return _strip_html(data.get("body", {}).get("storage", {}).get("value", ""))


# ══════════════════════════════════════════════════════════════════════════════
#  GROQ HELPERS
# ══════════════════════════════════════════════════════════════════════════════
GROQ_HOST = "api.groq.com"
GROQ_PATH = "/openai/v1/chat/completions"


def _groq_chat(api_key: str, model: str, messages: list,
               max_tokens: int = 900) -> str:
    body_bytes = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    headers = {
        "Content-Type":   "application/json",
        "Accept":         "application/json",
        "Authorization":  f"Bearer {api_key.strip()}",
        "Content-Length": str(len(body_bytes)),
        "User-Agent":     "Mozilla/5.0",
    }
    ctx = ssl.create_default_context()
    try:
        conn = http.client.HTTPSConnection(GROQ_HOST, timeout=30, context=ctx)
        conn.request("POST", GROQ_PATH, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        raw  = resp.read().decode("utf-8", errors="replace")
    except OSError as exc:
        raise ConnectionError(f"Network error reaching Groq: {exc}")
    finally:
        try: conn.close()
        except Exception: pass
    if resp.status == 413:
        raise ConnectionError(
            "Groq 413 -- Request too large.\n\n"
            "The combined prompt exceeded the model's token-per-minute limit.\n"
            "Try a shorter scenario or switch to a model with higher TPM in Settings."
        )
    if resp.status not in (200, 201):
        raise ConnectionError(f"Groq API error {resp.status}: {raw[:300]}")
    return json.loads(raw)["choices"][0]["message"]["content"]


def _build_page_context(pages: list, body_chars: int = BODY_CHARS_PER_PAGE,
                         max_pages: int = MAX_PAGES_IN_PROMPT) -> str:
    selected = pages[:max_pages]
    if not selected:
        return "No relevant Confluence pages were found."
    chunks = []
    for i, p in enumerate(selected, 1):
        trimmed_body = p["body_text"][:body_chars]
        if len(p["body_text"]) > body_chars:
            trimmed_body += "\n[... content truncated ...]"
        author_line = ""
        if p.get("author"):
            author_line = f"Author: {p['author']}"
        if p.get("last_editor") and p.get("last_editor") != p.get("author"):
            author_line += f"  |  Last edited by: {p['last_editor']}"
        if p.get("last_edited"):
            author_line += f"  ({p['last_edited']})"
        chunks.append(
            f"--- PAGE {i}: {p['title']} ---\n"
            f"URL: {p['url']}\n"
            + (f"{author_line}\n" if author_line else "")
            + f"\n{trimmed_body}"
        )
    return "\n\n".join(chunks)


def ask_kb_with_confluence(api_key: str, model: str,
                            scenario: str, pages: list) -> str:
    if len(scenario) > SCENARIO_MAX_CHARS:
        scenario = scenario[:SCENARIO_MAX_CHARS] + "..."
    context_block = _build_page_context(pages)

    # Build author attribution map for the prompt
    author_map = ""
    for i, p in enumerate(pages[:MAX_PAGES_IN_PROMPT], 1):
        name = p.get("author") or p.get("last_editor") or "Unknown"
        author_map += f"  Page {i} ({p['title']}): authored/edited by {name}\n"

    system_msg = (
        "You are a precise internal IT support assistant for 4G Capital.\n\n"
        "STRICT RULES — follow every one:\n"
        "1. Answer ONLY the exact question asked. No preamble, no background stories, no padding.\n"
        "2. Be direct: lead with the answer, then support it with facts from the pages.\n"
        "3. Attribute every fact: write 'According to [Author Name], ...' or "
        "'[Author Name] states that ...' using the author/editor names provided below.\n"
        "4. Use markdown tables (| col | col |) ONLY when comparing multiple items side-by-side.\n"
        "5. Keep the entire response under 250 words unless a table is necessary.\n"
        "6. End with a compact 'Sources' section: page title, URL, and author on one line each.\n"
        "7. If the pages do not contain the answer, say exactly: "
        "'The Confluence KB does not cover this. Please escalate to IT.' — nothing else.\n"
        "8. NEVER invent facts. NEVER add advice not found in the pages.\n\n"
        f"Author attribution reference:\n{author_map}"
    )
    return _groq_chat(api_key, model, [
        {"role": "system", "content": system_msg},
        {"role": "user",
         "content": f"QUESTION / SCENARIO:\n{scenario}\n\nCONFLUENCE PAGES:\n{context_block}"},
    ], max_tokens=900)


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT CONTEXT BUILDER
# ══════════════════════════════════════════════════════════════════════════════
def _build_chat_context_for_question(pages: list, question: str) -> str:
    if not pages:
        return "No Confluence pages are available. Cannot answer from knowledge base."

    keywords = _extract_keywords(question)

    scored_pages = []
    for p in pages:
        body  = p.get("body_text", "")
        score = _score_passage(body, keywords) if keywords else 0.0
        title_score = _score_passage(p.get("title", ""), keywords) * 2
        scored_pages.append((p, score + title_score))

    scored_pages.sort(key=lambda x: -x[1])

    top_pages = [p for p, _ in scored_pages[:CHAT_MAX_PAGES]]
    if not top_pages:
        top_pages = pages[:CHAT_MAX_PAGES]

    chunks = []
    for i, p in enumerate(top_pages, 1):
        passages = _extract_best_passages(
            p.get("body_text", ""), question, max_chars=CHAT_PASSAGE_CHARS)

        name = p.get("author") or p.get("last_editor") or ""
        attr_parts = []
        if p.get("author"):
            attr_parts.append(f"Author: {p['author']}")
        if p.get("last_editor") and p.get("last_editor") != p.get("author"):
            attr_parts.append(f"Last edited by: {p['last_editor']}")
        if p.get("last_edited"):
            attr_parts.append(p["last_edited"])
        attr_line = "  |  ".join(attr_parts)

        header = (
            f"=== SOURCE {i}: {p['title']} ===\n"
            f"URL: {p['url']}\n"
            + (f"{attr_line}\n" if attr_line else "")
        )
        chunks.append(header + "\n" + passages)

    return "\n\n".join(chunks)


# ══════════════════════════════════════════════════════════════════════════════
#  SCROLLABLE FRAME HELPER  — now with a VISIBLE vertical scrollbar
# ══════════════════════════════════════════════════════════════════════════════
def _bind_mousewheel_recursive(canvas: tk.Canvas, widget: tk.Widget):
    def _scroll(e):
        if e.delta:
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        elif e.num == 4:
            canvas.yview_scroll(-1, "units")
        elif e.num == 5:
            canvas.yview_scroll(1, "units")

    widget.bind("<MouseWheel>", _scroll, add="+")
    widget.bind("<Button-4>",   _scroll, add="+")
    widget.bind("<Button-5>",   _scroll, add="+")

    for child in widget.winfo_children():
        _bind_mousewheel_recursive(canvas, child)


def _make_scrollable(parent, bg=BG, show_scrollbar: bool = True):
    """
    Returns (outer_frame, inner_frame, canvas).
    show_scrollbar=True  → visible scrollbar on the right (keyboard-accessible).
    show_scrollbar=False → hidden scrollbar (mouse-wheel only, legacy behaviour).
    """
    outer  = tk.Frame(parent, bg=bg)
    canvas = tk.Canvas(outer, bg=bg, highlightthickness=0, bd=0)
    vsb    = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)

    if show_scrollbar:
        vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner  = tk.Frame(canvas, bg=bg)
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    inner.bind("<Configure>", lambda _:
        canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.bind("<Configure>", lambda e:
        canvas.itemconfig(win_id, width=e.width))

    def _reattach(_event=None):
        _bind_mousewheel_recursive(canvas, canvas)
        _bind_mousewheel_recursive(canvas, inner)

    inner.bind("<Configure>", lambda e: (
        _reattach(),
        canvas.configure(scrollregion=canvas.bbox("all"))
    ), add="+")
    _reattach()

    return outer, inner, canvas


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED RICH RENDERER  — uses SelectableText instead of tk.Label
# ══════════════════════════════════════════════════════════════════════════════
def render_rich(parent: tk.Frame, text: str, tables: list,
                wrap_width: int = 560,
                body_font=FONT_READER_BODY,
                bg: str = BG):
    segments = re.split(r'(<<TABLE_\d+>>)', text)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        mt = re.match(r'<<TABLE_(\d+)>>', seg)
        if mt:
            idx = int(mt.group(1))
            if idx < len(tables):
                _render_table(parent, tables[idx], bg)
            continue
        for para in re.split(r'\n{2,}', seg):
            para = para.strip()
            if not para:
                continue
            is_heading = (
                len(para) < 100 and "\n" not in para
                and not para.endswith((".", ",", ":", ";", "?", "!"))
                and not para.lower().startswith("http")
                and not para.startswith("Sources")
            )
            if is_heading:
                tk.Frame(parent, bg=BORDER, height=1).pack(
                    fill="x", pady=(14, 6))
                # Heading: still a Label (not selectable — minor content)
                lbl = tk.Label(
                    parent, text=para.upper(),
                    font=FONT_READER_SEC,
                    bg=bg, fg=TEXT_SECONDARY,
                    anchor="w", wraplength=wrap_width, justify="left",
                )
                lbl.pack(fill="x", pady=(0, 4))
            else:
                # Body: selectable Text widget — height grows to show ALL content
                st = SelectableText(
                    parent, text=para,
                    font=body_font,
                    bg=bg,
                    fg=TEXT_PRIMARY,
                    padx=2, pady=2,
                )
                st.pack(fill="x", pady=(0, 8))
                # Measure true line count AFTER the widget is rendered at its
                # actual width so word-wrap is accounted for, then set height.
                def _fit_height(widget=st):
                    try:
                        widget.update_idletasks()
                        # count() gives the number of display lines (post-wrap)
                        display_lines = int(
                            widget.count("1.0", tk.END, "displaylines")[0] or 1
                        )
                        widget.config(height=max(1, display_lines))
                    except Exception:
                        # Fallback: raw newline count
                        raw = int(widget.index(tk.END).split(".")[0]) - 1
                        widget.config(height=max(1, raw))
                # Schedule after layout so wraplength is resolved
                parent.after(10, _fit_height)


def _render_table(parent: tk.Frame, table_data: dict, bg: str = BG):
    headers = table_data.get("headers", [])
    rows    = table_data.get("rows", [])
    if not headers:
        return
    outer = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
    outer.pack(fill="x", pady=(4, 14))
    inner = tk.Frame(outer, bg=BG)
    inner.pack(fill="x")
    sn = f"KBTbl{id(outer)}.Treeview"
    st = ttk.Style()
    st.configure(sn,
                 background=BG, foreground=TEXT_PRIMARY,
                 fieldbackground=BG, rowheight=24,
                 font=("Segoe UI", 9), borderwidth=0)
    st.configure(f"{sn}.Heading",
                 background=BG_PANEL, foreground=TEXT_PRIMARY,
                 font=("Segoe UI", 9, "bold"), relief="flat")
    st.map(sn, background=[("selected", ACCENT_LIGHT)])
    tree = ttk.Treeview(inner, columns=headers, show="headings",
                         style=sn, height=min(len(rows), 10))
    for col in headers:
        tree.heading(col, text=col)
        tree.column(col, width=max(100, len(col) * 11), anchor="w", stretch=True)
    for i, row in enumerate(rows):
        padded = row + [""] * (len(headers) - len(row))
        tree.insert("", "end", values=padded[:len(headers)],
                    tags=("even" if i % 2 == 0 else "odd",))
    tree.tag_configure("even", background=BG)
    tree.tag_configure("odd",  background=BG_SUBTLE)
    xsb = ttk.Scrollbar(inner, orient="horizontal", command=tree.xview)
    tree.configure(xscrollcommand=xsb.set)
    tree.pack(fill="x")
    if len(headers) > 3:
        xsb.pack(fill="x")


# ══════════════════════════════════════════════════════════════════════════════
#  RELATED SOURCES PANEL  — wider, with visible scrollbar
# ══════════════════════════════════════════════════════════════════════════════
class RelatedTopicsPanel(tk.Frame):
    def __init__(self, parent, on_page_click=None, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self._on_page_click = on_page_click
        self._build()

    def _build(self):
        hdr = tk.Frame(self, bg=BG, pady=10)
        hdr.pack(fill="x", padx=12)
        tk.Label(hdr, text="Related Sources",
                 font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=TEXT_PRIMARY,
                 anchor="w").pack(side="left")
        self._count_lbl = tk.Label(hdr, text="",
                                    font=FONT_MONO_SM,
                                    bg=BG, fg=TEXT_MUTED,
                                    anchor="e")
        self._count_lbl.pack(side="right")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        scroll_outer, self._inner, self._canvas = _make_scrollable(
            self, bg=BG, show_scrollbar=True)
        scroll_outer.pack(fill="both", expand=True)

        tk.Label(
            self._inner,
            text="\nNo search results yet.\n\nRun a search to see\nrelated source pages.",
            font=FONT_BADGE, bg=BG, fg=TEXT_GHOST,
            justify="center", anchor="center"
        ).pack(pady=30, fill="x")

    def load(self, pages: list, on_page_click=None):
        if on_page_click:
            self._on_page_click = on_page_click
        for w in self._inner.winfo_children():
            w.destroy()
        if not pages:
            tk.Label(self._inner,
                     text="\nNo related pages found.",
                     font=FONT_BADGE, bg=BG, fg=TEXT_GHOST,
                     justify="center").pack(pady=20, fill="x")
            self._count_lbl.config(text="")
            return
        self._count_lbl.config(text=f"{len(pages)} page{'s' if len(pages)>1 else ''}")
        for i, page in enumerate(pages):
            self._add_card(i, page)

    def _add_card(self, idx: int, page: dict):
        card = tk.Frame(self._inner, bg=BG, cursor="hand2", pady=1)
        card.pack(fill="x")
        tk.Frame(self._inner, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(card, bg=BG, pady=8, padx=12)
        body.pack(fill="x", expand=True)

        num_lbl = tk.Label(body, text=f"{idx+1}.",
                 font=("Segoe UI", 7, "bold"),
                 bg=BG, fg=TEXT_MUTED)
        num_lbl.pack(side="left", anchor="n")

        right_body = tk.Frame(body, bg=BG)
        right_body.pack(side="left", padx=(6, 0), fill="x", expand=True)

        title_lbl = tk.Label(
            right_body,
            text=page["title"],
            font=("Segoe UI", 9, "bold"),
            bg=BG, fg=ACCENT,
            wraplength=230, justify="left", anchor="w",   # wider wrap for wider panel
            cursor="hand2")
        title_lbl.pack(fill="x", anchor="w")

        exc = page.get("excerpt", "")[:120]  # slightly more excerpt visible
        if exc:
            tk.Label(right_body,
                     text=exc + ("..." if len(page.get("excerpt","")) > 120 else ""),
                     font=("Segoe UI", 7),
                     bg=BG, fg=TEXT_MUTED,
                     wraplength=230, justify="left", anchor="w").pack(fill="x")

        meta_parts = []
        if page.get("author"):
            meta_parts.append(page['author'])
        if page.get("last_edited"):
            meta_parts.append(page["last_edited"])
        if meta_parts:
            tk.Label(right_body, text="  .  ".join(meta_parts),
                     font=("Segoe UI", 7, "italic"),
                     bg=BG, fg=TEXT_GHOST,
                     anchor="w").pack(fill="x", pady=(2, 0))

        def _click(e=None, i=idx):
            if self._on_page_click:
                self._on_page_click(i)

        def _enter(e, c=card, b=body, rb=right_body, t=title_lbl, n=num_lbl):
            for w in (c, b, rb, t, n): w.config(bg=ACCENT_LIGHT)
        def _leave(e, c=card, b=body, rb=right_body, t=title_lbl, n=num_lbl):
            for w in (c, b, rb, t, n): w.config(bg=BG)

        for w in (card, body, right_body, title_lbl, num_lbl):
            w.bind("<Button-1>", _click)
            w.bind("<Enter>",    _enter)
            w.bind("<Leave>",    _leave)


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT PANEL  — with visible scrollbar + selectable AI responses
# ══════════════════════════════════════════════════════════════════════════════
class ChatPanel(tk.Frame):
    def __init__(self, parent, on_send_cb, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self._on_send_cb    = on_send_cb
        self._history: list = []
        self._settings      = None
        self._model         = "llama-3.1-8b-instant"
        self._thinking_row  = None
        self._spin_active   = False
        self._spin_lbl      = None
        self._spin_frames   = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._spin_idx      = 0
        self._pages: list   = []
        self._initial_query = ""
        self._seeded        = False
        self._build()

    def seed(self, ai_body: str, pages: list, initial_query: str = ""):
        self._pages         = pages
        self._initial_query = initial_query
        self._seeded        = True

        try:
            self._settings = load_settings()
            self._model    = self._settings.get("groq_model", "llama-3.1-8b-instant")
        except Exception:
            pass

        page_list = "\n".join(
            f"  {i+1}. {p['title']} — {p['url']}"
            for i, p in enumerate(pages)
        )

        # Build author attribution map for chat system prompt
        author_map = ""
        for i, p in enumerate(pages, 1):
            name = p.get("author") or p.get("last_editor") or "Unknown"
            author_map += f"  Page {i} ({p['title']}): {name}\n"

        system_content = (
            "You are a precise internal IT support assistant for 4G Capital.\n\n"
            "STRICT RULES:\n"
            "1. Answer ONLY the exact question. No preamble, no stories, no padding.\n"
            "2. Lead with the direct answer. Support with facts from the KB pages.\n"
            "3. Attribute facts: use 'According to [Author Name], ...' or "
            "'[Author Name] states that ...' using the author map below.\n"
            "4. Keep responses under 200 words unless a table is needed.\n"
            "5. Use markdown tables only when comparing multiple items.\n"
            "6. If pages lack the answer, say: "
            "'Not covered in the Confluence KB. Please escalate to IT.'\n"
            "7. NEVER invent information.\n\n"
            f"Author attribution map:\n{author_map}\n"
            "Available KB pages:\n" + page_list
        )
        self._history = [{"role": "system", "content": system_content}]

        if ai_body.strip():
            self._history.append({
                "role": "assistant",
                "content": (
                    f"[Initial answer for: {initial_query[:120]}]\n\n{ai_body[:1200]}"
                ),
            })

        self._add_system_bubble(
            f"Ready — {len(pages)} page(s) loaded. Ask any follow-up question.")
        self._status_dot.config(fg=SUCCESS)
        self._status_word.config(text="Ready", fg=SUCCESS)

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG, pady=10)
        hdr.pack(fill="x", padx=12)
        tk.Label(hdr, text="AI Chat",
                 font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=TEXT_PRIMARY,
                 anchor="w").pack(side="left")

        # Status group: large dot + "Instant" word label
        status_group = tk.Frame(hdr, bg=BG)
        status_group.pack(side="right")
        self._status_dot = tk.Label(
            status_group, text="●",
            font=("Segoe UI", 13),
            bg=BG, fg=TEXT_GHOST)
        self._status_dot.pack(side="left")
        self._status_word = tk.Label(
            status_group, text="Instant",
            font=("Segoe UI", 7, "bold"),
            bg=BG, fg=TEXT_GHOST)
        self._status_word.pack(side="left", padx=(2, 0))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Messages area — show_scrollbar=True for keyboard users
        msg_outer, self._msg_frame, self._canvas = _make_scrollable(
            self, bg=BG, show_scrollbar=True)
        msg_outer.pack(fill="both", expand=True)

        self._add_system_bubble(
            "Run a Confluence search and I'll have full context to answer your questions accurately.")

        # Input area
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        inp_area = tk.Frame(self, bg=BG, pady=8, padx=10)
        inp_area.pack(fill="x", side="bottom")

        self._inp_border = tk.Frame(inp_area, bg=BORDER_MID, padx=1, pady=1)
        self._inp_border.pack(fill="x", pady=(0, 6))

        self._entry = tk.Text(
            self._inp_border, height=3, font=FONT_BODY, wrap="word",
            bg=BG_INPUT, fg=TEXT_PRIMARY, bd=0, relief="flat",
            padx=8, pady=6, insertbackground=ACCENT,
        )
        self._entry.pack(fill="x")
        self._entry.bind("<Return>",       self._on_return)
        self._entry.bind("<Shift-Return>", lambda e: None)
        self._entry.bind("<FocusIn>",
            lambda _: self._inp_border.config(bg=BORDER_FOCUS))
        self._entry.bind("<FocusOut>",
            lambda _: self._inp_border.config(bg=BORDER_MID))

        btn_row = tk.Frame(inp_area, bg=BG)
        btn_row.pack(fill="x")

        self._send_btn = tk.Button(
            btn_row, text="Send  Enter",
            bg=ACCENT, fg=TEXT_ON_ACCENT, font=FONT_BTN,
            relief="flat", cursor="hand2", padx=14, pady=5, bd=0,
            activebackground=ACCENT_HOVER,
            command=self._send)
        self._send_btn.pack(side="right")
        self._send_btn.bind("<Enter>",
            lambda _: self._send_btn.config(bg=ACCENT_HOVER))
        self._send_btn.bind("<Leave>",
            lambda _: self._send_btn.config(bg=ACCENT))

        tk.Label(btn_row, text="Shift+Enter for newline",
                 font=("Segoe UI", 7), bg=BG, fg=TEXT_GHOST,
                 anchor="w").pack(side="left")

    def _on_return(self, event):
        if not (event.state & 0x0001):
            self._send()
            return "break"

    def _send(self):
        text = self._entry.get("1.0", tk.END).strip()
        if not text:
            return
        self._entry.delete("1.0", tk.END)
        self._add_user_bubble(text)

        if not self._seeded:
            self._add_system_bubble(
                "Please run a Confluence search first so I have knowledge base context.")
            return

        if not self._settings:
            try:
                self._settings = load_settings()
                self._model    = self._settings.get("groq_model", "llama-3.1-8b-instant")
            except Exception:
                self._add_system_bubble("Could not load API settings.")
                return

        context_block = _build_chat_context_for_question(self._pages, text)

        system_msgs = [m for m in self._history if m["role"] == "system"]
        non_system  = [m for m in self._history if m["role"] != "system"]
        first_asst  = next((m for m in non_system if m["role"] == "assistant"), None)
        recent      = non_system[-(CHAT_HISTORY_TURNS * 2):]
        if first_asst and first_asst not in recent:
            recent = [first_asst] + recent

        trimmed_history = system_msgs + recent

        context_injection = {
            "role": "user",
            "content": (
                f"[Confluence KB context for this question]\n\n{context_block}\n\n"
                f"[End of KB context]\n\n"
                f"My question: {text}"
            ),
        }
        messages_to_send = trimmed_history + [context_injection]
        self._history.append({"role": "user", "content": text})

        self.set_thinking(True)
        self._send_btn.config(state="disabled")
        self._on_send_cb(text, messages_to_send, self._settings, self._model)

    def add_ai_reply(self, reply: str):
        self._history.append({"role": "assistant", "content": reply})
        self.set_thinking(False)
        self._send_btn.config(state="normal")
        self._status_dot.config(fg=SUCCESS)
        self._status_word.config(text="Ready", fg=SUCCESS)
        self._add_ai_bubble(reply)

    def add_error(self, msg: str):
        self.set_thinking(False)
        self._send_btn.config(state="normal")
        self._status_dot.config(fg=ERROR)
        self._status_word.config(text="Error", fg=ERROR)
        self._add_system_bubble(f"Error: {msg[:300]}")

    def set_thinking(self, thinking: bool):
        if thinking:
            self._status_dot.config(fg=WARNING)
            self._status_word.config(text="Thinking…", fg=WARNING)
            if self._thinking_row and self._thinking_row.winfo_exists():
                return
            self._thinking_row = tk.Frame(self._msg_frame, bg=BG)
            self._thinking_row.pack(fill="x", padx=10, pady=4)
            self._spin_lbl = tk.Label(
                self._thinking_row, text="  Thinking...",
                font=FONT_CHAT_META, bg=BG, fg=TEXT_MUTED)
            self._spin_lbl.pack(anchor="w")
            self._spin_active = True
            self._animate_spin()
            self._scroll_bottom()
        else:
            self._spin_active = False
            self._status_dot.config(fg=TEXT_GHOST)
            self._status_word.config(text="Instant", fg=TEXT_GHOST)
            if self._thinking_row and self._thinking_row.winfo_exists():
                self._thinking_row.destroy()
            self._thinking_row = None
            self._spin_lbl     = None

    def _animate_spin(self):
        if not self._spin_active:
            return
        try:
            if self._spin_lbl and self._spin_lbl.winfo_exists():
                f = self._spin_frames[self._spin_idx % 10]
                self._spin_lbl.config(text=f"{f}  Thinking...")
                self._spin_idx += 1
                self.after(90, self._animate_spin)
        except Exception:
            pass

    def _add_user_bubble(self, text: str):
        ts  = datetime.datetime.now().strftime("%H:%M")
        row = tk.Frame(self._msg_frame, bg=BG, pady=3)
        row.pack(fill="x", padx=8)
        tk.Label(row, text=f"You  {ts}",
                 font=FONT_CHAT_META, bg=BG, fg=TEXT_GHOST).pack(anchor="e")
        bubble = tk.Frame(row, bg=BG_PANEL, padx=10, pady=7)
        bubble.pack(anchor="e")
        # User bubbles: selectable
        st = SelectableText(
            bubble, text=text,
            font=FONT_CHAT_USER, bg=BG_PANEL, fg=TEXT_PRIMARY,
            padx=2, pady=2,
        )
        st.pack(anchor="w")
        def _fit_user(widget=st):
            try:
                widget.update_idletasks()
                dl = int(widget.count("1.0", tk.END, "displaylines")[0] or 1)
                widget.config(height=max(1, dl))
            except Exception:
                raw = int(widget.index(tk.END).split(".")[0]) - 1
                widget.config(height=max(1, raw))
        bubble.after(10, _fit_user)
        self._scroll_bottom()

    def _add_ai_bubble(self, text: str):
        ts  = datetime.datetime.now().strftime("%H:%M")
        row = tk.Frame(self._msg_frame, bg=BG, pady=3)
        row.pack(fill="x", padx=8)
        tk.Label(row, text=f"AI  {ts}",
                 font=FONT_CHAT_META, bg=BG, fg=TEXT_GHOST).pack(anchor="w")
        bubble = tk.Frame(row, bg=ACCENT_LIGHT, padx=10, pady=8)
        bubble.pack(anchor="w", fill="x")
        tk.Frame(bubble, bg=ACCENT, width=2).pack(side="left", fill="y")
        content = tk.Frame(bubble, bg=ACCENT_LIGHT)
        content.pack(side="left", fill="x", expand=True, padx=(8, 0))
        cleaned, tables = _parse_md_tables(text)
        render_rich(content, cleaned, tables,
                    wrap_width=400, body_font=FONT_CHAT_AI, bg=ACCENT_LIGHT)
        self._scroll_bottom()

    def _add_system_bubble(self, text: str):
        row = tk.Frame(self._msg_frame, bg=BG, pady=2)
        row.pack(fill="x", padx=10)
        tk.Label(row, text=text,
                 font=FONT_CHAT_META, bg=BG, fg=TEXT_MUTED,
                 wraplength=440, justify="left", anchor="w").pack(anchor="w")
        self._scroll_bottom()

    def _scroll_bottom(self):
        self.after(80, lambda: self._canvas.yview_moveto(1.0))

    def focus_input(self):
        self._entry.focus_set()


# ══════════════════════════════════════════════════════════════════════════════
#  SCROLLABLE TAB BAR
# ══════════════════════════════════════════════════════════════════════════════
class ScrollableTabBar(tk.Frame):
    def __init__(self, parent, bg=BG, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        self._bg       = bg
        self._tab_refs = []

        self._left_btn = tk.Button(
            self, text="<", width=2,
            bg=BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 8), relief="flat", cursor="hand2",
            bd=0, padx=4, pady=4,
            activebackground=BG_PANEL,
            command=self._scroll_left)
        self._left_btn.pack(side="left")

        self._canvas = tk.Canvas(self, bg=bg, highlightthickness=0,
                                  bd=0, height=34)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._inner = tk.Frame(self._canvas, bg=bg)
        self._win_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        self._right_btn = tk.Button(
            self, text=">", width=2,
            bg=BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 8), relief="flat", cursor="hand2",
            bd=0, padx=4, pady=4,
            activebackground=BG_PANEL,
            command=self._scroll_right)
        self._right_btn.pack(side="right")
        self._update_arrows()

    def add_tab(self, key, label: str, command, active: bool = False):
        btn = tk.Button(
            self._inner, text=label,
            bg=BG if not active else BG_PANEL,
            fg=ACCENT if active else TEXT_SECONDARY,
            font=("Segoe UI", 9, "bold") if active else ("Segoe UI", 8),
            relief="flat", cursor="hand2",
            padx=12, pady=7, bd=0,
            activebackground=BG_PANEL,
            command=command)
        btn.pack(side="left", padx=1, pady=4)
        self._tab_refs.append((key, btn))
        return btn

    def clear(self):
        for _, btn in self._tab_refs:
            btn.destroy()
        self._tab_refs = []
        self._canvas.xview_moveto(0)

    def set_active(self, key):
        for k, btn in self._tab_refs:
            active = (k == key)
            btn.config(
                bg=BG_PANEL if active else BG,
                fg=ACCENT if active else TEXT_SECONDARY,
                font=("Segoe UI", 9, "bold") if active else ("Segoe UI", 8))

    def _on_inner_configure(self, _=None):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        self._update_arrows()

    def _on_canvas_configure(self, _=None):
        self._update_arrows()

    def _scroll_left(self):
        self._canvas.xview_scroll(-3, "units")
        self.after(50, self._update_arrows)

    def _scroll_right(self):
        self._canvas.xview_scroll(3, "units")
        self.after(50, self._update_arrows)

    def _update_arrows(self):
        try:
            lo, hi = self._canvas.xview()
        except Exception:
            return
        self._left_btn.config(
            state="normal" if lo > 0.001 else "disabled",
            fg=TEXT_PRIMARY if lo > 0.001 else TEXT_GHOST)
        self._right_btn.config(
            state="normal" if hi < 0.999 else "disabled",
            fg=TEXT_PRIMARY if hi < 0.999 else TEXT_GHOST)


# ══════════════════════════════════════════════════════════════════════════════
#  FULL-WINDOW READER  — scrollable reader with visible scrollbar
# ══════════════════════════════════════════════════════════════════════════════
class FullWindowReader(tk.Frame):
    def __init__(self, parent, on_close_cb, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self._on_close_cb  = on_close_cb
        self._pages        = []
        self._current_tab  = -1
        self._ai_body      = ""
        self._current_url  = ""
        self._current_body = ""
        self._build()

    def _build(self):
        # Chrome bar
        chrome = tk.Frame(self, bg=BG, height=44)
        chrome.pack(fill="x")
        chrome.pack_propagate(False)
        tk.Frame(chrome, bg=BORDER, height=1).pack(side="bottom", fill="x")

        back_btn = tk.Button(
            chrome, text="<- Back",
            bg=BG, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9),
            relief="flat", cursor="hand2",
            bd=0, padx=14, pady=10,
            activebackground=BG_PANEL,
            command=self._close)
        back_btn.pack(side="left")
        back_btn.bind("<Enter>", lambda _: back_btn.config(fg=TEXT_PRIMARY))
        back_btn.bind("<Leave>", lambda _: back_btn.config(fg=TEXT_SECONDARY))

        tk.Label(chrome, text="KB Reader",
                 font=("Segoe UI", 9, "bold"),
                 bg=BG, fg=TEXT_PRIMARY).pack(side="left", padx=10)

        _bc = dict(bg=BG, relief="flat", cursor="hand2",
                   bd=0, padx=12, pady=10, font=("Segoe UI", 8))

        self._copy_var = tk.StringVar(value="Copy")
        copy_btn = tk.Button(
            chrome, textvariable=self._copy_var,
            fg=TEXT_SECONDARY,
            activebackground=BG_PANEL,
            command=self._copy, **_bc)
        copy_btn.pack(side="right", padx=2)
        copy_btn.bind("<Enter>", lambda _: copy_btn.config(fg=TEXT_PRIMARY))
        copy_btn.bind("<Leave>", lambda _: copy_btn.config(fg=TEXT_SECONDARY))

        self._open_btn = tk.Button(
            chrome, text="Open in Browser",
            fg=ACCENT, state="disabled",
            activebackground=BG_PANEL,
            command=self._open_browser, **_bc)
        self._open_btn.pack(side="right", padx=2)

        # Tab bar
        tab_outer = tk.Frame(self, bg=BG)
        tab_outer.pack(fill="x")
        self._tab_bar = ScrollableTabBar(tab_outer, bg=BG)
        self._tab_bar.pack(fill="x", padx=6)
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Body: three columns
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # LEFT: reader (expands) — visible scrollbar
        left_col = tk.Frame(body, bg=BG)
        left_col.pack(side="left", fill="both", expand=True)
        reader_outer, self._content_frame, self._canvas = _make_scrollable(
            left_col, bg=BG, show_scrollbar=True)
        reader_outer.pack(fill="both", expand=True)

        # Divider
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # CENTER: Chat (fixed width)
        center_col = tk.Frame(body, bg=BG, width=COL_CHAT_WIDTH)
        center_col.pack(side="left", fill="y")
        center_col.pack_propagate(False)
        self._chat = ChatPanel(center_col, on_send_cb=self._relay_chat_send)
        self._chat.pack(fill="both", expand=True)

        # Divider
        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # RIGHT: Related Sources (wider — 280px)
        right_col = tk.Frame(body, bg=BG, width=COL_SOURCES_WIDTH)
        right_col.pack(side="right", fill="y")
        right_col.pack_propagate(False)
        self._related = RelatedTopicsPanel(right_col)
        self._related.pack(fill="both", expand=True)

    # ── Tab management ────────────────────────────────────────────────────────
    def _build_tabs(self):
        self._tab_bar.clear()
        self._tab_bar.add_tab(
            "ai", "  AI Answer  ",
            command=lambda: self._switch_tab(-1),
            active=(self._current_tab == -1))
        for i, p in enumerate(self._pages):
            short = (p["title"][:22] + "...") if len(p["title"]) > 22 else p["title"]
            self._tab_bar.add_tab(
                i, f"  {short}  ",
                command=lambda idx=i: self._switch_tab(idx),
                active=(self._current_tab == i))

    def _switch_tab(self, idx: int):
        self._current_tab = idx
        self._tab_bar.set_active("ai" if idx == -1 else idx)
        if idx == -1:
            self._render_ai_answer()
        else:
            p = self._pages[idx]
            self._render_page(p["title"], p["body_text"], p["url"],
                               p.get("author", ""),
                               p.get("last_editor", ""),
                               p.get("last_edited", ""))
        self._canvas.yview_moveto(0)

    def load(self, ai_body: str, pages: list, initial_query: str = ""):
        self._ai_body = ai_body
        self._pages   = pages
        self._build_tabs()
        self._switch_tab(-1)
        self._chat.seed(ai_body, pages, initial_query=initial_query)
        self._related.load(pages, on_page_click=self._switch_tab)

    def _clear(self):
        for w in self._content_frame.winfo_children():
            w.destroy()

    def _margin(self) -> tk.Frame:
        m = tk.Frame(self._content_frame, bg=BG)
        m.pack(fill="both", expand=True, padx=40, pady=(20, 40))
        return m

    def _wrap(self) -> int:
        w = self.winfo_width()
        # subtract: chat col + sources col + 2 dividers (2px) + margins (80px)
        return max(220, w - COL_CHAT_WIDTH - COL_SOURCES_WIDTH - 4 - 80)

    # ── AI Answer renderer ────────────────────────────────────────────────────
    def _render_ai_answer(self):
        self._current_body = self._ai_body
        self._current_url  = ""
        self._open_btn.config(state="disabled", fg=TEXT_GHOST)
        self._clear()
        margin = self._margin()

        tk.Label(margin, text="AI Answer",
                 font=("Georgia", 14, "bold"),
                 bg=BG, fg=TEXT_PRIMARY,
                 anchor="w").pack(fill="x", pady=(0, 4))
        tk.Label(margin, text="Confluence Knowledge Base  .  4G Capital",
                 font=("Segoe UI", 8, "italic"),
                 bg=BG, fg=TEXT_MUTED,
                 anchor="w").pack(fill="x", pady=(0, 16))
        tk.Frame(margin, bg=BORDER, height=1).pack(fill="x", pady=(0, 16))

        cleaned, tables = _parse_md_tables(self._ai_body)
        main_section = re.split(r"Sources", cleaned)[0].strip()
        render_rich(margin, main_section, tables, wrap_width=self._wrap())

        if self._pages:
            tk.Frame(margin, bg=BORDER, height=1).pack(fill="x", pady=(20, 12))
            src_hdr = tk.Frame(margin, bg=BG)
            src_hdr.pack(fill="x", pady=(0, 10))
            tk.Label(src_hdr, text="Sources",
                     font=("Segoe UI", 10, "bold"),
                     bg=BG, fg=TEXT_PRIMARY, anchor="w").pack(side="left")
            tk.Label(src_hdr, text=f"  {len(self._pages)} page(s)",
                     font=FONT_BADGE, bg=BG, fg=TEXT_MUTED).pack(side="left")

            for i, p in enumerate(self._pages):
                src_row = tk.Frame(margin, bg=BG_SUBTLE, pady=8, padx=12)
                src_row.pack(fill="x", pady=(0, 4))
                tk.Frame(src_row, bg=ACCENT, width=2).pack(side="left", fill="y")
                info = tk.Frame(src_row, bg=BG_SUBTLE)
                info.pack(side="left", padx=(10, 0), fill="x", expand=True)

                lnk = tk.Button(
                    info, text=p["title"],
                    bg=BG_SUBTLE, fg=ACCENT,
                    font=("Segoe UI", 9, "bold"), relief="flat",
                    cursor="hand2", bd=0,
                    command=lambda idx=i: self._switch_tab(idx))
                lnk.pack(side="left")
                lnk.bind("<Enter>", lambda e, b=lnk: b.config(fg=ACCENT_HOVER))
                lnk.bind("<Leave>", lambda e, b=lnk: b.config(fg=ACCENT))

                attr_parts = []
                if p.get("author"):
                    attr_parts.append(p['author'])
                if p.get("last_editor") and p.get("last_editor") != p.get("author"):
                    attr_parts.append(f"edited by {p['last_editor']}")
                if p.get("last_edited"):
                    attr_parts.append(p["last_edited"])
                if attr_parts:
                    tk.Label(info, text="  .  ".join(attr_parts),
                             font=FONT_READER_META,
                             bg=BG_SUBTLE, fg=TEXT_MUTED).pack(
                        side="left", padx=(6, 0))

    # ── Page renderer ──────────────────────────────────────────────────────────
    def _render_page(self, title: str, body: str, url: str,
                      author: str = "", last_editor: str = "",
                      last_edited: str = ""):
        self._current_body = body
        self._current_url  = url
        self._open_btn.config(state="normal", fg=ACCENT)
        self._clear()
        margin = self._margin()

        tk.Label(
            margin, text=title,
            font=FONT_READER_TITLE, bg=BG, fg=TEXT_PRIMARY,
            wraplength=self._wrap(), justify="left", anchor="w",
        ).pack(fill="x", pady=(0, 10))

        attr_parts = []
        if author:
            attr_parts.append(f"Author: {author}")
        if last_editor and last_editor != author:
            attr_parts.append(f"Last edited by {last_editor}")
        if last_edited:
            attr_parts.append(last_edited)
        if attr_parts:
            tk.Label(margin,
                     text="  .  ".join(attr_parts),
                     font=("Segoe UI", 8, "italic"),
                     bg=BG, fg=TEXT_MUTED,
                     anchor="w").pack(fill="x", pady=(0, 10))

        if url:
            uf = tk.Frame(margin, bg=BG_SUBTLE, padx=10, pady=6)
            uf.pack(fill="x", pady=(0, 16))
            ul = tk.Label(
                uf, text=f"  {url}",
                font=("Consolas", 8), bg=BG_SUBTLE, fg=ACCENT,
                cursor="hand2", anchor="w")
            ul.pack(side="left", fill="x")
            ul.bind("<Button-1>", lambda _: webbrowser.open(url))
            ul.bind("<Enter>",    lambda _: ul.config(fg=ACCENT_HOVER))
            ul.bind("<Leave>",    lambda _: ul.config(fg=ACCENT))

        tk.Frame(margin, bg=BORDER, height=1).pack(fill="x", pady=(0, 16))
        cleaned, tables = _parse_md_tables(body)
        render_rich(margin, cleaned, tables, wrap_width=self._wrap())

    # ── Relay chat send -> KBPanel ─────────────────────────────────────────────
    def _relay_chat_send(self, text: str, messages: list,
                          settings: dict, model: str):
        w = self.master
        while w is not None:
            if isinstance(w, KBPanel):
                w._dispatch_chat(text, messages, settings, model, self._chat)
                return
            w = getattr(w, 'master', None)

    def _close(self):         self._on_close_cb()
    def _copy(self):
        self.clipboard_clear()
        self.clipboard_append(self._current_body)
        self._copy_var.set("Copied!")
        self.after(2000, lambda: self._copy_var.set("Copy"))
    def _open_browser(self):
        if self._current_url:
            webbrowser.open(self._current_url)


# ══════════════════════════════════════════════════════════════════════════════
#  KB PANEL  --  main entry frame
# ══════════════════════════════════════════════════════════════════════════════
class KBPanel(tk.Frame):
    def __init__(self, parent,
                 use_local_first: bool = False,
                 settings_loader=None,
                 **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self._use_local_first  = use_local_first
        self._settings_loader  = settings_loader
        self.on_client_ready   = None
        self._pages_found      = []
        self._last_answer      = ""
        self._last_scenario    = ""
        self._spinning         = False
        self._spin_idx         = 0
        self._spinner_frames   = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._settings_cache   = None
        self._reader_open      = False
        self._build_ui()

    def _build_ui(self):
        # Top control bar
        ctrl = tk.Frame(self, bg=BG, pady=0)
        ctrl.pack(fill="x")
        tk.Frame(ctrl, bg=BORDER, height=1).pack(side="bottom", fill="x")

        left = tk.Frame(ctrl, bg=BG)
        left.pack(side="left", fill="y", padx=12, pady=8)

        self._test_btn = tk.Button(
            left, text="Test Connection",
            bg=ACCENT, fg=TEXT_ON_ACCENT,
            font=FONT_BTN_SM, relief="flat", cursor="hand2",
            padx=10, pady=5, bd=0,
            activebackground=ACCENT_HOVER,
            command=self._test_connection)
        self._test_btn.pack(side="left", padx=(0, 10))
        self._test_btn.bind("<Enter>",
            lambda _: self._test_btn.config(bg=ACCENT_HOVER))
        self._test_btn.bind("<Leave>",
            lambda _: self._test_btn.config(bg=ACCENT))

        self._space_badge_var = tk.StringVar(value="Not connected")
        self._space_badge = tk.Label(
            left, textvariable=self._space_badge_var,
            font=FONT_BADGE, bg=BG, fg=TEXT_MUTED)
        self._space_badge.pack(side="left")

        right = tk.Frame(ctrl, bg=BG)
        right.pack(side="right", fill="y", padx=12, pady=8)

        self._pages_var = tk.StringVar(value="")
        tk.Label(right, textvariable=self._pages_var,
                 font=FONT_MONO_SM, bg=BG, fg=TEXT_SECONDARY).pack(
            side="right", padx=(8, 0))

        self.status_var = tk.StringVar(value="Run Test first")
        tk.Label(right, textvariable=self.status_var,
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_MUTED).pack(
            side="right", padx=4)

        self._spinner_var = tk.StringVar(value="")
        tk.Label(right, textvariable=self._spinner_var,
                 font=("Segoe UI", 11), bg=BG, fg=TEXT_MUTED).pack(
            side="right")

        # Search bar
        search_row = tk.Frame(self, bg=BG, pady=10)
        search_row.pack(fill="x", padx=0)
        tk.Frame(search_row, bg=BORDER, height=1).pack(side="bottom", fill="x")

        self._search_btn = tk.Button(
            search_row, text="Search & Answer",
            bg=ACCENT, fg=TEXT_ON_ACCENT, font=FONT_BTN,
            relief="flat", cursor="hand2", pady=7, padx=16, bd=0,
            activebackground=ACCENT_HOVER,
            command=self._on_search)
        self._search_btn.pack(side="left", padx=(12, 10))
        self._search_btn.bind("<Enter>",
            lambda _: self._search_btn.config(bg=ACCENT_HOVER))
        self._search_btn.bind("<Leave>",
            lambda _: self._search_btn.config(bg=ACCENT))

        inp_wrap = tk.Frame(search_row, bg=BG)
        inp_wrap.pack(side="left", fill="both", expand=True)

        tk.Label(inp_wrap, text="DESCRIBE YOUR SCENARIO OR ISSUE",
                 font=FONT_LABEL, bg=BG, fg=TEXT_GHOST,
                 anchor="w").pack(fill="x", pady=(0, 3))

        self._inp_border = tk.Frame(inp_wrap, bg=BORDER_MID, padx=1, pady=1)
        self._inp_border.pack(fill="x")

        _ph = "e.g.  Customer cannot log in after password reset on the Beyonic portal..."
        self._scenario_txt = tk.Text(
            self._inp_border, height=3, font=FONT_BODY, wrap="word",
            bg=BG_INPUT, fg=TEXT_PRIMARY, bd=0, relief="flat",
            padx=10, pady=8, insertbackground=ACCENT,
            selectbackground=ACCENT_LIGHT, selectforeground=TEXT_PRIMARY,
        )
        self._scenario_txt.pack(fill="x")
        self._scenario_txt.insert("1.0", _ph)
        self._scenario_txt.config(fg=TEXT_GHOST)
        self._scenario_txt._ph = _ph

        def _fi(_):
            self._inp_border.config(bg=BORDER_FOCUS)
            if self._scenario_txt.get("1.0", tk.END).strip() == _ph:
                self._scenario_txt.delete("1.0", tk.END)
                self._scenario_txt.config(fg=TEXT_PRIMARY)

        def _fo(_):
            self._inp_border.config(bg=BORDER_MID)
            if not self._scenario_txt.get("1.0", tk.END).strip():
                self._scenario_txt.insert("1.0", _ph)
                self._scenario_txt.config(fg=TEXT_GHOST)

        self._scenario_txt.bind("<FocusIn>",  _fi)
        self._scenario_txt.bind("<FocusOut>", _fo)

        self._copy_btn = tk.Button(
            search_row, text="Copy Answer",
            bg=BG, fg=TEXT_SECONDARY, font=FONT_BTN_SM,
            relief="flat", cursor="hand2", padx=12, pady=7, bd=0,
            command=self._copy_output)
        self._copy_btn.pack(side="right", padx=(8, 12))
        self._copy_btn.bind("<Enter>",
            lambda _: self._copy_btn.config(fg=TEXT_PRIMARY))
        self._copy_btn.bind("<Leave>",
            lambda _: self._copy_btn.config(fg=TEXT_SECONDARY))

        # Content area
        self._content_area = tk.Frame(self, bg=BG)
        self._content_area.pack(fill="both", expand=True)

        self._placeholder_frame = tk.Frame(self._content_area, bg=BG)
        self._placeholder_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._build_placeholder()

        self._reader = FullWindowReader(
            self, on_close_cb=self._close_reader)

    def _build_placeholder(self):
        outer = tk.Frame(self._placeholder_frame, bg=BG)
        outer.pack(fill="both", expand=True)

        left_ph = tk.Frame(outer, bg=BG)
        left_ph.pack(side="left", fill="both", expand=True, padx=24, pady=20)

        welcome = tk.Frame(left_ph, bg=BG_SUBTLE, padx=20, pady=20)
        welcome.pack(fill="x")
        tk.Frame(welcome, bg=ACCENT, height=2).pack(fill="x", pady=(0, 14))
        tk.Label(welcome, text="Knowledge Base",
                 font=("Georgia", 15, "bold"),
                 bg=BG_SUBTLE, fg=TEXT_PRIMARY,
                 anchor="w").pack(fill="x")
        tk.Label(welcome,
                 text="4G Capital  .  Confluence Integration",
                 font=("Segoe UI", 9, "italic"),
                 bg=BG_SUBTLE, fg=TEXT_MUTED,
                 anchor="w").pack(fill="x", pady=(4, 14))
        tk.Frame(welcome, bg=BORDER, height=1).pack(fill="x", pady=(0, 14))

        steps = [
            ("1", "Describe Scenario",  "Type your issue or question in the search field above"),
            ("2", "Search & Answer",    "Click Search & Answer — AI analyses up to 4 relevant pages"),
            ("3", "AI Chat (centre)",   "Ask follow-ups — context is re-matched per question; answers cite the page author"),
            ("4", "Related Sources",    "Source pages found appear on the right as clickable cards"),
        ]
        for num, title, desc in steps:
            row = tk.Frame(welcome, bg=BG_SUBTLE, pady=5)
            row.pack(fill="x")
            tk.Label(row, text=num,
                     font=("Segoe UI", 8, "bold"),
                     bg=ACCENT, fg=TEXT_ON_ACCENT,
                     padx=7, pady=4).pack(side="left", anchor="n")
            info = tk.Frame(row, bg=BG_SUBTLE)
            info.pack(side="left", padx=10, fill="x", expand=True)
            tk.Label(info, text=title, font=FONT_SUBHEADING,
                     bg=BG_SUBTLE, fg=TEXT_PRIMARY, anchor="w").pack(anchor="w")
            tk.Label(info, text=desc, font=("Segoe UI", 8),
                     bg=BG_SUBTLE, fg=TEXT_MUTED,
                     wraplength=340, justify="left", anchor="w").pack(anchor="w")

        info_strip = tk.Frame(left_ph, bg=BG, pady=6, padx=2)
        info_strip.pack(fill="x", pady=(10, 0))
        tk.Label(info_strip,
                 text=(f"Context: up to {CHAT_MAX_PAGES} pages  .  "
                       f"{CHAT_PASSAGE_CHARS} chars of best-matched passages per question  .  "
                       f"All text is selectable (click & drag to copy)"),
                 font=("Segoe UI", 8, "italic"),
                 bg=BG, fg=TEXT_GHOST,
                 anchor="w").pack(anchor="w")

        tk.Frame(outer, bg=BORDER, width=1).pack(side="left", fill="y")
        right_ph = tk.Frame(outer, bg=BG, width=COL_SOURCES_WIDTH + 90)
        right_ph.pack(side="right", fill="y")
        right_ph.pack_propagate(False)

        chat_hint = tk.Frame(right_ph, bg=BG, padx=16, pady=20)
        chat_hint.pack(fill="x")
        tk.Label(chat_hint, text="AI Chat  (centre column)",
                 font=("Georgia", 13, "bold"),
                 bg=BG, fg=TEXT_PRIMARY,
                 anchor="w").pack(fill="x")
        tk.Label(chat_hint,
                 text=(
                     "Each follow-up retrieves the most relevant passages "
                     "from your KB pages. Answers are attributed to the page "
                 ),
                 font=("Segoe UI", 9),
                 bg=BG, fg=TEXT_MUTED,
                 justify="left", anchor="w",
                 wraplength=240).pack(fill="x", pady=(6, 0))
        tk.Frame(chat_hint, bg=BORDER, height=1).pack(fill="x", pady=12)
        tk.Label(chat_hint, text="Related Sources  (right column)",
                 font=("Georgia", 13, "bold"),
                 bg=BG, fg=TEXT_PRIMARY,
                 anchor="w").pack(fill="x")
        tk.Label(chat_hint,
                 text="Source pages appear as clickable cards.",
                 font=("Segoe UI", 9),
                 bg=BG, fg=TEXT_MUTED,
                 justify="left", anchor="w",
                 wraplength=240).pack(fill="x", pady=(6, 0))

    # ── Reader open / close ────────────────────────────────────────────────────
    def _open_reader(self):
        if not self._reader_open:
            self._reader.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._reader.lift()
            self._reader_open = True

    def _close_reader(self):
        if self._reader_open:
            self._reader.place_forget()
            self._reader_open = False

    def _load_settings_safe(self):
        s = load_settings()
        missing = [
            label for label, key in [
                ("Groq API Key",         "api_key"),
                ("Confluence Username",  "conf_username"),
                ("Confluence API Token", "conf_api_token"),
                ("Confluence Base URL",  "conf_base_url"),
            ] if not str(s.get(key, "")).strip()
        ]
        if missing:
            messagebox.showwarning(
                "Missing Configuration",
                "Please fill in the following in Settings:\n\n* "
                + "\n* ".join(missing), parent=self)
            return s, False
        return s, True

    def _test_connection(self):
        s, ok = self._load_settings_safe()
        if not ok:
            return
        self._test_btn.config(state="disabled", text="Testing...")
        self.status_var.set("Testing connection...")
        threading.Thread(target=self._test_worker, args=(s,), daemon=True).start()

    def _test_worker(self, settings):
        try:
            client = ConfluenceClient(
                base_url  = settings["conf_base_url"],
                username  = settings["conf_username"],
                api_token = settings["conf_api_token"],
            )
            result = client.test_connection()
            self.after(0, lambda r=result, c=client: self._show_test_ok(r, c))
        except ConnectionError as exc:
            self.after(0, lambda e=str(exc): self._show_test_fail(e))
        except Exception as exc:
            self.after(0, lambda e=str(exc):
                self._show_test_fail(f"Unexpected error:\n{e}"))
        finally:
            self.after(0, lambda: self._test_btn.config(
                state="normal", text="Test Connection"))

    def _show_test_ok(self, result, client):
        self._space_badge_var.set(
            f"Connected ({client._token_type})  .  Space: {client.space_key or '?'}")
        self._space_badge.config(fg=SUCCESS)
        self.status_var.set("Ready to search")
        if callable(self.on_client_ready):
            self.on_client_ready(client)

    def _show_test_fail(self, error_msg):
        self._space_badge_var.set("Connection failed")
        self._space_badge.config(fg=ERROR)
        self.status_var.set("Connection failed")
        messagebox.showerror("Connection Error", error_msg, parent=self)

    def _on_search(self):
        settings, ok = self._load_settings_safe()
        if not ok:
            return
        scenario = self._scenario_txt.get("1.0", tk.END).strip()
        if not scenario or scenario == self._scenario_txt._ph:
            messagebox.showinfo("No Scenario",
                "Please describe your scenario before searching.", parent=self)
            return
        self._settings_cache  = settings
        self._last_scenario   = scenario
        self._start_spinner()
        self._search_btn.config(state="disabled")
        self.status_var.set("Connecting to Confluence...")
        self._pages_var.set("")
        threading.Thread(
            target=self._worker, args=(settings, scenario), daemon=True).start()

    def _worker(self, settings, scenario):
        try:
            client = ConfluenceClient(
                base_url  = settings["conf_base_url"],
                username  = settings["conf_username"],
                api_token = settings["conf_api_token"],
            )
            self.after(0, lambda: self.status_var.set(
                f"Searching {client.space_key or 'all spaces'}..."))

            local_pages = []
            if self._use_local_first:
                try:
                    from kb_local_search import search_local, get_db_stats
                    stats = get_db_stats()
                    if stats["page_count"] > 0:
                        local_pages = search_local(
                            scenario, limit=10,
                            space_key=client.space_key)
                        if local_pages:
                            self.after(0, lambda n=len(local_pages):
                                self.status_var.set(
                                    f"Local: {n} pages -- AI analysing..."))
                except Exception:
                    pass

            pages = local_pages if local_pages else client.search_pages(scenario, limit=10)
            if not local_pages and self._use_local_first:
                self.after(0, lambda: self.status_var.set("Live search..."))

            self._pages_found = pages
            pl = f"{len(pages)} page(s) found" if pages else "No pages found"
            self.after(0, lambda p=pl, c=client: (
                self._pages_var.set(p),
                self._space_badge_var.set(
                    f"Connected  .  Space: {c.space_key or 'all'}"),
            ))
            self.after(0, lambda: self.status_var.set("AI analysing..."))
            answer = ask_kb_with_confluence(
                api_key  = settings["api_key"],
                model    = settings.get("groq_model", "llama-3.1-8b-instant"),
                scenario = scenario,
                pages    = pages,
            )
            self._last_answer = answer
            self.after(0, lambda a=answer, p=pages: self._on_answer_ready(a, p))
        except ConnectionError as exc:
            self.after(0, lambda e=str(exc): self._show_search_error(e))
        except Exception as exc:
            self.after(0, lambda e=str(exc): messagebox.showerror(
                "Error", e, parent=self))
        finally:
            self.after(0, self._stop_spinner)
            self.after(0, lambda: self._search_btn.config(state="normal"))

    def _on_answer_ready(self, answer: str, pages: list):
        self._reader.load(answer, pages, initial_query=self._last_scenario)
        self._open_reader()
        self.status_var.set(
            f"Done  .  {len(answer.split())} words  .  "
            f"{min(len(pages), MAX_PAGES_IN_PROMPT)}/{len(pages)} pages used")

    def _show_search_error(self, error_msg: str):
        self.status_var.set("Error")
        messagebox.showerror("Search Error", error_msg, parent=self)

    def _dispatch_chat(self, user_text: str, messages: list,
                        settings: dict, model: str, chat_panel):
        threading.Thread(
            target=self._chat_worker,
            args=(messages, settings, model, chat_panel),
            daemon=True,
        ).start()

    def _chat_worker(self, messages: list, settings: dict,
                      model: str, chat_panel):
        try:
            reply = _groq_chat(
                api_key    = settings["api_key"],
                model      = model,
                messages   = messages,
                max_tokens = CHAT_MAX_TOKENS,
            )
            self.after(0, lambda r=reply: chat_panel.add_ai_reply(r))
        except Exception as exc:
            self.after(0, lambda e=str(exc): chat_panel.add_error(e))

    def _copy_output(self):
        content = self._last_answer.strip() if self._last_answer else ""
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            old = self._copy_btn.cget("text")
            self._copy_btn.config(text="Copied!", fg=SUCCESS)
            self.after(2200, lambda: self._copy_btn.config(
                text=old, fg=TEXT_SECONDARY))
            self.status_var.set("Copied to clipboard")

    def _start_spinner(self):
        self._spinning = True
        self._tick_spinner()

    def _stop_spinner(self):
        self._spinning = False
        self._spinner_var.set("")

    def _tick_spinner(self):
        if not self._spinning:
            return
        self._spinner_var.set(
            self._spinner_frames[self._spin_idx % len(self._spinner_frames)])
        self._spin_idx += 1
        self.after(80, self._tick_spinner)