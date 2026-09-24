"""Read a public Google Scholar profile with one request per listing page."""

import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

BASE_URL = 'https://scholar.google.com/citations'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'en-US,en;q=0.9'}
PAGE_SIZE = 100


def request_html(url):
    with urlopen(Request(url, headers=HEADERS), timeout=20) as response:
        body = response.read().decode('utf-8', errors='replace')
    if any(marker in body.lower() for marker in ('unusual traffic', 'automated queries', 'recaptcha')):
        raise ConnectionError('Cannot fetch from Google Scholar: challenge page')
    return body


def parse_profile(body, user, allow_empty=False):
    soup = BeautifulSoup(body, 'html.parser')
    stats = soup.select('#gsc_rsb_st tbody tr')
    rows = soup.select('#gsc_a_b tr.gsc_a_tr')
    if len(stats) < 2 or (not rows and not allow_empty):
        raise ValueError('Scholar profile metrics or publication rows absent')
    try:
        citedby = int(stats[0].select('td.gsc_rsb_std')[0].get_text(strip=True).replace(',', ''))
        hindex = int(stats[1].select('td.gsc_rsb_std')[0].get_text(strip=True).replace(',', ''))
    except (IndexError, ValueError) as error:
        raise ValueError('Scholar profile metrics unreadable') from error
    publications = []
    for row in rows:
        title_link = row.select_one('a.gsc_a_at')
        if not title_link:
            continue
        identifier = parse_qs(urlparse(title_link.get('href', '')).query).get('citation_for_view', [''])[0]
        if not identifier.startswith(user + ':'):
            continue
        year = row.select_one('.gsc_a_y')
        citations = row.select_one('.gsc_a_c .gsc_a_ac')
        citation_text = citations.get_text(strip=True).replace(',', '') if citations else ''
        publications.append({
            'author_pub_id': identifier,
            'bib': {'title': title_link.get_text(' ', strip=True),
                    'pub_year': year.get_text(strip=True) if year else ''},
            'num_citations': int(citation_text) if citation_text.isdigit() else 0,
        })
    if not publications and not allow_empty:
        raise ValueError('Scholar profile publication identifiers absent')
    return {'citedby': citedby, 'hindex': hindex, 'publications': publications}


def load_profile(user):
    cache_name = os.environ.get('SCHOLAR_PROFILE_CACHE')
    cache = Path(cache_name) if cache_name else None
    if cache and cache.is_file():
        saved = json.loads(cache.read_text(encoding='utf-8'))
        if saved.get('user') == user and saved.get('profile', {}).get('publications'):
            return saved['profile']
    publications = []
    profile = None
    for offset in range(0, 1000, PAGE_SIZE):
        url = BASE_URL + '?' + urlencode({'hl': 'en', 'user': user, 'cstart': offset,
                                          'pagesize': PAGE_SIZE})
        page = parse_profile(request_html(url), user, allow_empty=offset > 0)
        if profile is None:
            profile = page
        publications.extend(page['publications'])
        if len(page['publications']) < PAGE_SIZE:
            break
    else:
        raise ValueError('Scholar profile exceeds 1000 publications; refusing a partial list')
    profile['publications'] = publications
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix(cache.suffix + '.tmp')
        temporary.write_text(json.dumps({'user': user, 'profile': profile}), encoding='utf-8')
        temporary.replace(cache)
    return profile


def publication_details(publication):
    identifier = publication['author_pub_id']
    user = identifier.split(':', 1)[0]
    if not re.fullmatch(r'[\w-]+:[\w-]+', identifier):
        raise ValueError('Unsafe Scholar publication identifier')
    url = BASE_URL + '?' + urlencode({'view_op': 'view_citation', 'hl': 'en',
                                       'user': user, 'citation_for_view': identifier})
    soup = BeautifulSoup(request_html(url), 'html.parser')
    title = soup.select_one('#gsc_oci_title a.gsc_oci_title_link')
    fields = {}
    for row in soup.select('#gsc_oci_table .gs_scl'):
        label = row.select_one('.gsc_oci_field')
        value = row.select_one('.gsc_oci_value')
        if label and value:
            fields[label.get_text(' ', strip=True)] = value.get_text(' ', strip=True)
    if not title or not fields:
        raise ValueError('Scholar publication details absent')
    publication_date = fields.get('Publication date', '')
    year = re.match(r'(19|20)\d{2}', publication_date)
    authors = [name.strip() for name in fields.get('Authors', '').split(',')]
    return {'author_pub_id': identifier, 'pub_url': title.get('href', ''),
            'bib': {'title': title.get_text(' ', strip=True), 'author': authors,
                    'pub_year': year.group() if year else publication['bib'].get('pub_year', ''),
                    'journal': fields.get('Journal', ''),
                    'conference': fields.get('Conference', ''),
                    'volume': fields.get('Volume', ''), 'number': fields.get('Issue', ''),
                    'pages': fields.get('Pages', '') or fields.get('Article number', '')}}
