import importlib.util
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('retry', 'bin/run_scholar_update.py')
retry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retry)


class ScholarRetryTest(unittest.TestCase):
    def result(self, code, output=''):
        return subprocess.CompletedProcess([], code, output, '')

    @patch.object(retry, 'report')
    @patch.object(retry, 'diagnose', return_value='HTTP 429')
    @patch.object(retry.time, 'sleep')
    def test_transient_retry_then_success(self, sleep, diagnosis, report):
        with patch.object(retry.subprocess, 'run', side_effect=[self.result(1, 'Cannot Fetch from Google Scholar.'), self.result(0)]) as run:
            self.assertEqual(retry.run('example.py', 10), 0)
            self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(30)

    @patch.object(retry, 'report')
    def test_programming_error_not_retried(self, report):
        with patch.object(retry.subprocess, 'run', return_value=self.result(1, 'ModuleNotFoundError')) as run:
            self.assertEqual(retry.run('example.py', 10), 1)
            self.assertEqual(run.call_count, 1)

    @patch.object(retry, 'report')
    @patch.object(retry, 'diagnose', return_value='TimeoutError')
    @patch.object(retry.time, 'sleep')
    def test_timeouts_stop_at_two(self, sleep, diagnosis, report):
        with patch.object(retry.subprocess, 'run', side_effect=subprocess.TimeoutExpired('example', 10)) as run:
            self.assertEqual(retry.run('example.py', 10), 124)
            self.assertEqual(run.call_count, 2)

    def test_diagnostic_classification(self):
        self.assertIn('rate limited', retry.response_diagnosis(429, ''))
        self.assertIn('challenge', retry.response_diagnosis(200, 'unusual traffic'))
        self.assertIn('accessible', retry.response_diagnosis(200, 'gsc_a_tr'))
        self.assertIn('absent', retry.response_diagnosis(200, 'unexpected page'))


if __name__ == '__main__':
    unittest.main()
