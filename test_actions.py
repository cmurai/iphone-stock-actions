import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_actions as app


def fixture(state):
    return {'body': {'content': {'pickupMessage': {'stores': [{
        'storeNumber': 'R001', 'storeName': 'Test Store',
        'partsAvailability': {'TEST/A': {'pickupDisplay': state, 'pickupQuote': 'Tomorrow'}}
    }]}}}}


class ActionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for p in [patch.object(app, 'STATE', Path(self.temp.name) / 'state.json'),
                  patch.dict(app.os.environ, {'APPLE_ZIP': '94086', 'APPLE_PARTS': 'TEST/A',
                             'SLACK_WEBHOOK_URL': 'https://hooks.slack.com/services/test'}, clear=True)]:
            p.start()
            self.addCleanup(p.stop)

    def check(self, state):
        with patch.object(app, 'fetch', return_value=fixture(state)), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return app.run()

    def test_transitions_and_unknown_preservation(self):
        with patch.object(app, 'notify') as notify:
            for state in ['available', 'available', 'unknown', 'available']:
                self.assertEqual(self.check(state), 0)
            self.assertEqual(notify.call_count, 1)
            self.check('unavailable')
            self.check('available')
            self.assertEqual(notify.call_count, 2)

    def test_failed_notification_is_retried(self):
        with patch.object(app, 'notify', side_effect=app.CheckError('Delivery failed')):
            self.assertEqual(self.check('available'), 1)
        self.assertFalse(app.STATE.exists())
        with patch.object(app, 'notify') as notify:
            self.assertEqual(self.check('available'), 0)
            notify.assert_called_once()

    def test_configuration_change(self):
        with patch.object(app, 'notify') as notify:
            self.check('available')
            with patch.dict(app.os.environ, {'APPLE_ZIP': '10001'}):
                self.check('available')
            self.assertEqual(notify.call_count, 2)

    def test_optional_slack(self):
        with patch.dict(app.os.environ, {'SLACK_WEBHOOK_URL': ''}), patch.object(app, 'notify') as notify:
            self.assertEqual(self.check('available'), 0)
            notify.assert_not_called()

    def test_webhook_payload(self):
        rows = app.parse_rows(fixture('available'), ['TEST/A'], set())
        with patch('urllib.request.urlopen') as send:
            send.return_value.__enter__.return_value.read.return_value = b'ok'
            app.notify('https://hooks.slack.com/services/test', rows)
            request = send.call_args.args[0]
            payload = json.loads(request.data)
            self.assertFalse(payload['mrkdwn'])
            self.assertIn('Tomorrow', payload['text'])
            self.assertEqual(request.method, 'POST')


if __name__ == '__main__':
    unittest.main()
