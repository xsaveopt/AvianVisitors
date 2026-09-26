import os
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

BIRDNET_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDING = os.path.join(BIRDNET_DIR, "birdnet_recording.sh")
LIVESTREAM = os.path.join(BIRDNET_DIR, "livestream.sh")

STUB = """#!/usr/bin/env bash
printf '%s\\n' "$(basename "$0") $*" >> "$STUB_LOG"
if [ "$(basename "$0")" = ffmpeg ] && [ "$1" = -version ]; then
  echo "ffmpeg version ${STUB_FFMPEG_VERSION:-6.1.1} Copyright"
  exit 0
fi
if [ "$(basename "$0")" = pgrep ]; then
  exit "${STUB_PGREP_RC:-1}"
fi
if [ -n "$STUB_BLOCK" ]; then
  sleep 30
fi
exit 0
"""


@unittest.skipIf(shutil.which("bash") is None, "bash not available")
class ShellScriptTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin = os.path.join(self.tmp.name, "bin")
        os.mkdir(self.bin)
        for name in ("arecord", "ffmpeg", "pgrep"):
            path = os.path.join(self.bin, name)
            with open(path, "w") as f:
                f.write(STUB)
            os.chmod(path, 0o755)
        self.log = os.path.join(self.tmp.name, "calls.log")
        self.conf_path = os.path.join(self.tmp.name, "birdnet.conf")
        self.recs = os.path.join(self.tmp.name, "BirdSongs")
        self.conf = {
            "RECS_DIR": self.recs,
            "CHANNELS": "2",
            "RECORDING_LENGTH": "15",
            "MODEL": "BirdNET_GLOBAL_6K_V2.4_Model_FP16",
            "REC_CARD": "",
            "RTSP_STREAM": "",
            "ICE_PWD": "icepass",
        }

    def env(self, **extra):
        with open(self.conf_path, "w") as f:
            f.write("".join(f'{k}="{v}"\n' for k, v in self.conf.items()))
        env = {
            "PATH": f"{self.bin}:/usr/local/bin:/usr/bin:/bin",
            "HOME": self.tmp.name,
            "STUB_LOG": self.log,
            "AV_TEST_CONF": self.conf_path,
            "BASH_FUNC_source%%": '() { builtin source "$AV_TEST_CONF"; }',
        }
        env.update(extra)
        return env

    def run_script(self, script, **extra):
        return subprocess.run(["bash", script], env=self.env(**extra), capture_output=True, text=True, timeout=30)

    def calls(self, name=None):
        if not os.path.exists(self.log):
            return []
        lines = open(self.log).read().splitlines()
        return [line for line in lines if name is None or line.split(" ", 1)[0] == name]

    def run_until(self, script, name, count, **extra):
        proc = subprocess.Popen(["bash", script], env=self.env(STUB_BLOCK="1", **extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline and len([c for c in self.calls(name) if "-version" not in c]) < count:
                time.sleep(0.05)
        finally:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
        return [c for c in self.calls(name) if "-version" not in c]


class TestBirdnetRecording(ShellScriptTestCase):
    def test_records_from_default_card(self):
        result = self.run_script(RECORDING)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls("arecord")
        self.assertEqual(len(calls), 1)
        args = calls[0].split()
        self.assertIn("-c2", args)
        self.assertEqual(args[args.index("-r") + 1], "48000")
        self.assertEqual(args[args.index("--max-file-time") + 1], "15")
        self.assertNotIn("-D", args)
        self.assertEqual(args[-1], f"{self.recs}/StreamData/%F-birdnet-%H:%M:%S.wav")
        self.assertTrue(os.path.isdir(os.path.join(self.recs, "StreamData")))

    def test_uses_configured_card(self):
        self.conf["REC_CARD"] = "plughw:1,0"
        self.run_script(RECORDING)
        args = self.calls("arecord")[0].split()
        self.assertEqual(args[args.index("-D") + 1], "plughw:1,0")

    def test_perch_records_at_32k(self):
        self.conf["MODEL"] = "Perch_v2"
        self.run_script(RECORDING)
        args = self.calls("arecord")[0].split()
        self.assertEqual(args[args.index("-r") + 1], "32000")

    def test_missing_recording_length_defaults_to_15(self):
        self.conf["RECORDING_LENGTH"] = ""
        self.run_script(RECORDING)
        args = self.calls("arecord")[0].split()
        self.assertEqual(args[args.index("--max-file-time") + 1], "15")

    def test_skips_when_already_recording(self):
        result = self.run_script(RECORDING, STUB_PGREP_RC="0")
        self.assertIn("Recording", result.stdout)
        self.assertEqual(self.calls("arecord"), [])

    def test_one_ffmpeg_loop_per_stream(self):
        self.conf["RTSP_STREAM"] = "rtsp://cam.example/one,http://cam.example/two,/dev/null"
        calls = self.run_until(RECORDING, "ffmpeg", 3)
        self.assertEqual(len(calls), 3)
        by_input = {c.split()[c.split().index("-i") + 1]: c.split() for c in calls}
        rtsp = by_input["rtsp://cam.example/one"]
        self.assertEqual(rtsp[rtsp.index("-timeout") + 1], "10000000")
        self.assertTrue(rtsp[-1].endswith("/StreamData/%F-birdnet-RTSP_1-%H:%M:%S.wav"))
        self.assertEqual(rtsp[rtsp.index("-ar") + 1], "48000")
        http = by_input["http://cam.example/two"]
        self.assertEqual(http[http.index("-rw_timeout") + 1], "10000000")
        self.assertTrue(http[-1].endswith("RTSP_2-%H:%M:%S.wav"))
        local = by_input["/dev/null"]
        self.assertNotIn("-timeout", local)
        self.assertNotIn("-rw_timeout", local)
        self.assertEqual(self.calls("arecord"), [])

    def test_old_ffmpeg_uses_stimeout(self):
        self.conf["RTSP_STREAM"] = "rtsps://cam.example/one"
        calls = self.run_until(RECORDING, "ffmpeg", 1, STUB_FFMPEG_VERSION="4.4.2")
        args = calls[0].split()
        self.assertEqual(args[args.index("-stimeout") + 1], "10000000")


class TestLivestream(ShellScriptTestCase):
    def test_no_card_means_no_stream(self):
        result = self.run_script(LIVESTREAM)
        self.assertIn("Stream not supported", result.stdout)
        self.assertEqual(self.calls("ffmpeg"), [])

    def test_streams_alsa_card_to_icecast(self):
        self.conf["REC_CARD"] = "default"
        self.run_script(LIVESTREAM)
        args = self.calls("ffmpeg")[0].split()
        self.assertEqual(args[args.index("-f") + 1], "alsa")
        self.assertEqual(args[args.index("-i") + 1], "default")
        self.assertIn("icecast://source:icepass@localhost:8000/stream", args)
        self.assertNotIn("-af", args)

    def test_selects_configured_rtsp_stream(self):
        self.conf.update({"REC_CARD": "default", "RTSP_STREAM": "rtsp://cam.example/one,rtsp://cam.example/two", "RTSP_STREAM_TO_LIVESTREAM": "1"})
        self.run_script(LIVESTREAM)
        args = self.calls("ffmpeg")[0].split()
        self.assertEqual(args[args.index("-i") + 1], "rtsp://cam.example/two")

    def test_out_of_range_stream_index_falls_back_to_first(self):
        self.conf.update({"REC_CARD": "default", "RTSP_STREAM": "rtsp://cam.example/one,rtsp://cam.example/two", "RTSP_STREAM_TO_LIVESTREAM": "5"})
        self.run_script(LIVESTREAM)
        args = self.calls("ffmpeg")[0].split()
        self.assertEqual(args[args.index("-i") + 1], "rtsp://cam.example/one")

    def test_freqshift_adds_rubberband_filter(self):
        self.conf.update({"REC_CARD": "default", "ACTIVATE_FREQSHIFT_IN_LIVESTREAM": "true", "FREQSHIFT_LO": "3000", "FREQSHIFT_HI": "6000"})
        self.run_script(LIVESTREAM)
        args = self.calls("ffmpeg")[0].split()
        self.assertEqual(args[args.index("-af") + 1], "rubberband=pitch=3000/6000")


if __name__ == "__main__":
    unittest.main()
