import argparse
import json
import sys
from datetime import datetime, timezone

from jobscout.config import (
    DB_PATH, SCORE_THRESHOLD, SOURCES_DIR, DISCOVERED_COMPANIES_PATH, TAILORED_DIR,
    get_queries, get_resume_map, get_company_seeds,
)
from jobscout.db import init_db, insert_job, get_job, update_job_status, get_jobs_by_status, insert_run, complete_run
from jobscout.budget import check_budget, budget_summary, is_alert_threshold
from jobscout.pipeline.extractor import extract_job_data
from jobscout.pipeline.classifier import classify_job
from jobscout.pipeline.scorer import score_job
from jobscout.pipeline.cv_tuner import tune_cv
from jobscout.pipeline.reporter import generate_report
from jobscout.integrations.pigeon import send_document, send_question, send_message, poll_reply
from jobscout.integrations.imessage import send_imessage
from jobscout.scrapers.indeed import IndeedScraper
from jobscout.scrapers.linkedin import LinkedInScraper
from jobscout.scrapers.greenhouse import GreenhouseScraper
from jobscout.scrapers.ashby import AshbyScraper
from jobscout.scrapers.lever import LeverScraper
from jobscout.scrapers.reddit import RedditScraper
from jobscout.scrapers.monster import MonsterScraper
from jobscout.scrapers.slack import SlackScraper
from jobscout.scrapers.discovery import try_discover_career_page, load_discovered, save_discovered

def _portal_queries(portal_name: str) -> list[str]:
    if portal_name in ("slack", "greenhouse", "ashby", "lever"):
        return [""]
    return get_queries(portal_name) or [""]

_SCRAPER_ATTR = {
    "indeed": "IndeedScraper",
    "linkedin": "LinkedInScraper",
    "reddit": "RedditScraper",
    "monster": "MonsterScraper",
    "slack": "SlackScraper",
    "greenhouse": "GreenhouseScraper",
    "ashby": "AshbyScraper",
    "lever": "LeverScraper",
}


def _scraper_cls(portal_name: str):
    """Look up scraper class from module namespace at call time (supports mocking)."""
    attr = _SCRAPER_ATTR.get(portal_name)
    if attr is None:
        return None
    return getattr(sys.modules[__name__], attr, None)


def _pick_query(queries: list[str]) -> str:
    hour = datetime.now(timezone.utc).hour
    return queries[hour % len(queries)]


def _career_page_scraper(portal_name: str):
    discovered = load_discovered(DISCOVERED_COMPANIES_PATH)
    seed = get_company_seeds().get(portal_name, [])
    disc = discovered.get(portal_name, [])

    seen_slugs = {c["slug"] for c in seed}
    merged = list(seed)
    for c in disc:
        if c["slug"] not in seen_slugs:
            merged.append(c)
            seen_slugs.add(c["slug"])

    scraper_cls = _scraper_cls(portal_name)
    if scraper_cls is None:
        return None
    return scraper_cls(merged)


