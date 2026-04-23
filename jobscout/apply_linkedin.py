"""Auto-apply to LinkedIn Easy Apply jobs using patchright (stealth Playwright).

Usage:
    python3 -m jobscout.apply_linkedin --job-id linkedin-alert-4379693068
    python3 -m jobscout.apply_linkedin --job-id <id> --dry-run
    python3 -m jobscout.apply_linkedin --top 5           # best-scored unapplied
    python3 -m jobscout.apply_linkedin --headed          # show window (default)
    python3 -m jobscout.apply_linkedin --headless        # hidden

Notes:
- Uses patchright (drop-in stealth Playwright).
- Persistent user_data_dir at data/chrome-profile/linkedin/ so LinkedIn
  sees a consistent browser identity across runs.
- Loads li_at from ~/.env/ashcode/jobscout/linkedin-cookie.
- Unknown questions escalate to LLM (task="apply_q") using candidate
  profile + job context.
- Dry-run fills the modal but stops before the final Submit click.
"""
import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from patchright.sync_api import sync_playwright
from jobscout.config import DATA_DIR, SOURCES_DIR, read_credential, get_candidate, get_resume_map
from jobscout.db import init_db, get_job, get_jobs_by_status, update_job_status
from jobscout.llm import call_llm

DB_PATH = DATA_DIR / "jobscout.db"
PROFILE_DIR = DATA_DIR / "chrome-profile" / "linkedin"
TAILORED_DIR = DATA_DIR / "tailored"
CONFIRM_DIR = DATA_DIR


def _build_apply_q_system() -> str:
    c = get_candidate()
    name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or "the candidate"
    yrs = c.get("years_experience", "20+")
    salary = c.get("salary_expectation", "250000")
    return f"""You are an application-form answering assistant for {name}.
Given a LinkedIn Easy Apply question, the input type (text/number/select/radio),
available options (if any), and the candidate's profile, return ONLY the answer value.
Rules:
- Numbers-only questions: return digits only (no $, commas, units).
- Years-of-experience questions: use the closest match based on {yrs} years.
- Salary/compensation questions: use {salary} unless context suggests hourly (then 150).
- Authorization: Yes. Sponsorship: No.
- Identity questions (EEO, race, gender, veteran, disability): "I don't wish to answer" or "Prefer not to say".
- Radio/select: return one of the provided options exactly.
- If multi-word yes/no variant: match tone (e.g. "Yes, I am" if that's the option).
Return the bare answer on one line."""


def human_pause(min_s=0.5, max_s=1.8):
    time.sleep(random.uniform(min_s, max_s))


def load_cookie_context(pw, headless: bool, seed_cookie: bool = False):
    """Launch a persistent patchright context.

    The persistent user_data_dir keeps the full cookie jar (li_at + JSESSIONID +
    bcookie + bscookie + ...) across runs. First-time use requires `--login` to
    sign in interactively. li_at alone is not enough for Easy Apply sessions.
    """
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless,
        viewport={"width": 1400, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
        args=["--disable-blink-features=AutomationControlled"],
    )
    if seed_cookie:
        try:
            li_at = read_credential("linkedin-cookie").strip()
            if li_at.startswith("li_at="):
                li_at = li_at.split("=", 1)[1]
            ctx.add_cookies([{
                "name": "li_at", "value": li_at,
                "domain": ".linkedin.com", "path": "/",
                "httpOnly": True, "secure": True, "sameSite": "Lax",
            }])
        except Exception as e:
            print(f"  [warn] could not seed li_at: {e}")
    return ctx


def run_login(pw, poll_timeout_s: int = 300):
    """Open headed browser for manual LinkedIn login. Profile persists after close.

    Polls the page URL; exits once the user reaches /feed/ or /in/<profile>.
    """
    ctx = load_cookie_context(pw, headless=False, seed_cookie=False)
    page = ctx.new_page()
    page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
    print(f"\n  Browser opened. Log into LinkedIn in the window.")
    print(f"  Waiting up to {poll_timeout_s}s for you to land on /feed/ ...\n")

    start = time.time()
    while time.time() - start < poll_timeout_s:
        try:
            url = page.url
            if any(marker in url for marker in ("/feed/", "/mynetwork/", "/notifications/", "/in/")):
                print(f"  ✓ Logged in — URL: {url[:120]}")
                time.sleep(2)  # let cookies settle
                print("  ✓ Session saved to", PROFILE_DIR)
                ctx.close()
                return
        except Exception:
            pass
        time.sleep(3)

    print("  ⚠ Timed out waiting for login. Run --login again if needed.")
    ctx.close()


