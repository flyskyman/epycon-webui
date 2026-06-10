#!/usr/bin/env python3
"""Delete GitHub Actions artifacts for a repository until none remain.

Usage: set environment variable GITHUB_TOKEN with repo scope (or use gh auth),
then run: python scripts/gh_delete_artifacts.py --owner flyskyman --repo epycon-webui
"""
import os
import sys
import time
import argparse
import requests

API = "https://api.github.com"


def paged_artifacts(session, owner, repo, per_page=100):
    page = 1
    while True:
        url = f"{API}/repos/{owner}/{repo}/actions/artifacts"
        params = {"per_page": per_page, "page": page}
        r = session.get(url, params=params)
        if r.status_code != 200:
            raise SystemExit(f"Failed to list artifacts: {r.status_code} {r.text}")
        data = r.json()
        artifacts = data.get("artifacts", [])
        if not artifacts:
            break
        for a in artifacts:
            yield a
        page += 1


def delete_artifact(session, owner, repo, artifact_id):
    url = f"{API}/repos/{owner}/{repo}/actions/artifacts/{artifact_id}"
    r = session.delete(url)
    return r.status_code, r.text


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--owner", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--max-passes", type=int, default=20, help="Max full passes to attempt")
    p.add_argument("--sleep", type=float, default=1.0, help="Seconds to sleep between passes")
    args = p.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("ERROR: set GITHUB_TOKEN (or GH_TOKEN) in environment with repo scope.")
        sys.exit(2)

    session = requests.Session()
    session.headers.update({"Authorization": f"token {token}", "Accept": "application/vnd.github+json", "User-Agent": "gh-delete-artifacts-script"})

    total_deleted = 0
    for passno in range(1, args.max_passes + 1):
        print(f"Pass {passno}: listing artifacts...")
        artifacts = list(paged_artifacts(session, args.owner, args.repo))
        if not artifacts:
            print("No artifacts found; finished.")
            break
        print(f"Found {len(artifacts)} artifacts on this pass; attempting deletes...")
        for a in artifacts:
            aid = a.get("id")
            name = a.get("name")
            created = a.get("created_at")
            print(f"Deleting artifact ID:{aid} Name:{name} Created:{created}")
            status, text = delete_artifact(session, args.owner, args.repo, aid)
            if status == 204:
                print(" -> deleted")
                total_deleted += 1
            elif status == 404:
                print(" -> already gone (404)")
            else:
                print(f" -> unexpected status {status}; body: {text}")
        print(f"Pass {passno} complete. Sleeping {args.sleep}s before next pass...")
        time.sleep(args.sleep)
    print(f"Finished deletion loop. Total delete attempts reported: {total_deleted}")
    # final verification
    r = session.get(f"{API}/repos/{args.owner}/{args.repo}/actions/artifacts?per_page=100")
    if r.status_code != 200:
        print(f"Final verification failed: {r.status_code} {r.text}")
        sys.exit(1)
    final = r.json()
    total = final.get("total_count", 0)
    if total == 0:
        print("No remaining artifacts.")
        sys.exit(0)
    print(f"Remaining total_count: {total}")
    for a in final.get("artifacts", []):
        print(f" - ID:{a.get('id')} Name:{a.get('name')} Created:{a.get('created_at')}")
    sys.exit(3)


if __name__ == "__main__":
    main()