def run_scan(portals: list[str], db_path=None) -> dict:
    conn = init_db(db_path or DB_PATH)
    stats = {"jobs_found": 0, "jobs_new": 0, "jobs_scored": 0, "errors": []}
    scored_jobs = []

    for portal_name in portals:
        scraper_cls = _scraper_cls(portal_name)
        if scraper_cls is None:
            stats["errors"].append(f"Unknown portal: {portal_name}")
            continue

        queries = _portal_queries(portal_name)
        run_id = insert_run(conn, portal=portal_name)

        if portal_name in ("greenhouse", "ashby", "lever"):
            scraper = _career_page_scraper(portal_name)
            if scraper is None or not scraper._companies:
                continue
        else:
            scraper = scraper_cls()

        try:
            any_provider_ok = False
            for provider in ["openai", "anthropic", "gemini"]:
                ok, remaining = check_budget(conn, provider)
                if ok:
                    any_provider_ok = True
                elif remaining <= 0:
                    # Only alert once per exhausted provider per run
                    pass
            if not any_provider_ok:
                msg = "Budget exhausted for all LLM providers"
                send_message(title="JobScout: All Budgets Exhausted", body=msg, priority="urgent")
                send_imessage(f"JobScout PAUSED: all LLM budgets exhausted")
                complete_run(conn, run_id, error=msg)
                stats["errors"].append(msg)
                continue

            query = _pick_query(queries)
            listings = scraper.search(query)
            stats["jobs_found"] += len(listings)

            for listing in listings:
                if get_job(conn, listing["id"]):
                    continue

                inserted = insert_job(
                    conn, id=listing["id"], portal=listing["portal"],
                    url=listing["url"], title=listing["title"],
                    company=listing["company"], location=listing["location"],
                    raw_html=listing.get("raw_html"),
                )
                if not inserted:
                    continue
                stats["jobs_new"] += 1

                raw_html = listing.get("raw_html", "")
                if portal_name == "linkedin" and hasattr(scraper, "get_job_detail"):
                    try:
                        raw_html = scraper.get_job_detail(listing["url"])
                    except Exception:
                        pass

                # --- EXTRACT ---
                extracted = extract_job_data(raw_html, conn=conn)
                if not extracted:
                    update_job_status(conn, listing["id"], "extract_failed")
                    continue

                update_job_status(conn, listing["id"], "extracted",
                                  extracted_json=json.dumps(extracted))

                # --- CLASSIFY ---
                classification = classify_job(extracted, conn=conn)
                if classification:
                    resume_key = classification["resume_variant"]
                    update_job_status(conn, listing["id"], "classified",
                                      archetype=classification["archetype"],
                                      archetype_confidence=classification.get("confidence"))
                else:
                    classification = None
                    resume_key = "default"

                # --- SCORE ---
                score_result = score_job(extracted, classification=classification, conn=conn)
                if not score_result:
                    update_job_status(conn, listing["id"], "score_failed")
                    continue

                resume_map = get_resume_map()
                resume_file = resume_map.get(resume_key, resume_map["default"])

                update_job_status(
                    conn, listing["id"], "scored",
                    score=score_result["score"],
                    star_rating=score_result["star_rating"],
                    resume_used=resume_file,
                    notes=score_result.get("reasoning", ""),
                )
                stats["jobs_scored"] += 1

                if score_result["score"] >= SCORE_THRESHOLD:
                    # --- CV TUNE (non-blocking) ---
                    resume_path = SOURCES_DIR / resume_file
                    if resume_path.exists():
                        try:
                            resume_html = resume_path.read_text()
                            tuned = tune_cv(resume_html, extracted,
                                            classification or {}, conn=conn)
                            if tuned:
                                TAILORED_DIR.mkdir(parents=True, exist_ok=True)
                                tailored_path = TAILORED_DIR / f"{listing['id']}.html"
                                tailored_path.write_text(tuned)
                                update_job_status(conn, listing["id"], "tuned",
                                                  tailored_resume_path=str(tailored_path))
                        except Exception:
                            pass

                    # --- AUTO-DISCOVER (non-blocking) ---
                    try:
                        company_name = extracted.get("company") or listing.get("company", "")
                        if company_name:
                            disc_result = try_discover_career_page(company_name)
                            if disc_result:
                                discovered = load_discovered(DISCOVERED_COMPANIES_PATH)
                                platform = disc_result["platform"]
                                existing_slugs = {c["slug"] for c in discovered.get(platform, [])}
                                if disc_result["slug"] not in existing_slugs:
                                    discovered.setdefault(platform, []).append(disc_result)
                                    save_discovered(DISCOVERED_COMPANIES_PATH, discovered)
                    except Exception:
                        pass

                    scored_jobs.append({
                        **listing,
                        "score": score_result["score"],
                        "star_rating": score_result["star_rating"],
                        "extracted_json": json.dumps(extracted),
                        "resume_used": resume_file,
                    })

            complete_run(conn, run_id, jobs_found=len(listings), jobs_new=stats["jobs_new"])

        except RuntimeError as e:
            if "session expired" in str(e).lower():
                send_question(
                    title="JobScout: LinkedIn Cookie Expired",
                    body="LinkedIn session expired. Please update ~/.env/ashcode/jobscout/linkedin-cookie with a fresh li_at value.",
                )
                send_imessage("JobScout: LinkedIn cookie expired — update needed")
            complete_run(conn, run_id, error=str(e))
            stats["errors"].append(str(e))

        except Exception as e:
            complete_run(conn, run_id, error=str(e))
            stats["errors"].append(str(e))

        finally:
            if hasattr(scraper, "close"):
                scraper.close()

    if scored_jobs:
        scored_jobs.sort(key=lambda j: j["score"], reverse=True)
        html = generate_report(scored_jobs)
        n = len(scored_jobs)
        top = scored_jobs[0]
        send_document(
            title=f"JobScout: {n} new role{'s' if n != 1 else ''} ({datetime.now().strftime('%I:%M %p')})",
            html=html,
        )
        send_imessage(f"JobScout: {n} new VP Eng match{'es' if n != 1 else ''} — top: {top['title']} at {top['company']} ({'★' * top['star_rating']}) — check Pigeon")

    for provider in ["gemini", "anthropic", "openai"]:
        if is_alert_threshold(conn, provider):
            summary = budget_summary(conn)
            p = summary[provider]
            send_message(
                title=f"JobScout: {provider} budget at {p['pct']}%",
                body=f"Spent ${p['spent']:.2f} of ${p['limit']:.2f}. ${p['remaining']:.2f} remaining.",
            )

    conn.close()
    return stats


