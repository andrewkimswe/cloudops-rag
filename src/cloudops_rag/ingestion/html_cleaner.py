"""HTML to cleaned markdown-like text conversion."""

from __future__ import annotations

from bs4 import BeautifulSoup


REMOVE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "header",
    "aside",
    "form",
    "svg",
    "button",
    "[role='navigation']",
    ".breadcrumbs",
    ".breadcrumb",
    ".feedback",
    ".toc",
]


def html_to_text(html: str, title: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in REMOVE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.body or soup
    lines: list[str] = []

    for tag in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "pre", "code", "tr"]):
        text = " ".join(tag.get_text(" ", strip=True).split())
        if not text:
            continue
        if text in {"Javascript is disabled or is unavailable in your browser."}:
            continue
        if tag.name == "h1":
            lines.append(f"# {text}")
        elif tag.name == "h2":
            lines.append(f"\n## {text}")
        elif tag.name == "h3":
            lines.append(f"\n### {text}")
        elif tag.name == "h4":
            lines.append(f"\n#### {text}")
        elif tag.name == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)

    cleaned = "\n".join(lines)
    cleaned = "\n".join(line.rstrip() for line in cleaned.splitlines())
    cleaned = "\n".join(line for line in cleaned.splitlines() if line.strip())
    if not cleaned.startswith("#"):
        cleaned = f"# {title}\n\n{cleaned}"
    return cleaned.strip() + "\n"