def find_resume(job_id: str) -> Path | None:
    for ext in (".pdf", ".html"):
        p = TAILORED_DIR / f"{job_id}{ext}"
        if p.exists():
            return p
    resume_map = get_resume_map()
    default = resume_map.get("default", "resume.pdf")
    for ext in (".pdf", ".html"):
        name = Path(default).stem + ext
        p = SOURCES_DIR / name
        if p.exists():
            return p
    return None


def llm_answer(question: str, input_type: str, options: list[str], job_ctx: dict) -> str:
    profile_str = json.dumps(get_candidate(), indent=2)
    opts_str = ("\n".join(f"- {o}" for o in options)) if options else "(none)"
    prompt = (
        f"Question: {question}\n"
        f"Input type: {input_type}\n"
        f"Options:\n{opts_str}\n\n"
        f"Job: {job_ctx.get('title','')} at {job_ctx.get('company','')}\n\n"
        f"Candidate profile:\n{profile_str}\n"
    )
    resp = call_llm(task="apply_q", system=_build_apply_q_system(), prompt=prompt, conn=None)
    return resp.text.strip().splitlines()[0]


def answer_known(question: str) -> str | None:
    """Fast-path for questions we can answer without an LLM call."""
    c = get_candidate()
    q = question.lower()
    if "first name" in q:
        return c.get("first_name", "")
    if "last name" in q:
        return c.get("last_name", "")
    if "email" in q:
        return c.get("email", "")
    if "phone" in q and "country" in q:
        return c.get("phone_country", "")
    if "mobile" in q or "phone" in q:
        return c.get("phone", "")
    if "linkedin" in q and ("url" in q or "profile" in q):
        return c.get("linkedin", "")
    if "city" in q:
        return c.get("city", "")
    if "state" in q or "province" in q:
        return c.get("state", "")
    if "country" in q:
        return c.get("country", "")
    if any(k in q for k in ["authorized to work", "legally authorized", "work authorization", "us work authorization"]):
        return c.get("authorized_us", "Yes")
    if any(k in q for k in ["require sponsorship", "need sponsorship", "visa sponsorship"]):
        return c.get("needs_sponsorship", "No")
    if "years of experience" in q or "how many years" in q:
        return c.get("years_experience", "")
    if "salary" in q or "compensation" in q or "expected pay" in q:
        return c.get("salary_expectation", "")
    if "veteran" in q:
        return c.get("veteran", "I don't wish to answer")
    if "disability" in q:
        return c.get("disability", "I don't wish to answer")
    if "gender" in q or "race" in q or "ethnicity" in q:
        return c.get("gender", "Prefer not to say")
    return None


def get_label_for(page, el_handle) -> str:
    """Return the best-effort text label associated with an input/select."""
    try:
        el_id = el_handle.get_attribute("id")
        if el_id:
            label = page.query_selector(f'label[for="{el_id}"]')
            if label:
                return (label.inner_text() or "").strip()
        # Walk up to form element container
        parent = el_handle.evaluate_handle("el => el.closest('[data-test-form-element],[data-test-single-line-text-form-component],[data-test-text-entity-list-form-component]')")
        if parent:
            txt = parent.evaluate("el => el.innerText")
            if txt:
                return txt.strip().splitlines()[0]
    except Exception:
        pass
    return ""


