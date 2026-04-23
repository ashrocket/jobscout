"""Auto-apply to Greenhouse job postings using Playwright.

Usage:
    python -m jobscout.apply_greenhouse --job-id greenhouse-anthropic-4902636008
    python -m jobscout.apply_greenhouse --all-tuned
    python -m jobscout.apply_greenhouse --dry-run --job-id greenhouse-gusto-7577659
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, Frame

try:
    from playwright_stealth import Stealth
    _HAS_STEALTH = True
except ImportError:
    _HAS_STEALTH = False

from jobscout.config import get_candidate

DATA_DIR = Path(__file__).parent.parent / "data"
TAILORED_DIR = DATA_DIR / "tailored"


def find_resume_pdf(job_id: str) -> Path | None:
    pdf = TAILORED_DIR / f"{job_id}.pdf"
    if pdf.exists():
        return pdf
    html = TAILORED_DIR / f"{job_id}.html"
    if html.exists():
        return html
    return None


def get_cover_letter(job_id: str) -> str | None:
    """Load cover letter from data/cover_letters/{job_id}.txt if it exists."""
    cl_path = DATA_DIR / "cover_letters" / f"{job_id}.txt"
    if cl_path.exists():
        return cl_path.read_text().strip()
    return None


def dismiss_cookie_banner(page: Page):
    """Dismiss common cookie-consent banners that intercept pointer events.

    Toast (Osano), Cookiebot, OneTrust, TrustArc, and custom rails consent modals
    block clicks on the Apply button until dismissed. Try a list of known
    accept/reject selectors; swallow failures silently.
    """
    selectors = [
        'button#onetrust-accept-btn-handler',
        'button#onetrust-reject-all-handler',
        'button.osano-cm-accept-all',
        'button.osano-cm-accept',
        'button.osano-cm-denyAll',
        'button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll',
        'button#CybotCookiebotDialogBodyButtonAccept',
        'button[aria-label*="Accept" i]',
        'button[aria-label*="Agree" i]',
        'button:has-text("Accept All")',
        'button:has-text("Accept all")',
        'button:has-text("Accept cookies")',
        'button:has-text("I agree")',
        'button:has-text("Got it")',
        '.consent-modal button:has-text("Accept")',
        '.consent-modal button:has-text("Agree")',
    ]
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click(timeout=2000)
                print(f"  Dismissed cookie banner via {sel}")
                time.sleep(1)
                return True
        except Exception:
            continue
    return False


def find_greenhouse_frame(page: Page):
    """Find the Greenhouse application form, handling iframes and direct forms."""
    # Strategy 1: Click Apply button to scroll/reveal form
    apply_btn = page.query_selector('button:has-text("Apply")')
    if apply_btn:
        apply_btn.click()
        time.sleep(2)

    # Strategy 2: Use frame_locator for Greenhouse iframe (recommended approach)
    for selector in ['#grnhse_iframe', 'iframe[src*="greenhouse"]', 'iframe[src*="grnh"]']:
        try:
            fl = page.frame_locator(selector)
            # Test if frame has content
            fl.locator('input').first.wait_for(timeout=5000)
            print(f"  Found form via frame_locator({selector})")
            return fl, "frame_locator"
        except Exception:
            continue

    # Strategy 3: Access iframe via content_frame()
    for iframe in page.query_selector_all('iframe'):
        frame = iframe.content_frame()
        if frame:
            try:
                frame.wait_for_selector('input', timeout=3000)
                print("  Found form via content_frame()")
                return frame, "frame"
            except Exception:
                continue

    # Strategy 4: Form directly on page (no iframe)
    if page.query_selector('form input[type="text"]'):
        print("  Found form directly on page")
        return page, "page"

    return None, None


def fill_greenhouse_form(page: Page, job_url: str, job_id: str, dry_run: bool = False):
    """Navigate to a Greenhouse job posting and fill out the application form."""
    CANDIDATE = get_candidate()
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Applying to: {job_url}")

    page.goto(job_url, wait_until="networkidle", timeout=30000)
    time.sleep(3)

    dismiss_cookie_banner(page)

    form_ctx, ctx_type = find_greenhouse_frame(page)
    if not form_ctx:
        print("  ERROR: Could not find application form")
        return False

    print("  Found application form")

    # Build locator helper that works with both frame_locator and frame/page
    def loc(selector):
        if ctx_type == "frame_locator":
            return form_ctx.locator(selector)
        else:
            return form_ctx.locator(selector) if hasattr(form_ctx, 'locator') else None

    def fill_field(selector, value, label=""):
        try:
            el = loc(selector)
            if el and el.count() > 0:
                el.first.fill(value)
                print(f"  Filled: {label or selector} = {value}")
                return True
        except Exception:
            pass
        return False

    # Fill basic fields — try Greenhouse standard names, then fallback to labels
    fill_field('input[name="job_application[first_name]"]', CANDIDATE["first_name"], "First Name") or \
        fill_field('#first_name', CANDIDATE["first_name"], "First Name")

    fill_field('input[name="job_application[last_name]"]', CANDIDATE["last_name"], "Last Name") or \
        fill_field('#last_name', CANDIDATE["last_name"], "Last Name")

    fill_field('input[name="job_application[email]"]', CANDIDATE["email"], "Email") or \
        fill_field('#email', CANDIDATE["email"], "Email")

    fill_field('input[name="job_application[phone]"]', CANDIDATE["phone"], "Phone") or \
        fill_field('#phone', CANDIDATE["phone"], "Phone")

    fill_field('input[name="job_application[location]"]', CANDIDATE["location"], "Location")

    # LinkedIn URL
    fill_field('input[name*="linkedin"]', CANDIDATE["linkedin"], "LinkedIn") or \
        fill_field('input[placeholder*="LinkedIn"]', CANDIDATE["linkedin"], "LinkedIn")

    # Website
    fill_field('input[name*="website"]', CANDIDATE["website"], "Website") or \
        fill_field('input[placeholder*="Website"]', CANDIDATE["website"], "Website")

    # Upload resume
    resume_path = find_resume_pdf(job_id)
    if resume_path:
        try:
            file_input = loc('input[type="file"]')
            if file_input and file_input.count() > 0:
                file_input.first.set_input_files(str(resume_path))
                print(f"  Uploaded resume: {resume_path.name}")
                time.sleep(2)
            else:
                print(f"  WARNING: Resume ready ({resume_path.name}) but no file upload field found")
        except Exception as e:
            print(f"  WARNING: Resume upload failed: {e}")
    else:
        print(f"  WARNING: No resume found for {job_id}")

    # Fill cover letter
    cover_letter = get_cover_letter(job_id)
    if cover_letter:
        filled = fill_field('textarea[name*="cover_letter"]', cover_letter, "Cover Letter") or \
            fill_field('textarea[name*="cover"]', cover_letter, "Cover Letter")
        if not filled:
            print(f"  Cover letter will be placed in 'Why' textarea below")

    # Handle country field (often an autocomplete text input, not a select)
    try:
        country_input = loc('#country, input[id="country"], input[name*="country"]')
        if country_input and country_input.count() > 0:
            country_input.first.fill("United States")
            country_input.first.press("ArrowDown")
            time.sleep(0.5)
            country_input.first.press("Enter")
            print(f"  Filled: Country = United States")
    except Exception as e:
        print(f"  WARNING: Country field issue: {e}")

    # Handle yes/no dropdowns (work authorization, etc.)
    try:
        selects = loc('select')
        if selects:
            for i in range(selects.count()):
                sel = selects.nth(i)
                current = sel.evaluate('el => el.value')
                if current:
                    continue  # Already filled (e.g. country)
                options = sel.locator('option').all_inner_texts()
                if 'Yes' in options:
                    sel.select_option(label="Yes")
                    print(f"  Selected 'Yes' for dropdown #{i+1}")
    except Exception:
        pass

    # Handle custom text questions common on Greenhouse forms
    custom_answers = {
        "earliest": "Immediately / 2 weeks notice",
        "start": "Immediately / 2 weeks notice",
        "soonest": "Immediately / 2 weeks notice",
        "relocat": "Yes, open to relocation",
        "deadline": "No specific deadlines",
        "timeline": "Available immediately, flexible on start date",
        "salary": "Open to discussion",
        "compensation": "Open to discussion",
        "hear about": "Company careers page",
        "how did you": "Company careers page",
        "know anyone": "",
        "address from which": CANDIDATE.get("location", ""),
        "address": CANDIDATE.get("location", ""),
        "working from": CANDIDATE.get("location", ""),
        "plan on working": CANDIDATE.get("location", ""),
        "in person": "Yes",
        "on-site": "Yes",
        "onsite": "Yes",
        "office": "Yes",
        "in the office": "Yes",
        "hybrid": "Yes",
        "sponsor": "No, I am authorized to work in the US",
        "authorized": "Yes",
        "legally": "Yes",
    }

    # Find all labeled inputs/textareas/selects that are empty and try to answer them
    try:
        labels = loc('label')
        if labels:
            for i in range(min(labels.count(), 40)):
                try:
                    label = labels.nth(i)
                    label_text = label.inner_text().strip().lower()
                    if not label_text or len(label_text) < 3:
                        continue

                    label_for = label.get_attribute('for') or ''
                    if not label_for:
                        continue

                    input_el = loc(f'#{label_for}')
                    if not input_el or input_el.count() == 0:
                        continue

                    el = input_el.first
                    tag = el.evaluate('el => el.tagName').lower()

                    # Handle select dropdowns
                    if tag == 'select':
                        current_select = el.evaluate('el => el.value')
                        if current_select:
                            continue
                        options = el.locator('option').all_inner_texts()
                        # Check custom answers first
                        matched = False
                        for keyword, answer in custom_answers.items():
                            if keyword in label_text and answer:
                                # Try to find matching option
                                for opt in options:
                                    if answer.lower() in opt.lower() or opt.lower() in answer.lower():
                                        el.select_option(label=opt)
                                        print(f"  Custom select: '{label_text[:50]}' → '{opt}'")
                                        matched = True
                                        break
                                if matched:
                                    break
                        if not matched and 'Yes' in options:
                            # Default yes/no to Yes for authorization-type questions
                            auth_keywords = ['authorized', 'legal', 'open to', 'willing', 'in person', 'office', 'onsite', 'hybrid', 'relocat']
                            if any(kw in label_text for kw in auth_keywords):
                                el.select_option(label='Yes')
                                print(f"  Auto-select Yes: '{label_text[:50]}'")
                        continue

                    # Handle text inputs and textareas
                    if tag in ('input', 'textarea'):
                        current_val = el.input_value()
                        if current_val:
                            continue

                        # Check if it's a React Select combobox
                        role = el.get_attribute('role') or ''
                        is_combobox = role == 'combobox'

                        # Use most specific keyword match (longest keyword that matches)
                        best_match = None
                        best_len = 0
                        for keyword, answer in custom_answers.items():
                            if keyword in label_text and answer and len(keyword) > best_len:
                                best_match = answer
                                best_len = len(keyword)
                        if best_match:
                            if is_combobox:
                                # React Select: type answer, wait for dropdown, press Enter
                                el.click()
                                time.sleep(0.3)
                                el.fill(best_match)
                                time.sleep(0.5)
                                el.press("ArrowDown")
                                time.sleep(0.3)
                                el.press("Enter")
                                print(f"  Custom select: '{label_text[:50]}' → '{best_match}'")
                            else:
                                el.fill(best_match)
                                print(f"  Custom Q: '{label_text[:50]}' → '{best_match}'")
                except Exception:
                    continue
    except Exception:
        pass

    # Fill LinkedIn — search by label text since Greenhouse uses dynamic IDs
    try:
        linkedin_filled = False
        linkedin_inputs = loc('input[name*="linkedin"], input[placeholder*="linkedin" i], input[id*="linkedin" i]')
        if linkedin_inputs and linkedin_inputs.count() > 0:
            for i in range(linkedin_inputs.count()):
                inp = linkedin_inputs.nth(i)
                if not inp.input_value():
                    inp.fill(CANDIDATE["linkedin"])
                    print(f"  Filled LinkedIn field (by attr)")
                    linkedin_filled = True
        if not linkedin_filled:
            # Search by label text
            labels = loc('label')
            if labels:
                for i in range(labels.count()):
                    lt = labels.nth(i).inner_text().strip().lower()
                    if 'linkedin' in lt:
                        label_for = labels.nth(i).get_attribute('for')
                        if label_for:
                            inp = loc(f'#{label_for}')
                            if inp and inp.count() > 0 and not inp.first.input_value():
                                inp.first.fill(CANDIDATE["linkedin"])
                                print(f"  Filled LinkedIn field (by label)")
                        break
    except Exception:
        pass

    # Fill "Why [Company]?" and "Additional Information" textareas
    additional_info = CANDIDATE.get("application_disclosure", "")
    if cover_letter:
        try:
            textareas = loc('textarea')
            if textareas:
                for i in range(textareas.count()):
                    ta = textareas.nth(i)
                    current = ta.input_value()
                    if current:
                        continue
                    ta_id = ta.get_attribute('id') or ''
                    if ta_id:
                        assoc_label = loc(f'label[for="{ta_id}"]')
                        if assoc_label and assoc_label.count() > 0:
                            lt = assoc_label.first.inner_text().lower()
                            if any(kw in lt for kw in ['why', 'interest', 'motivation', 'what excites', 'what attracts']):
                                ta.fill(cover_letter)
                                print(f"  Filled 'Why' textarea with cover letter")
                            elif 'additional' in lt or 'anything else' in lt:
                                ta.fill(additional_info)
                                print(f"  Filled 'Additional Info' with AI disclosure")
        except Exception:
            pass

    # Fill remaining required comboboxes and fields that weren't caught above
    additional_answers = {
        "interviewed": "No",
        "coding language": "Ruby",
        "language preference": "Ruby",
        "years of professional": "Yes",
        "at least": "Yes",
        "ai policy": "Yes",
        "acknowledge": "Yes",
        "experience": "Yes",
        "currently employed": "Yes",
    }
    # Merge with existing custom_answers
    custom_answers.update(additional_answers)

    # Second pass: fill any remaining empty required fields
    try:
        labels = loc('label')
        if labels:
            for i in range(min(labels.count(), 50)):
                try:
                    label = labels.nth(i)
                    label_text = label.inner_text().strip().lower()
                    if not label_text or len(label_text) < 3:
                        continue
                    label_for = label.get_attribute('for') or ''
                    if not label_for:
                        continue
                    input_el = loc(f'#{label_for}')
                    if not input_el or input_el.count() == 0:
                        continue
                    el = input_el.first
                    required = el.get_attribute('aria-required') or ''
                    if required != 'true':
                        continue
                    tag = el.evaluate('el => el.tagName').lower()
                    role = el.get_attribute('role') or ''
                    current_val = ''
                    try:
                        current_val = el.input_value()
                    except Exception:
                        pass
                    if current_val:
                        continue
                    # Try to find an answer
                    best_match = None
                    best_len = 0
                    for keyword, answer in custom_answers.items():
                        if keyword in label_text and answer and len(keyword) > best_len:
                            best_match = answer
                            best_len = len(keyword)
                    if best_match:
                        if role == 'combobox':
                            el.click()
                            time.sleep(0.3)
                            el.fill(best_match)
                            time.sleep(0.5)
                            el.press("ArrowDown")
                            time.sleep(0.3)
                            el.press("Enter")
                            print(f"  2nd pass select: '{label_text[:50]}' → '{best_match}'")
                        elif tag in ('input', 'textarea'):
                            el.fill(best_match)
                            print(f"  2nd pass fill: '{label_text[:50]}' → '{best_match}'")
                except Exception:
                    continue
    except Exception:
        pass

    if dry_run:
        print("  [DRY RUN] Form filled — NOT submitting")
        print("  Taking screenshot...")
        page.screenshot(path=str(DATA_DIR / f"apply-screenshot-{job_id}.png"), full_page=True)
        return True

    # Submit
    try:
        submit = loc('button[type="submit"], input[type="submit"]')
        if submit and submit.count() > 0:
            submit.first.click()
            print("  SUBMITTED!")
            time.sleep(5)
            page.screenshot(path=str(DATA_DIR / f"apply-confirmed-{job_id}.png"), full_page=True)
            return True
        else:
            print("  ERROR: Could not find submit button")
            return False
    except Exception as e:
        print(f"  ERROR submitting: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Auto-apply to Greenhouse jobs")
    parser.add_argument("--job-id", help="Specific job ID (e.g. greenhouse-anthropic-4902636008)")
    parser.add_argument("--all-tuned", action="store_true", help="Apply to all tuned jobs")
    parser.add_argument("--dry-run", action="store_true", help="Fill forms but don't submit")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    args = parser.parse_args()

    # Build job list
    from jobscout.db import init_db, get_job, get_jobs_by_status
    conn = init_db(DATA_DIR / "jobscout.db")

    if args.job_id:
        job = get_job(conn, args.job_id)
        if not job:
            print(f"Job {args.job_id} not found in database")
            sys.exit(1)
        jobs = [job]
    elif args.all_tuned:
        jobs = get_jobs_by_status(conn, "tuned")
    else:
        parser.print_help()
        sys.exit(1)

    print(f"Found {len(jobs)} job(s) to apply to")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        context = browser.new_context()
        if _HAS_STEALTH:
            Stealth().apply_stealth_sync(context)
            print("  Stealth mode enabled")
        page = context.new_page()

        results = {"success": 0, "failed": 0, "skipped": 0}

        for job in jobs:
            job_id = job["id"]
            url = job["url"]
            title = job["title"]

            if not url:
                print(f"  Skipping {job_id}: no URL")
                results["skipped"] += 1
                continue

            print(f"\n--- {title} ({job_id}) ---")
            try:
                ok = fill_greenhouse_form(page, url, job_id, dry_run=args.dry_run)
                if ok:
                    results["success"] += 1
                    if not args.dry_run:
                        from jobscout.db import update_job_status
                        update_job_status(conn, job_id, "applied")
                else:
                    results["failed"] += 1
            except Exception as e:
                print(f"  ERROR: {e}")
                results["failed"] += 1

        browser.close()

    print(f"\nResults: {results['success']} applied, {results['failed']} failed, {results['skipped']} skipped")


if __name__ == "__main__":
    main()
