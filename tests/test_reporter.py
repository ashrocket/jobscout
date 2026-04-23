from jobscout.pipeline.reporter import generate_report


def test_generate_report_renders_html():
    jobs = [
        {
            "id": "j1",
            "title": "VP of Engineering",
            "company": "Nomi Health",
            "location": "Remote",
            "url": "https://linkedin.com/jobs/123",
            "score": 92,
            "star_rating": 5,
            "extracted_json": '{"industry": "healthcare", "company_stage": "Series C", "description": "Lead eng team", "signals": ["healthcare", "scaling"]}',
            "resume_used": "healthcare",
        },
        {
            "id": "j2",
            "title": "CTO",
            "company": "Stealth Fintech",
            "location": "NYC",
            "url": "https://linkedin.com/jobs/456",
            "score": 78,
            "star_rating": 4,
            "extracted_json": '{"industry": "fintech", "company_stage": "Series B", "description": "Rebuild platform", "signals": ["fintech", "rebuilding"]}',
            "resume_used": "vpeng",
        },
    ]
    html = generate_report(jobs)
    assert "Nomi Health" in html
    assert "★★★★★" in html
    assert "Stealth Fintech" in html
    assert "★★★★" in html
    assert "<html" in html.lower()
