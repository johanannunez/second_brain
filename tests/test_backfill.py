from sb.backfill import plan_backfill


def test_backfill_adds_source_and_date_citations_without_writing(tmp_path):
    result = plan_backfill(
        {
            "facts": [
                {
                    "source": "gmail:parcel",
                    "date": "2026-10-26",
                    "target": "businesses/parcel-co.md",
                    "fact": "Owner approved the new onboarding timeline.",
                }
            ]
        },
        root=tmp_path,
    )
    assert result["proposals"] == [
        {
            "target": "businesses/parcel-co.md",
            "fact": "Owner approved the new onboarding timeline.",
            "citation": "[gmail:parcel, 2026-10-26]",
        }
    ]
    assert not list(tmp_path.iterdir())


def test_backfill_drops_todoist_and_notion_task_rows():
    rows = [
        {
            "source": "todoist",
            "date": "2026-10-26",
            "target": "goals/goals.md",
            "fact": "Task copied here",
            "kind": "task",
        },
        {
            "source": "notion",
            "date": "2026-10-26",
            "target": "businesses/proxy.md",
            "fact": "Notion task copied here",
            "kind": "todo",
        },
    ]
    result = plan_backfill({"facts": rows})
    assert not result["proposals"]
    assert all("stay in Todoist" in item["reason"] for item in result["deferred"])


def test_backfill_rejects_missing_citations_unsafe_paths_and_private_values():
    result = plan_backfill(
        {
            "facts": [
                {
                    "source": "gmail",
                    "target": "people/alex.md",
                    "fact": "No source date.",
                },
                {
                    "source": "gmail",
                    "date": "2026-10-26",
                    "target": "../profile.md",
                    "fact": "Path traversal.",
                },
                {
                    "source": "gmail",
                    "date": "2026-10-26",
                    "target": "people/alex.md",
                    "fact": "Guest phone 605-555-0111.",
                },
            ]
        }
    )
    assert not result["proposals"]
    assert len(result["deferred"]) == 3