def fill_modal_step(page, job_ctx: dict, resume_path: Path | None) -> int:
    """Fill visible fields in the current modal step. Returns count filled."""
    filled = 0
    modal = page.query_selector('[role="dialog"]') or page

    # Resume upload (if present and resume available)
    if resume_path:
        try:
            file_input = modal.query_selector('input[type="file"]')
            if file_input and file_input.is_visible():
                file_input.set_input_files(str(resume_path))
                print(f"  Uploaded resume: {resume_path.name}")
                human_pause(1, 2)
                filled += 1
        except Exception:
            pass

    # Text / number / tel inputs
    for inp in modal.query_selector_all('input[type="text"], input[type="tel"], input[type="email"], input[type="number"]'):
        try:
            if not inp.is_visible() or not inp.is_enabled():
                continue
            cur = inp.input_value() or ""
            if cur.strip():
                continue
            label = get_label_for(page, inp)
            if not label:
                continue
            ans = answer_known(label)
            if ans is None:
                ans = llm_answer(label, "text", [], job_ctx)
            inp.fill(str(ans))
            print(f"  Filled text: {label[:60]} = {ans[:40]}")
            human_pause(0.3, 0.8)
            filled += 1
        except Exception as e:
            print(f"  [text err] {e}")

    # Textareas
    for ta in modal.query_selector_all('textarea'):
        try:
            if not ta.is_visible():
                continue
            if (ta.input_value() or "").strip():
                continue
            label = get_label_for(page, ta)
            ans = answer_known(label) if label else None
            if ans is None and label:
                ans = llm_answer(label, "textarea", [], job_ctx)
            if ans:
                ta.fill(str(ans))
                print(f"  Filled textarea: {label[:60]}")
                filled += 1
        except Exception:
            pass

    # Selects
    for sel in modal.query_selector_all('select'):
        try:
            if not sel.is_visible():
                continue
            cur = sel.input_value()
            if cur and cur.lower() not in ("select an option", "--"):
                continue
            label = get_label_for(page, sel)
            options = [o.inner_text().strip() for o in sel.query_selector_all('option')
                       if o.get_attribute('value')]
            if not options:
                continue
            ans = answer_known(label) if label else None
            if ans is None and label:
                ans = llm_answer(label, "select", options, job_ctx)
            if not ans:
                continue
            # Fuzzy match to an option
            match = _fuzzy_option(ans, options)
            if match:
                sel.select_option(label=match)
                print(f"  Selected: {label[:50]} → {match[:40]}")
                human_pause(0.3, 0.7)
                filled += 1
        except Exception as e:
            print(f"  [select err] {e}")

    # Radio groups
    for group in modal.query_selector_all('fieldset[data-test-form-builder-radio-button-form-component], fieldset'):
        try:
            if not group.is_visible():
                continue
            legend = group.query_selector('legend')
            question = (legend.inner_text().strip() if legend else "") or ""
            radios = group.query_selector_all('input[type="radio"]')
            if not radios:
                continue
            if any(r.is_checked() for r in radios):
                continue
            options = []
            for r in radios:
                rid = r.get_attribute("id")
                lbl = group.query_selector(f'label[for="{rid}"]') if rid else None
                options.append((r, (lbl.inner_text().strip() if lbl else r.get_attribute("value") or "")))
            ans = answer_known(question)
            if ans is None:
                ans = llm_answer(question, "radio", [o[1] for o in options], job_ctx)
            match = _fuzzy_option(ans, [o[1] for o in options])
            if match:
                for r, lbl in options:
                    if lbl == match:
                        r.check()
                        print(f"  Radio: {question[:50]} → {match[:40]}")
                        filled += 1
                        break
                human_pause(0.3, 0.7)
        except Exception:
            pass

    return filled


def _fuzzy_option(answer: str, options: list[str]) -> str | None:
    a = answer.lower().strip()
    for o in options:
        if o.lower() == a:
            return o
    for o in options:
        if a in o.lower() or o.lower() in a:
            return o
    # number substring match
    if a.isdigit():
        for o in options:
            if a in re.sub(r'[^0-9]', '', o):
                return o
    return None


def click_easy_apply(page) -> bool:
    """Click the top Easy Apply button on the job page."""
    for sel in [
        'button.jobs-apply-button',
        'button[aria-label*="Easy Apply" i]',
        'button:has-text("Easy Apply")',
    ]:
        btn = page.query_selector(sel)
        if btn and btn.is_visible():
            btn.click()
            human_pause(1.5, 2.5)
            return True
    return False


def advance_modal(page, dry_run: bool) -> str:
    """Click Next/Review/Submit. Returns 'next','review','submit','done','stuck'."""
    modal = page.query_selector('[role="dialog"]')
    if not modal:
        return "done"
    for text, label in [("Submit application", "submit"), ("Review", "review"), ("Next", "next"), ("Continue", "next")]:
        btn = modal.query_selector(f'button:has-text("{text}")')
        if btn and btn.is_visible() and btn.is_enabled():
            if label == "submit" and dry_run:
                print("  [DRY RUN] Stopping before final Submit")
                return "done"
            btn.click()
            print(f"  Clicked: {text}")
            human_pause(1.5, 3)
            return label
    return "stuck"


