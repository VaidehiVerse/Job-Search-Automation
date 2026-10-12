import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DB_NAME = Path(__file__).resolve().parent / "jobs_database.db"


@contextmanager
def _connection():
    conn = sqlite3.connect(DB_NAME)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db():
    with _connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS evaluated_jobs (
                id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                location TEXT,
                site TEXT,
                job_url TEXT,
                visa_status TEXT,
                match_score REAL,
                req_yoe TEXT,
                exp_score REAL,
                semantic_score REAL,
                title_score REAL,
                search_query TEXT,
                date_posted TEXT,
                key_matches TEXT,
                missing_skills TEXT,
                scraped_at TIMESTAMP
            )
        """)
        for col, col_type in (
            ("search_query", "TEXT"),
            ("date_posted", "TEXT"),
            ("key_matches", "TEXT"),
            ("missing_skills", "TEXT"),
            ("experience_eligible", "INTEGER"),
        ):
            try:
                cursor.execute(f"ALTER TABLE evaluated_jobs ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass


def is_job_existing(job_id: str) -> bool:
    with _connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM evaluated_jobs WHERE id = ?", (job_id,))
        return cursor.fetchone() is not None


def save_evaluated_job(job_data: dict):
    with _connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO evaluated_jobs
            (id, title, company, location, site, job_url, visa_status, match_score,
             req_yoe, exp_score, semantic_score, title_score, search_query, date_posted,
             key_matches, missing_skills, experience_eligible, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_data["id"],
            job_data["title"],
            job_data["company"],
            job_data["location"],
            job_data["site"],
            job_data["job_url"],
            job_data["visa_status"],
            job_data["match_score"],
            str(job_data["req_yoe"]),
            job_data["exp_score"],
            job_data["semantic_score"],
            job_data["title_score"],
            job_data.get("search_query", ""),
            str(job_data.get("date_posted", "") or ""),
            job_data.get("key_matches", ""),
            job_data.get("missing_skills", ""),
            1 if job_data.get("experience_eligible", True) else 0,
            _utc_now_iso(),
        ))


def save_evaluated_jobs_batch(jobs: list[dict]):
    if not jobs:
        return
    now = _utc_now_iso()
    rows = [
        (
            j["id"],
            j["title"],
            j["company"],
            j["location"],
            j["site"],
            j["job_url"],
            j["visa_status"],
            j["match_score"],
            str(j["req_yoe"]),
            j["exp_score"],
            j["semantic_score"],
            j["title_score"],
            j.get("search_query", ""),
            str(j.get("date_posted", "") or ""),
            j.get("key_matches", ""),
            j.get("missing_skills", ""),
            1 if j.get("experience_eligible", True) else 0,
            now,
        )
        for j in jobs
    ]
    with _connection() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO evaluated_jobs
            (id, title, company, location, site, job_url, visa_status, match_score,
             req_yoe, exp_score, semantic_score, title_score, search_query, date_posted,
             key_matches, missing_skills, experience_eligible, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)


def load_all_evaluated_jobs(
    search_query: str | None = None,
    current_search_only: bool = False,
    max_evaluated_hours: int | None = None,
) -> pd.DataFrame:
    with _connection() as conn:
        if current_search_only and search_query:
            df = pd.read_sql_query(
                """
                SELECT * FROM evaluated_jobs
                WHERE search_query = ?
                ORDER BY match_score DESC
                """,
                conn,
                params=(search_query,),
            )
        else:
            df = pd.read_sql_query(
                "SELECT * FROM evaluated_jobs ORDER BY match_score DESC",
                conn,
            )
    if max_evaluated_hours and max_evaluated_hours > 0:
        from freshness import filter_by_evaluated_hours

        df = filter_by_evaluated_hours(df, max_evaluated_hours)
    return df


def clear_all_jobs():
    with _connection() as conn:
        conn.execute("DELETE FROM evaluated_jobs")


def job_count() -> int:
    with _connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM evaluated_jobs")
        return int(cursor.fetchone()[0])
