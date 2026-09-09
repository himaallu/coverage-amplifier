import html
from html.parser import HTMLParser


class _SingleAnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchor_count = 0
        self.other_root_tags = 0
        self.depth = 0
        self.has_root_anchor = False
        self.outside_text = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.depth == 0:
            if tag == "a":
                self.has_root_anchor = True
                self.anchor_count += 1
            else:
                self.other_root_tags += 1
        elif tag == "a":
            self.anchor_count += 1
        self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.depth == 0 and data.strip():
            self.outside_text = True


def is_single_anchor_element(html_snippet: str) -> bool:
    """Validate that html_snippet is a single, self-contained <a> element."""
    snippet = html_snippet.strip()
    if not snippet.startswith("<a") or not snippet.endswith("</a>"):
        return False

    parser = _SingleAnchorParser()
    try:
        parser.feed(snippet)
        parser.close()
    except Exception:
        return False

    return (
        parser.has_root_anchor
        and parser.anchor_count == 1
        and parser.other_root_tags == 0
        and not parser.outside_text
        and parser.depth == 0
    )


def generate_badge_html(outlet: str, article_url: str | None = None) -> str:
    """Template-generate a single self-contained <a> badge element."""
    url = article_url.strip() if article_url and article_url.strip() else "#"

    safe_outlet = html.escape(outlet.strip() if outlet else "Media")
    safe_url = html.escape(url)
    return (
        f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer">'
        f"As featured in {safe_outlet}</a>"
    )