def apply_to_job(page, job: dict, dry_run: bool) -> str:
    """Apply to one LinkedIn job. Returns 'applied','dry','failed','skipped'."""
    url = job["url"].split("?")[0].rstrip("/")
    if "/jobs/view/" not in url:
        return "skipped"
    # LinkedIn tracking /comm/ prefix loops; use clean path
    url = url.replace("/comm/jobs/view/", "/jobs/view/")
    print(f"\n--- {job['title'][:70]} ---\n  {url}")
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    human_pause(2.5, 4)

    # Dismiss any cookie or popup
    for sel in ['button[aria-label*="Dismiss" i]', 'button:has-text("Accept")']:
        b = page.query_selector(sel)
        if b and b.is_visible():
            try: b.click(); human_pause(0.5, 1)
            except Exception: pass

    if not click_easy_apply(page):
        print("  No Easy Apply button found (external ATS?)")
        return "skipped"

    resume = find_resume(job["id"])
    job_ctx = {"title": job.get("title", ""), "company": job.get("company", "")}

    max_steps = 8
    for step in range(max_steps):
        fill_modal_step(page, job_ctx, resume)
        state = advance_modal(page, dry_run)
        if state in ("done", "stuck"):
            break

    # Verify success
    success = page.query_selector('h3:has-text("Your application was sent"), h2:has-text("Application sent")')
    if success and not dry_run:
        shot = CONFIRM_DIR / f"apply-confirmed-{job['id']}.png"
        page.screenshot(path=str(shot))
        print(f"  ✓ SUBMITTED — screenshot: {shot.name}")
        return "applied"
    if dry_run:
        shot = CONFIRM_DIR / f"apply-dry-{job['id']}.png"
        page.screenshot(path=str(shot))
        print(f"  [DRY] filled modal — screenshot: {shot.name}")
        return "dry"
    print("  Could not verify success")
    return "failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-id", help="Specific job id to apply to")
    ap.add_argument("--top", type=int, help="Top N tuned LinkedIn-alert jobs by score")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--headed", action="store_true", default=True)
    ap.add_argument("--login", action="store_true", help="One-time headed login to seed session")
    ap.add_argument("--cdp", default=None, metavar="URL",
                    help="Attach to running Chrome via CDP (e.g. http://localhost:9222). "
                         "Start Chrome with --remote-debugging-port=9222 first.")
    args = ap.parse_args()

    if args.login:
        with sync_playwright() as pw:
            run_login(pw)
        return

    conn = init_db(DB_PATH)

    if args.job_id:
        job = get_job(conn, args.job_id)
        if not job:
            print(f"Job {args.job_id} not found")
            sys.exit(1)
        jobs = [job]
    elif args.top:
        all_tuned = get_jobs_by_status(conn, "tuned")
        linkedin_tuned = [j for j in all_tuned if j["portal"] in ("linkedin", "linkedin-alert")]
        linkedin_tuned.sort(key=lambda j: (j.get("score") or 0), reverse=True)
        jobs = linkedin_tuned[: args.top]
    else:
        ap.print_help()
        sys.exit(1)

    print(f"Applying to {len(jobs)} LinkedIn job(s). dry_run={args.dry_run}")

    with sync_playwright() as pw:
        if args.cdp:
            print(f"  Attaching to Chrome via CDP at {args.cdp}")
            browser = pw.chromium.connect_over_cdp(args.cdp)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            cdp_mode = True
        else:
            ctx = load_cookie_context(pw, headless=args.headless, seed_cookie=False)
            page = ctx.new_page()
            cdp_mode = False

        print("  Warming session...")
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=45000)
        human_pause(2, 4)
        if "login" in page.url or "authwall" in page.url:
            print(f"  ✗ Session invalid — run: python3 -m jobscout.apply_linkedin --login "
                  f"(or start Chrome logged-in with --remote-debugging-port=9222 and use --cdp)")
            if not cdp_mode:
                ctx.close()
            sys.exit(1)
        else:
            print(f"  Session OK: {page.url[:80]}")
        results = {"applied": 0, "dry": 0, "failed": 0, "skipped": 0}
        for job in jobs:
            try:
                r = apply_to_job(page, job, args.dry_run)
                results[r] += 1
                if r == "applied":
                    update_job_status(conn, job["id"], "applied")
            except Exception as e:
                print(f"  ERROR: {e}")
                results["failed"] += 1
            human_pause(3, 6)  # politeness between jobs
        if not cdp_mode:
            ctx.close()

    print(f"\nResults: {results}")


if __name__ == "__main__":
    main()
