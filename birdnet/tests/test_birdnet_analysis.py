import importlib
import logging
import os
import queue
import sys
import tempfile
import types
import unittest
from subprocess import CalledProcessError
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

STUBS = {
    "inotify.adapters": {"Inotify": MagicMock},
    "inotify.constants": {"IN_CLOSE_WRITE": 0x8},
    "utils.analysis": {"load_global_model": lambda: None, "run_analysis": lambda file: []},
    "utils.reporting": {
        name: (lambda *args, **kwargs: None)
        for name in ("apprise", "bird_weather", "extract_detection", "heartbeat", "summary", "update_json_file", "write_to_db", "write_to_file")
    },
}


def stub_module(name, attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module


def load_daemon():
    before = dict(sys.modules)
    for name, attrs in STUBS.items():
        stub_module(name, attrs)
    try:
        return importlib.import_module("birdnet_analysis")
    finally:
        for name in [n for n in sys.modules if n not in before and n != "birdnet_analysis"]:
            del sys.modules[name]
        sys.modules.update(before)


birdnet_analysis = load_daemon()


class FakeNotifyQueue:
    def __init__(self, messages, size=0):
        self.messages = list(messages)
        self.size = size
        self.seen = []

    def get(self):
        return self.messages.pop(0)

    def qsize(self):
        return self.size

    def put(self, item):
        self.seen.append(item)


def detection(name="Pica pica"):
    return SimpleNamespace(scientific_name=name, file_name_extr=None)


class TestPrioritizedItem(unittest.TestCase):
    def test_orders_by_priority_only(self):
        items = [birdnet_analysis.PrioritizedItem(10, object()), birdnet_analysis.PrioritizedItem(0, object())]
        self.assertEqual([i.priority for i in sorted(items)], [0, 10])

    def test_equal_priorities_do_not_compare_the_payload(self):
        a = birdnet_analysis.PrioritizedItem(1, object())
        b = birdnet_analysis.PrioritizedItem(1, object())
        self.assertFalse(a < b)
        self.assertFalse(b < a)

    def test_priority_queue_drains_lowest_first(self):
        q = queue.PriorityQueue()
        for priority in (10, 0, 5):
            q.put(birdnet_analysis.PrioritizedItem(priority, f"item-{priority}"))
        self.assertEqual([q.get().priority for _ in range(3)], [0, 5, 10])


class TestSigHandler(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, birdnet_analysis, "shutdown", birdnet_analysis.shutdown)

    def test_sets_the_shutdown_flag(self):
        birdnet_analysis.shutdown = False
        birdnet_analysis.sig_handler(15, None)
        self.assertTrue(birdnet_analysis.shutdown)


class ProcessFileTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.analyzing = os.path.join(self.tmp.name, "analyzing_now.txt")
        self.queue = queue.Queue()

    def wav(self, contents=b"RIFF"):
        path = os.path.join(self.tmp.name, "sample.wav")
        with open(path, "wb") as f:
            f.write(contents)
        return path

    def process(self, path, run_analysis):
        with (
            patch.object(birdnet_analysis, "ANALYZING_NOW", self.analyzing),
            patch.object(birdnet_analysis, "ParseFileName", side_effect=lambda name: SimpleNamespace(file_name=name)),
            patch.object(birdnet_analysis, "run_analysis", run_analysis),
        ):
            birdnet_analysis.process_file(path, self.queue)


class TestProcessFile(ProcessFileTestCase):
    def test_empty_file_is_deleted_and_not_queued(self):
        path = self.wav(b"")
        self.process(path, MagicMock())
        self.assertFalse(os.path.exists(path))
        self.assertTrue(self.queue.empty())

    def test_queues_the_parsed_file_with_its_detections(self):
        path = self.wav()
        detections = [detection()]
        self.process(path, MagicMock(return_value=detections))
        file, queued = self.queue.get_nowait()
        self.assertEqual(file.file_name, path)
        self.assertIs(queued, detections)

    def test_records_the_file_being_analyzed(self):
        path = self.wav()
        self.process(path, MagicMock(return_value=[]))
        with open(self.analyzing) as f:
            self.assertEqual(f.read(), path)

    def test_analysis_failure_is_swallowed(self):
        path = self.wav()
        with self.assertLogs(birdnet_analysis.log, level="ERROR"):
            self.process(path, MagicMock(side_effect=RuntimeError("boom")))
        self.assertTrue(self.queue.empty())
        self.assertTrue(os.path.exists(path))

    def test_called_process_error_stderr_is_decoded(self):
        path = self.wav()
        error = CalledProcessError(1, ["sox"], stderr=b"sox failed")
        with self.assertLogs(birdnet_analysis.log, level="ERROR") as logs:
            self.process(path, MagicMock(side_effect=error))
        self.assertIn("sox failed", "\n".join(logs.output))

    def test_missing_file_is_swallowed(self):
        with self.assertLogs(birdnet_analysis.log, level="ERROR"):
            self.process(os.path.join(self.tmp.name, "gone.wav"), MagicMock())
        self.assertTrue(self.queue.empty())


class TestHandleReportingQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.queue = queue.Queue()
        self.notify = queue.PriorityQueue()
        self.reporting = {
            "update_json_file": MagicMock(),
            "extract_detection": MagicMock(return_value=os.path.join(self.tmp.name, "extracted", "Pica pica.wav")),
            "summary": MagicMock(return_value="summary"),
            "write_to_file": MagicMock(),
            "write_to_db": MagicMock(),
            "heartbeat": MagicMock(),
        }

    def source_file(self):
        path = os.path.join(self.tmp.name, "sample.wav")
        with open(path, "wb") as f:
            f.write(b"RIFF")
        return SimpleNamespace(file_name=path)

    def run_queue(self, *messages, **overrides):
        for message in messages:
            self.queue.put(message)
        self.queue.put(None)
        patches = {**self.reporting, **overrides}
        with patch.multiple(birdnet_analysis, **patches):
            birdnet_analysis.handle_reporting_queue(self.queue, self.notify)

    def test_reports_every_detection_and_hands_it_to_the_notifier(self):
        file = self.source_file()
        detections = [detection("Pica pica"), detection("Corvus corax")]
        self.run_queue((file, detections))
        self.reporting["update_json_file"].assert_called_once_with(file, detections)
        self.assertEqual(self.reporting["write_to_db"].call_count, 2)
        self.assertEqual(self.reporting["write_to_file"].call_count, 2)
        self.reporting["heartbeat"].assert_called_once_with()
        item = self.notify.get_nowait()
        self.assertEqual(item.priority, 10)
        self.assertEqual(item.item, (file, detections))

    def test_extracted_name_is_stored_on_the_detection(self):
        file = self.source_file()
        det = detection()
        self.run_queue((file, [det]))
        self.assertEqual(det.file_name_extr, self.reporting["extract_detection"].return_value)

    def test_source_recording_is_removed_once_reported(self):
        file = self.source_file()
        self.run_queue((file, []))
        self.assertFalse(os.path.exists(file.file_name))

    def test_a_reporting_failure_does_not_stop_the_loop(self):
        first, second = self.source_file(), self.source_file()
        with self.assertLogs(birdnet_analysis.log, level="ERROR"):
            self.run_queue((first, [detection()]), (second, []), write_to_db=MagicMock(side_effect=RuntimeError("boom")))
        self.assertEqual(self.reporting["update_json_file"].call_count, 2)
        self.assertEqual(self.notify.qsize(), 1)

    def test_none_terminates_and_balances_task_done(self):
        self.run_queue()
        self.assertEqual(self.queue.unfinished_tasks, 0)


class TestHandleNotifyQueue(unittest.TestCase):
    def setUp(self):
        self.apprise = MagicMock()
        self.bird_weather = MagicMock()

    def run_queue(self, messages, size=0):
        items = [birdnet_analysis.PrioritizedItem(10, m) for m in messages] + [birdnet_analysis.PrioritizedItem(0, None)]
        q = FakeNotifyQueue(items, size=size)
        with patch.multiple(birdnet_analysis, apprise=self.apprise, bird_weather=self.bird_weather):
            birdnet_analysis.handle_notify_queue(q)
        return q

    def test_notifies_both_sinks(self):
        message = (SimpleNamespace(file_name="a.wav"), [detection()])
        self.run_queue([message])
        self.apprise.assert_called_once_with(*message)
        self.bird_weather.assert_called_once_with(*message)

    def test_drops_everything_once_the_backlog_is_too_deep(self):
        self.run_queue([(SimpleNamespace(file_name="a.wav"), [])], size=201)
        self.apprise.assert_not_called()
        self.bird_weather.assert_not_called()

    def test_backlog_at_the_limit_still_notifies(self):
        self.run_queue([(SimpleNamespace(file_name="a.wav"), [])], size=200)
        self.apprise.assert_called_once()

    def test_a_notifier_failure_does_not_stop_the_loop(self):
        self.apprise.side_effect = RuntimeError("boom")
        messages = [(SimpleNamespace(file_name="a.wav"), []), (SimpleNamespace(file_name="b.wav"), [])]
        with self.assertLogs(birdnet_analysis.log, level="ERROR"):
            self.run_queue(messages)
        self.assertEqual(self.apprise.call_count, 2)
        self.bird_weather.assert_not_called()

    def test_none_terminates_immediately(self):
        q = self.run_queue([])
        self.assertEqual(q.messages, [])


class TestSetupLogging(unittest.TestCase):
    def setUp(self):
        root = logging.getLogger()
        self.addCleanup(root.setLevel, root.level)
        self.addCleanup(setattr, root, "handlers", list(root.handlers))
        self.addCleanup(setattr, birdnet_analysis, "log", birdnet_analysis.log)

    def test_installs_a_stdout_handler_at_info(self):
        before = len(logging.getLogger().handlers)
        birdnet_analysis.setup_logging()
        root = logging.getLogger()
        self.assertEqual(len(root.handlers), before + 1)
        self.assertEqual(root.level, logging.INFO)
        self.assertEqual(birdnet_analysis.log.name, "birdnet_analysis")


if __name__ == "__main__":
    unittest.main()
