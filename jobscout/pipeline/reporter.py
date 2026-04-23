import json
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader
from jobscout.config import TEMPLATES_DIR


def generate_report(jobs: list[dict]) -> str:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("report.html")

    enriched = []
    for job in jobs:
        entry = dict(job)
        try:
            entry["extracted"] = json.loads(job.get("extracted_json", "{}") or "{}")
        except json.JSONDecodeError:
            entry["extracted"] = {}
        enriched.append(entry)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return template.render(jobs=enriched, timestamp=timestamp)
