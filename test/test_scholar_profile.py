import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path('bin').resolve()))
import scholar_profile as profile

USER = '1UvIUrEAAAAJ'
IDENTIFIER = USER + ':test123'
PROFILE_HTML = f'''<table id="gsc_rsb_st"><tbody>
<tr><td>Citations</td><td class="gsc_rsb_std">1,836</td></tr>
<tr><td>h-index</td><td class="gsc_rsb_std">25</td></tr>
</tbody></table><table id="gsc_a_b"><tr class="gsc_a_tr">
<td><a class="gsc_a_at" href="/citations?citation_for_view={IDENTIFIER}">Test paper</a></td>
<td class="gsc_a_c"><a class="gsc_a_ac">12</a></td>
<td class="gsc_a_y">2026</td></tr></table>'''
DETAIL_HTML = '''<div id="gsc_oci_title"><a class="gsc_oci_title_link"
href="https://doi.org/10.1234/example">Test paper</a></div>
<div id="gsc_oci_table">
<div class="gs_scl"><div class="gsc_oci_field">Authors</div><div class="gsc_oci_value">Ye Ming Qing, Ze Tao Huang</div></div>
<div class="gs_scl"><div class="gsc_oci_field">Publication date</div><div class="gsc_oci_value">2026/9</div></div>
<div class="gs_scl"><div class="gsc_oci_field">Journal</div><div class="gsc_oci_value">Example Journal</div></div>
<div class="gs_scl"><div class="gsc_oci_field">Volume</div><div class="gsc_oci_value">16</div></div>
<div class="gs_scl"><div class="gsc_oci_field">Issue</div><div class="gsc_oci_value">5</div></div>
<div class="gs_scl"><div class="gsc_oci_field">Pages</div><div class="gsc_oci_value">1470-1479</div></div>
</div>'''


class ScholarProfileTest(unittest.TestCase):
    def test_metrics_and_publication_list(self):
        result = profile.parse_profile(PROFILE_HTML, USER)
        self.assertEqual((result['citedby'], result['hindex']), (1836, 25))
        self.assertEqual(result['publications'][0]['author_pub_id'], IDENTIFIER)
        self.assertEqual(result['publications'][0]['num_citations'], 12)

    def test_one_fetch_reused_by_two_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'SCHOLAR_PROFILE_CACHE': str(Path(directory) / 'profile.json')}):
                with patch.object(profile, 'request_html', return_value=PROFILE_HTML) as fetch:
                    self.assertEqual(profile.load_profile(USER), profile.load_profile(USER))
                    fetch.assert_called_once()

    def test_full_details_required_for_new_publication(self):
        stub = profile.parse_profile(PROFILE_HTML, USER)['publications'][0]
        with patch.object(profile, 'request_html', return_value=DETAIL_HTML):
            result = profile.publication_details(stub)
        self.assertEqual(result['bib']['author'], ['Ye Ming Qing', 'Ze Tao Huang'])
        self.assertEqual(result['bib']['number'], '5')
        self.assertEqual(result['pub_url'], 'https://doi.org/10.1234/example')

    def test_missing_rows_are_not_treated_as_fresh_data(self):
        with self.assertRaises(ValueError):
            profile.parse_profile('<html>Blocked</html>', USER)


if __name__ == '__main__':
    unittest.main()
