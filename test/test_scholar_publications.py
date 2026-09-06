import importlib.util
import re
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('sync', 'bin/update_scholar_publications.py')
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class PublicationSyncTest(unittest.TestCase):
    def setUp(self):
        self.page = Path('_pages/publications.md').read_text(encoding='utf-8')
        self.pub = {'author_pub_id': 'test:abc', 'pub_url': 'https://doi.org/10.1234/example',
                    'bib': {'title': 'A new example paper', 'author': 'Ye Ming Qing and Ze-Tao Huang',
                            'journal': 'Example Journal', 'pub_year': 2027, 'volume': '1', 'pages': '1–9'}}

    def test_future_year_and_idempotence(self):
        kind, year, line = sync.entry(self.pub)
        updated = sync.merge(self.page, {kind: [(year, line)]})
        self.assertIn('### 2027', updated)
        existing = sync.sections(self.page)['期刊论文'][2]
        number = max(map(int, re.findall(r'\*\*\[(\d+)\]', existing))) + 1
        self.assertIn('**[' + str(number).zfill(2) + ']**', updated)
        self.assertTrue(sync.known(self.pub, updated))
        self.assertEqual(updated, sync.merge(updated, {}))

    def test_curated_entries_and_patents_preserved(self):
        updated = sync.merge(self.page, {})
        for line in self.page.splitlines():
            if line.startswith('- **['):
                self.assertIn(line, updated)
        self.assertEqual(self.page.split('## 专利')[1], updated.split('## 专利')[1])

    def test_conference_classification(self):
        self.pub['bib'].pop('journal')
        self.pub['bib']['conference'] = 'International Conference on Optics'
        kind, year, line = sync.entry(self.pub)
        self.assertEqual(kind, '会议论文')
        section = sync.merge(self.page, {kind: [(year, line)]}).split('## 会议论文')[1]
        self.assertNotIn('### ', section)
        self.assertIn(line, section)

    def test_no_empty_future_year(self):
        updated = sync.merge(self.page, {})
        self.assertNotIn('### 2027', updated)
        self.assertNotIn('### ', sync.sections(updated)['会议论文'][2])

    def test_no_invented_correspondence(self):
        line = sync.entry(self.pub)[2]
        self.assertIn('<strong>Qing Y. M.</strong>', line)
        self.assertNotIn('M.*', line)

    def test_incomplete_and_unsafe_records(self):
        self.pub['bib']['author'] = 'Ye Ming Qing and et al.'
        with self.assertRaises(ValueError):
            sync.entry(self.pub)
        self.pub['bib']['author'] = 'Ye Ming Qing'
        self.pub['pub_url'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError):
            sync.entry(self.pub)

    def test_title_and_doi_deduplication(self):
        self.assertTrue(sync.known({'bib': {'title': 'Strong Coupling in Two-Dimensional Materials-Based Nanostructures: A Review'}}, self.page))
        self.assertTrue(sync.known({'pub_url': 'https://doi.org/10.1117/12.3122548'}, self.page))


if __name__ == '__main__':
    unittest.main()
