"""Bounded retries and sanitized network diagnostics for Scholar update scripts."""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def report(message):
    print(message, flush=True)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write('- ' + message + '\n')


def response_diagnosis(status, body):
    if status in (403, 429):
        return f'HTTP {status}: access denied or rate limited'
    if any(marker in body.lower() for marker in ('captcha', 'unusual traffic', 'automated queries')):
        return f'HTTP {status}: challenge/automated-traffic page detected'
    if 'gsc_a_tr' in body:
        return f'HTTP {status}: profile rows accessible in this diagnostic request'
    return f'HTTP {status}: expected profile rows absent; response body not logged'


def diagnose():
    import yaml
    user = yaml.safe_load(Path('_data/socials.yml').read_text(encoding='utf-8'))['scholar_userid']
    url = 'https://scholar.google.com/citations?hl=en&user=' + user
    try:
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=15) as response:
            return response_diagnosis(response.status, response.read(512000).decode('utf-8', errors='replace'))
    except HTTPError as error:
        return response_diagnosis(error.code, '')
    except (URLError, TimeoutError) as error:
        return 'Network diagnostic failed: ' + type(error).__name__
    except Exception as error:
        return 'Diagnostic configuration/error: ' + type(error).__name__


def transient(output):
    return any(marker in output.lower() for marker in (
        'cannot fetch from google scholar', 'maxtriesexceededexception',
        'timed out', 'timeout', 'connectionerror', 'connecterror',
        'connection reset', 'temporary failure in name resolution',
        'http error 403', 'http error 429', 'http error 502', 'http error 503',
    ))


def run(script, timeout, attempts=2, delay=30):
    for attempt in range(1, attempts + 1):
        report(f'{script}: attempt {attempt}/{attempts} (limit {timeout}s)')
        try:
            result = subprocess.run([sys.executable, '-u', script], capture_output=True,
                                    text=True, encoding='utf-8', errors='replace', timeout=timeout)
            output = result.stdout + result.stderr
            print(output, end='', flush=True)
            status = result.returncode
            retryable = transient(output)
        except subprocess.TimeoutExpired:
            status, retryable = 124, True
            report(f'{script}: process timeout after {timeout}s')
        if status == 0:
            report(f'{script}: completed successfully on attempt {attempt}')
            return 0
        report(f'{script}: failed (exit {status}); ' +
               ('network/timeout failure' if retryable else 'non-network error; not retried'))
        if retryable:
            report(diagnose())
        if not retryable or attempt == attempts:
            report(f'{script}: not updated successfully; existing data retained on fetch failure')
            return status if status > 0 else 1
        report(f'{script}: retrying after {delay}s; no proxy or challenge bypass')
        time.sleep(delay)
    return 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('script', choices=['bin/update_scholar_citations.py', 'bin/update_scholar_publications.py'])
    parser.add_argument('--timeout', type=int, required=True)
    args = parser.parse_args()
    sys.exit(run(args.script, args.timeout))
