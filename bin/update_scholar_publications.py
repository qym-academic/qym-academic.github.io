"""Add Scholar publications without overwriting curated citations or annotations."""

import argparse
import html
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

PAGE = Path('_pages/publications.md')
HEADINGS = ('期刊论文', '会议论文')


def normalized(value):
    value = html.unescape(re.sub(r'<[^>]+>', '', value))
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def sections(page):
    result = {}
    for name in HEADINGS:
        start = page.index('## ' + name + '\n') + len('## ' + name + '\n')
        end = page.index('<hr ', start)
        result[name] = (start, end, page[start:end])
    return result


def known(publication, page):
    bib = publication.get('bib', {})
    title = normalized(bib.get('title', ''))
    if len(title) > 20 and title in normalized(page):
        return True
    url = publication.get('pub_url', '')
    doi = re.search(r'10\.\d{4,9}/[^\s?#]+', url)
    if doi and doi.group().casefold().rstrip('/') in page.casefold():
        return True
    identifier = publication.get('author_pub_id', '')
    return bool(identifier and ('<!-- scholar:' + identifier + ' -->') in page)


def escaped(value):
    value = html.escape(str(value).strip(), quote=False)
    # Keep external metadata from becoming Markdown or Liquid instructions.
    for char in '*_[]{}':
        value = value.replace(char, '&#' + str(ord(char)) + ';')
    return value.replace('\n', ' ').replace('\r', ' ')


def author_name(value):
    parts = value.strip().replace('-', ' ').split()
    if len(parts) < 2:
        raise ValueError('Incomplete author name')
    surname = parts[-1]
    initials = ' '.join(c[0].upper() + '.' for c in parts[:-1])
    name = surname + ' ' + initials
    if normalized(name) in ('qingym', 'qingyeming'):
        return '<strong>Qing Y. M.</strong>'
    return escaped(name)


def entry(publication):
    bib = publication.get('bib', {})
    year = str(bib.get('pub_year', ''))
    authors = bib.get('author', '')
    title = str(bib.get('title', '')).strip()
    if not re.fullmatch(r'(19|20)\d{2}', year) or not title or not authors:
        raise ValueError('Missing title, authors, or publication year')
    if isinstance(authors, str):
        authors = authors.split(' and ')
    if any('…' in a or '...' in a or 'et al' in a.lower() for a in authors):
        raise ValueError('Truncated author list')
    conference = bib.get('conference', '')
    journal = bib.get('journal', '')
    venue = conference or journal
    if not venue or re.search(r'arxiv|preprint|patent|dissertation|thesis', venue, re.I):
        raise ValueError('Not an identified journal or conference')
    kind = '会议论文' if conference or re.search(r'proceedings|conference|symposium|congress', venue, re.I) else '期刊论文'
    if venue == 'The Journal of Chemical Physics':
        venue = 'Journal of Chemical Physics'
    url = publication.get('pub_url', '')
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc or any(c in url for c in '\r\n<>"'):
        raise ValueError('Missing safe publication link')
    url = url.replace('(', '%28').replace(')', '%29')
    fields = [year] + [str(bib[k]) for k in ('volume', 'number', 'pages') if bib.get(k)]
    fields = [escaped(v.replace('--', '–')) for v in fields]
    identifier = publication.get('author_pub_id', '')
    if not re.fullmatch(r'[\w:-]+', identifier):
        raise ValueError('Missing Scholar identifier')
    line = '; '.join(author_name(a) for a in authors) + '; '
    line += escaped(title.rstrip('.')) + '. _' + escaped(venue) + '_, '
    line += ', '.join(fields) + '. [论文链接](' + url + ')'
    line += ' <!-- scholar:' + identifier + ' -->'
    return kind, int(year), line


def merge(page, additions):
    """Rebuild year headings while retaining every curated entry verbatim."""
    for kind, (start, end, body) in reversed(list(sections(page).items())):
        rows = []
        for line in body.splitlines():
            match = re.match(r'- \*\*\[(\d+)\]\*\* (.*)', line)
            if not match:
                continue
            number, content = int(match[1]), match[2]
            # Journal year follows venue; conference grouping uses actual event date.
            year_match = re.search(r'_\s*,\s*((?:19|20)\d{2})', content)
            dates = re.findall(r'\(((?:19|20)\d{2})\.\d{2}\.\d{2}', content)
            if kind == '会议论文' and dates:
                year = int(dates[-1])
            elif year_match:
                year = int(year_match[1])
            else:
                raise ValueError('Cannot determine year for existing entry: ' + content)
            rows.append((year, number, content))
        if not rows:
            raise ValueError('Existing section unexpectedly empty')
        next_number = max(r[1] for r in rows)
        for year, content in sorted(additions.get(kind, [])):
            next_number += 1
            rows.append((year, next_number, content))
        output, previous = [], None
        for year, number, content in sorted(rows, key=lambda r: (r[0], r[1]), reverse=True):
            group = '2017–2021' if kind == '期刊论文' and 2017 <= year <= 2021 else str(year)
            if group != previous:
                output.append('\n### ' + group + '\n')
                previous = group
            output.append('- **[' + str(number).zfill(2) + ']** ' + content)
        page = page[:start] + '\n'.join(output) + '\n\n' + page[end:]
    return page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--normalize-only', action='store_true')
    args = parser.parse_args()
    original = PAGE.read_text(encoding='utf-8')
    additions = {name: [] for name in HEADINGS}
    if not args.normalize_only:
        import yaml
        from scholarly import scholarly
        user = yaml.safe_load(Path('_data/socials.yml').read_text(encoding='utf-8'))['scholar_userid']
        scholarly.set_timeout(15)
        scholarly.set_retries(2)
        author = scholarly.fill(scholarly.search_author_id(user), sections=['publications'])
        publications = author.get('publications')
        if not publications:
            raise RuntimeError('Scholar returned no publications; existing page retained')
        report, attempted = [], 0
        matched_page = original
        for pub in sorted(publications, key=lambda p: str(p.get('bib', {}).get('pub_year', '')), reverse=True):
            if known(pub, matched_page):
                continue
            # Bound per-run requests; unresolved records are retried next time.
            if attempted >= 20:
                report.append('Remaining candidates deferred to the next run.')
                break
            attempted += 1
            try:
                full = scholarly.fill(pub)
                if known(full, matched_page):
                    continue
                kind, year, content = entry(full)
                additions[kind].append((year, content))
                matched_page += '\n' + content
                report.append('Added: ' + full['bib']['title'])
            except Exception as error:
                report.append('Deferred: ' + str(pub.get('bib', {}).get('title', '')) + ' (' + str(error) + ')')
        for message in report:
            print(message)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as stream:
                stream.write('\n## Publication sync\n' + '\n'.join('- ' + escaped(m) for m in report) + '\n')
    result = merge(original, additions)
    if result != original:
        temporary = PAGE.with_suffix('.md.tmp')
        temporary.write_text(result, encoding='utf-8')
        temporary.replace(PAGE)
    print('Publication page synchronized; curated annotations preserved.')


if __name__ == '__main__':
    main()
