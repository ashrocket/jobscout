"""Gmail-based LinkedIn job alert scraper.

Parses HTML content from LinkedIn "Jobs you may be interested in" emails
and returns structured job listings for the JobScout pipeline.

Usage:
    This scraper does NOT call Gmail APIs directly. Instead:
    1. Use Gmail MCP tools (gmail_search_messages + gmail_read_message) to
       fetch LinkedIn alert email HTML content.
    2. Pass that HTML to parse_alert_email() or LinkedInAlertScraper.search().

    Example from CLI / MCP orchestration layer:
        from jobscout.scrapers.gmail_alerts import parse_alert_email
        jobs = parse_alert_email(email_html)
"""

import re
from bs4 import BeautifulSoup

from jobscout.scrapers.base import BaseScraper

# Pattern to extract numeric job ID from LinkedIn URLs
_JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")

# LinkedIn job alert emails come from this address
LINKEDIN_ALERT_SENDER = "jobs-noreply@linkedin.com"


def _extract_job_id(url: str) -> str | None:
    """Extract numeric job ID from a LinkedIn job URL."""
    match = _JOB_ID_RE.search(url)
    return match.group(1) if match else None


def _clean_text(text: str | None) -> str:
    """Strip and normalise whitespace in extracted text."""
    if not text:
        return ""
    return " ".join(text.split()).strip()


def parse_alert_email(html: str) -> list[dict]:
    """Parse a LinkedIn job alert email and return structured job listings.

    Args:
        html: Raw HTML body of the LinkedIn alert email.

    Returns:
        List of dicts with keys: id, portal, url, title, company, location, raw_html
    """
    if not html or not html.strip():
        return []

    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen_ids: set[str] = set()

    # Strategy 1: Find links to /jobs/view/ — the most reliable signal.
    # LinkedIn alert emails wrap each job title in an <a> pointing to the job page.
    job_links = soup.find_all("a", href=_JOB_ID_RE)

    for link in job_links:
        href = link.get("href", "")
        job_id_num = _extract_job_id(href)
        if not job_id_num or job_id_num in seen_ids:
            continue

        title = _clean_text(link.get_text())
        if not title:
            continue

        seen_ids.add(job_id_num)

        # Normalise URL — strip tracking params, ensure full URL
        url = href.split("?")[0]
        if not url.startswith("http"):
            url = f"https://www.linkedin.com{url}"

        # Walk up from the link to find the enclosing job card container.
        # LinkedIn emails use nested tables; the job card is typically
        # a <td> or <div> ancestor that also contains company + location.
        company = ""
        location = ""
        card_html = ""

        card = _find_job_card(link)
        if card:
            card_html = str(card)
            company, location = _extract_company_location(card, title)

        job_id = f"linkedin-alert-{job_id_num}"
        results.append({
            "id": job_id,
            "portal": "linkedin-alert",
            "url": url,
            "title": title,
            "company": company or "Unknown",
            "location": location or "Unknown",
            "raw_html": card_html or str(link),
        })

    return results


def _find_job_card(link_tag) -> object | None:
    """Walk up the DOM from a job link to find the enclosing card element.

    LinkedIn alert emails are table-based. The job card is typically a <td>
    that contains the title link plus sibling text nodes for company/location.
    We look for a container that has enough text to include metadata.
    """
    # Walk up parents, looking for a container with multiple text segments
    current = link_tag.parent
    for _ in range(8):  # don't walk too far
        if current is None:
            break

        text = _clean_text(current.get_text())
        # A good card container has the title plus company/location info
        # (at least ~20 more chars beyond the title itself)
        title_text = _clean_text(link_tag.get_text())
        extra = len(text) - len(title_text)

        if extra > 15:
            # Check this isn't the entire email body
            all_job_links = current.find_all("a", href=_JOB_ID_RE)
            if len(all_job_links) <= 1:
                return current

        current = current.parent

    # Fallback: return the direct parent
    return link_tag.parent


def _extract_company_location(card, title: str) -> tuple[str, str]:
    """Extract company name and location from a job card element.

    LinkedIn alert emails vary in structure, so we try multiple strategies.
    """
    company = ""
    location = ""

    # Strategy A: Look for text blocks that aren't the title.
    # In LinkedIn alert emails, company and location are typically in
    # separate <span>, <p>, or <td> elements near the title link.
    text_blocks = []
    for el in card.find_all(["span", "p", "td", "div", "a"]):
        text = _clean_text(el.get_text())
        if not text or text == title:
            continue
        # Skip promotional text, buttons, unsubscribe links
        if any(skip in text.lower() for skip in [
            "unsubscribe", "view all", "see all", "privacy",
            "help center", "linkedin corporation", "apply now",
            "recommended for you", "similar jobs", "premium",
            "jobs you may", "copyright", "\u00a9",
        ]):
            continue
        # Skip very long text (probably a description, not metadata)
        if len(text) > 120:
            continue
        # Skip if it's a substring of the title (partial match from inner elements)
        if text in title and len(text) > 3:
            continue
        text_blocks.append(text)

    # Deduplicate while preserving order
    seen = set()
    unique_blocks = []
    for block in text_blocks:
        if block not in seen:
            seen.add(block)
            unique_blocks.append(block)

    # The first non-title text block is usually company, second is location
    if len(unique_blocks) >= 2:
        company = unique_blocks[0]
        location = unique_blocks[1]
    elif len(unique_blocks) == 1:
        company = unique_blocks[0]

    # Strategy B: If company looks like a location, swap
    location_indicators = [
        "remote", "united states", "usa", ", ca", ", ny", ", tx",
        ", wa", "san francisco", "new york", "seattle", "austin",
        "los angeles", "chicago", "boston", "denver",
    ]
    if company and any(ind in company.lower() for ind in location_indicators):
        if not location:
            location = company
            company = ""
        elif not any(ind in location.lower() for ind in location_indicators):
            company, location = location, company

    return company, location


class LinkedInAlertScraper(BaseScraper):
    """Scraper for LinkedIn job alert emails.

    Unlike other scrapers, this one doesn't fetch data from the web.
    Pass the email HTML body as the `query` parameter to search().
    Multiple emails can be passed by concatenating their HTML or by
    calling search() multiple times.
    """

    portal = "linkedin-alert"

    def search(self, query: str) -> list[dict]:
        """Parse a LinkedIn job alert email body.

        Args:
            query: HTML content of a LinkedIn job alert email.

        Returns:
            List of job dicts ready for insert_job().
        """
        return parse_alert_email(query)

    def close(self):
        pass


def fetch_and_parse_linkedin_alerts(email_bodies: list[str]) -> list[dict]:
    """Parse multiple LinkedIn alert email bodies and return all jobs.

    This is a convenience function for CLI / orchestration use.
    The caller is responsible for fetching email content via Gmail MCP tools:

        1. mcp__claude_ai_Gmail__gmail_search_messages(
               q='from:jobs-noreply@linkedin.com subject:"jobs" newer_than:1d'
           )
        2. For each message, mcp__claude_ai_Gmail__gmail_read_message(id=msg_id)
        3. Collect the HTML bodies and pass them here.

    Args:
        email_bodies: List of HTML strings from LinkedIn alert emails.

    Returns:
        Deduplicated list of job dicts.
    """
    scraper = LinkedInAlertScraper()
    all_jobs: list[dict] = []
    seen_ids: set[str] = set()

    for body in email_bodies:
        jobs = scraper.search(body)
        for job in jobs:
            if job["id"] not in seen_ids:
                seen_ids.add(job["id"])
                all_jobs.append(job)

    return all_jobs