def run_apply_approved(db_path=None):
    conn = init_db(db_path or DB_PATH)
    surfaced = get_jobs_by_status(conn, "surfaced")

    for job in surfaced:
        if not job["pigeon_message_id"]:
            continue
        reply = poll_reply(job["pigeon_message_id"])
        if reply and any(w in reply.lower() for w in ["yes", "apply", "go"]):
            update_job_status(conn, job["id"], "approved")
            send_message(
                title=f"JobScout: Approved — {job['title']} at {job['company']}",
                body="Queued for application. (Auto-apply coming in Phase 2)",
            )

    conn.close()


def run_budget_report(db_path=None):
    conn = init_db(db_path or DB_PATH)
    summary = budget_summary(conn)
    lines = ["Budget Report:"]
    for provider, data in summary.items():
        lines.append(f"  {provider}: ${data['spent']:.2f} / ${data['limit']:.2f} ({data['pct']}%)")
    send_message(title="JobScout: Daily Budget Report", body="\n".join(lines))
    conn.close()


def run_process_backlog(limit: int = 50, db_path=None) -> dict:
    """Re-run extract/classify/score/tune on jobs stuck in 'new' status.

    These accumulated during the LLM outage. Their raw_html is already stored.
    """
    import sqlite3
    conn = init_db(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row

    cur = conn.execute(
        "SELECT id, portal, url, title, company, location, raw_html FROM jobs "
        "WHERE status='new' AND raw_html IS NOT NULL AND length(raw_html) > 100 "
        "ORDER BY discovered_at DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    stats = {"processed": 0, "scored": 0, "tuned": 0, "failed": 0, "tuned_jobs": []}

    for row in rows:
        job_id = row["id"]
        raw_html = row["raw_html"]
        try:
            extracted = extract_job_data(raw_html, conn=conn)
            if not extracted:
                update_job_status(conn, job_id, "extract_failed")
                stats["failed"] += 1
                continue
            update_job_status(conn, job_id, "extracted",
                              extracted_json=json.dumps(extracted))
            classification = classify_job(extracted, conn=conn)
            resume_key = "default"
            if classification:
                resume_key = classification["resume_variant"]
                update_job_status(conn, job_id, "classified",
                                  archetype=classification["archetype"],
                                  archetype_confidence=classification.get("confidence"))
            score_result = score_job(extracted, classification=classification, conn=conn)
            if not score_result:
                update_job_status(conn, job_id, "score_failed")
                stats["failed"] += 1
                continue
            resume_map = get_resume_map()
            resume_file = resume_map.get(resume_key, resume_map["default"])
            update_job_status(
                conn, job_id, "scored",
                score=score_result["score"],
                star_rating=score_result["star_rating"],
                resume_used=resume_file,
                notes=score_result.get("reasoning", ""),
            )
            stats["scored"] += 1
            if score_result["score"] >= SCORE_THRESHOLD:
                resume_path = SOURCES_DIR / resume_file
                if resume_path.exists():
                    try:
                        tuned = tune_cv(resume_path.read_text(), extracted,
                                        classification or {}, conn=conn)
                        if tuned:
                            TAILORED_DIR.mkdir(parents=True, exist_ok=True)
                            tailored_path = TAILORED_DIR / f"{job_id}.html"
                            tailored_path.write_text(tuned)
                            update_job_status(conn, job_id, "tuned",
                                              tailored_resume_path=str(tailored_path))
                            stats["tuned"] += 1
                            stats["tuned_jobs"].append({
                                "id": job_id, "portal": row["portal"],
                                "url": row["url"], "title": row["title"],
                                "company": row["company"], "location": row["location"],
                                "score": score_result["score"],
                                "star_rating": score_result["star_rating"],
                                "extracted_json": json.dumps(extracted),
                                "resume_used": resume_file,
                            })
                    except Exception:
                        pass
        except Exception:
            stats["failed"] += 1
        stats["processed"] += 1

    if stats["tuned_jobs"]:
        html = generate_report(stats["tuned_jobs"])
        send_document(
            title=f"JobScout: Backlog processed — {len(stats['tuned_jobs'])} surfaced",
            html=html,
        )
    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description="JobScout — automated job search pipeline")
    parser.add_argument("--portals", type=str, default="indeed",
                        help="Comma-separated portals to scan")
    parser.add_argument("--apply-approved", action="store_true",
                        help="Check for approved jobs and apply")
    parser.add_argument("--budget-report", action="store_true",
                        help="Send daily budget report")
    parser.add_argument("--process-backlog", action="store_true",
                        help="Re-process jobs stuck in 'new' status")
    parser.add_argument("--backlog-limit", type=int, default=50,
                        help="Max backlog jobs to process in one run")
    args = parser.parse_args()

    if args.apply_approved:
        run_apply_approved()
    elif args.budget_report:
        run_budget_report()
    elif args.process_backlog:
        stats = run_process_backlog(limit=args.backlog_limit)
        print(f"Backlog processed: {stats}")
    else:
        portals = [p.strip() for p in args.portals.split(",")]
        stats = run_scan(portals)
        print(f"Scan complete: {stats}")


if __name__ == "__main__":
    main()
