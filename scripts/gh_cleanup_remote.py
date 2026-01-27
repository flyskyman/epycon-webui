#!/usr/bin/env python3
"""Cleanup remote repo: delete non-master branches, tags matching patterns, and old workflow runs.

Usage: set GITHUB_TOKEN (or GH_TOKEN) in env or rely on `gh auth token`.

Careful: this will delete remote refs and workflow runs.
"""
import os
import sys
import time
import argparse
import re
from datetime import datetime, timezone, timedelta
import requests

API = "https://api.github.com"


def get_token():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    # fallback to gh auth token
    try:
        import subprocess
        t = subprocess.check_output(["gh", "auth", "token"], universal_newlines=True).strip()
        if t:
            return t
    except Exception:
        pass
    return None


def api_get(session, url, params=None):
    r = session.get(url, params=params)
    if r.status_code >= 400:
        raise SystemExit(f"GET {url} failed: {r.status_code} {r.text}")
    return r.json()


def api_delete(session, url):
    r = session.delete(url)
    return r.status_code, r.text


def list_branches(session, owner, repo):
    out = []
    page = 1
    while True:
        url = f"{API}/repos/{owner}/{repo}/branches"
        data = api_get(session, url, params={"per_page":100, "page":page})
        if not data:
            break
        for b in data:
            out.append(b.get("name"))
        if len(data) < 100:
            break
        page += 1
    return out


def delete_branch(session, owner, repo, branch):
    url = f"{API}/repos/{owner}/{repo}/git/refs/heads/{branch}"
    return api_delete(session, url)


def list_tags(session, owner, repo):
    out = []
    page = 1
    while True:
        url = f"{API}/repos/{owner}/{repo}/git/refs/tags"
        r = session.get(url, params={"per_page":100, "page":page})
        if r.status_code >= 400:
            raise SystemExit(f"GET tags failed: {r.status_code} {r.text}")
        data = r.json()
        if not data:
            break
        for t in data:
            # ref looks like refs/tags/<tag>
            ref = t.get('ref')
            if ref and ref.startswith('refs/tags/'):
                out.append(ref.split('refs/tags/')[1])
        if len(data) < 100:
            break
        page += 1
    return out


def delete_tag(session, owner, repo, tag):
    url = f"{API}/repos/{owner}/{repo}/git/refs/tags/{tag}"
    return api_delete(session, url)


def list_runs(session, owner, repo, per_page=100):
    url = f"{API}/repos/{owner}/{repo}/actions/runs"
    page = 1
    out = []
    while True:
        r = session.get(url, params={"per_page":per_page, "page":page})
        if r.status_code >= 400:
            raise SystemExit(f"GET runs failed: {r.status_code} {r.text}")
        j = r.json()
        runs = j.get('workflow_runs', [])
        if not runs:
            break
        out.extend(runs)
        if len(runs) < per_page:
            break
        page += 1
    return out


def delete_run(session, owner, repo, run_id):
    url = f"{API}/repos/{owner}/{repo}/actions/runs/{run_id}"
    return api_delete(session, url)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--owner', required=True)
    p.add_argument('--repo', required=True)
    p.add_argument('--delete-branches', action='store_true')
    p.add_argument('--delete-tags', action='store_true')
    p.add_argument('--delete-runs', action='store_true')
    p.add_argument('--tag-pattern', default=r'(-test|-ci-)')
    p.add_argument('--runs-older-days', type=int, default=30)
    args = p.parse_args()

    token = get_token()
    if not token:
        print('ERROR: no GITHUB_TOKEN / GH_TOKEN and gh auth token not available; aborting.')
        sys.exit(2)

    session = requests.Session()
    session.headers.update({
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'gh-cleanup-remote-script'
    })

    owner = args.owner
    repo = args.repo

    if args.delete_branches:
        print('Listing branches...')
        branches = list_branches(session, owner, repo)
        to_delete = [b for b in branches if b not in ('master', 'main')]
        print(f'Found {len(branches)} branches; will delete {len(to_delete)} non-master branches.')
        for b in to_delete:
            print(f'Deleting branch: {b}')
            status, text = delete_branch(session, owner, repo, b)
            if status in (204, 200):
                print(' -> deleted')
            elif status == 422:
                print(' -> Unprocessable (maybe protected)')
            elif status == 404:
                print(' -> not found')
            else:
                print(f' -> unexpected {status}: {text}')
            time.sleep(0.5)

    if args.delete_tags:
        print('Listing tags...')
        tags = list_tags(session, owner, repo)
        pattern = re.compile(args.tag_pattern)
        to_delete = [t for t in tags if pattern.search(t)]
        print(f'Found {len(tags)} tags; will delete {len(to_delete)} matching pattern "{args.tag_pattern}".')
        for t in to_delete:
            print(f'Deleting tag: {t}')
            status, text = delete_tag(session, owner, repo, t)
            if status in (204, 200):
                print(' -> deleted')
            elif status == 404:
                print(' -> not found')
            else:
                print(f' -> unexpected {status}: {text}')
            time.sleep(0.3)

    if args.delete_runs:
        print('Listing workflow runs...')
        runs = list_runs(session, owner, repo)
        cutoff = datetime.now(timezone.utc) - timedelta(days=args.runs_older_days)
        to_delete = [r for r in runs if datetime.fromisoformat(r.get('created_at').replace('Z', '+00:00')) < cutoff]
        print(f'Found {len(runs)} runs; will delete {len(to_delete)} older than {args.runs_older_days} days.')
        for r in to_delete:
            rid = r.get('id')
            created = r.get('created_at')
            print(f'Deleting run id:{rid} created:{created}')
            status, text = delete_run(session, owner, repo, rid)
            if status == 204:
                print(' -> deleted')
            elif status == 404:
                print(' -> not found')
            else:
                print(f' -> unexpected {status}: {text}')
            time.sleep(0.5)

    print('Cleanup script finished.')

if __name__ == '__main__':
    main()
