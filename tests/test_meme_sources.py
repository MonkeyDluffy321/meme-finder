from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from utils import meme_sources as sources
from utils.meme_index import load_index
from utils.meme_search import search_finished_memes


def record(**changes):
    return dict(dict(id="abc123", image_url="/memes/waffles-abc123.png",
                     text_content=json.dumps([{"text": "Weekend"}, {"text": "waffles"}])), **changes)


class SourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "index.json"
        self.config = Path(temp.name) / "sources.json"
        self.config.write_text(json.dumps({"sources": [{"name": "GenMyMeme", "approved": True,
                                                       "seeds": [sources.ORIGIN + "/"]}]}))
        self.robots = b"User-agent: *\nAllow: /\n"
        self.payload = {"memes": [record()]}
        self.requests = []
        for target, kwargs in [
            ("utils.meme_sources.download_resource", dict(side_effect=self.download)),
            ("utils.meme_sources.sleep", {}),
            ("socket.socket.connect", dict(side_effect=AssertionError("Tests must stay offline"))),
        ]:
            mock = patch(target, **kwargs)
            mock.start()
            self.addCleanup(mock.stop)

    def download(self, url, **kwargs):
        self.requests.append((url, kwargs))
        if url == sources.ORIGIN + "/robots.txt":
            return self.robots
        self.assertEqual(url, sources.GALLERY)
        self.assertTrue(kwargs["respect_indexing"])
        self.assertEqual(kwargs["timeout"], sources.REQUEST_TIMEOUT)
        return json.dumps(self.payload).encode()

    def run_source(self, **kwargs):
        return sources.run_sources(index_path=self.path, config_path=self.config, **kwargs)["sources"][0]

    def test_real_response_mapping_provenance_and_search_without_template(self):
        report = self.run_source()
        self.assertEqual((report["provider"], report["accepted"], report["index_size"]), ("genmymeme", 1, 1))
        row = load_index(self.path)[0]
        self.assertEqual(row["caption_text"], "Weekend\nwaffles")
        self.assertEqual(row["source_page"], sources.ORIGIN + "/m/abc123")
        self.assertEqual(row["image_url"], sources.ORIGIN + "/memes/waffles-abc123.png")
        self.assertEqual((row["template_id"], row["language"]), ("", "und"))
        self.assertEqual(row["provenance"][0]["meme_id"], "abc123")
        self.assertEqual(search_finished_memes("Weekend waffles", index_path=self.path)[0]["meme_id"], "abc123")
        self.assertEqual(len(self.requests), 2)  # robots + one JSON response, no images

    def test_optional_metadata(self):
        self.payload["memes"] = [record(tags=["Breakfast"], description="Weekend food",
                                        language="en", template_id="unknown", template_name="Unknown")]
        self.run_source()
        row = load_index(self.path)[0]
        self.assertEqual((row["topics"], row["situation"], row["template_id"]), (["breakfast"], "Weekend food", "unknown"))

    def test_malformed_remote_records_are_isolated(self):
        bad = [None, {}, record(id=[]), record(text_content="bad json"),
               record(text_content='[{"text": 1}]'), record(text_content="[]"),
               record(image_url="https://other.example/image.png"), record(image_url="/memes/a.gif"),
               record(image_url="https://[broken"), record(tags="bad"),
               record(text_content='[{"text":" "}]'), record(image_url="/memes/../admin/x.png")]
        self.payload["memes"] = [*bad, record()]
        report = self.run_source()
        self.assertEqual((report["invalid"], report["accepted"]), (len(bad), 1))

    def test_limit_and_duplicate_determinism(self):
        self.payload["memes"] = [record(), record(), record(id="second", text_content='[{"text":"Monday misery"}]')]
        report = self.run_source(limit=2)
        self.assertEqual((report["received"], report["duplicates"], report["index_size"]), (2, 1, 1))
        before = self.path.read_bytes()
        repeat = self.run_source(limit=2)
        self.assertEqual(repeat["duplicates"], 2)
        self.assertFalse(repeat["written"])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(self.run_source(limit=3)["index_size"], 2)

    def test_invalid_limit_before_network(self):
        for limit in (0, 51, True):
            with self.assertRaises(ValueError):
                self.run_source(limit=limit)
        self.assertEqual(self.requests, [])

    def test_robots_denial_missing_and_excessive_delay(self):
        for robots in (b"User-agent: *\nDisallow: /api/", b"", b"<html>challenge</html>",
                       b"User-agent: *\nCrawl-delay: 30\n", b"User-agent: *\nRequest-rate: 1/60\n"):
            with self.subTest(robots=robots):
                self.requests.clear()
                self.robots = robots
                report = self.run_source()
                self.assertTrue(report["errors"])
                self.assertEqual(report["accepted"], 0)
                self.assertEqual(len(self.requests), 1)
                self.assertFalse(self.path.exists())

    def test_robots_image_and_source_restrictions(self):
        for path in ("/memes/", "/m/"):
            self.robots = f"User-agent: *\nDisallow: {path}\n".encode()
            self.assertEqual(self.run_source()["invalid"], 1)

    def test_robots_delay_and_request_rate_respected(self):
        self.robots = b"User-agent: *\nCrawl-delay: 2\nRequest-rate: 1/3\n"
        with patch("utils.meme_sources.sleep") as wait:
            self.run_source()
        self.assertEqual([call.args[0] for call in wait.call_args_list], [1, 3])

    def test_disabled_approval_blocks_network(self):
        config = json.loads(self.config.read_text())
        config["sources"][0]["approved"] = False
        self.config.write_text(json.dumps(config))
        self.assertTrue(self.run_source()["errors"])
        self.assertEqual(self.requests, [])

    def test_timeout_http_access_errors_and_bad_envelope(self):
        for error in (TimeoutError("timeout"), ValueError("HTTP 403"), ValueError("HTTP 429"), ValueError("noindex")):
            with patch("utils.meme_sources.download_resource", side_effect=[self.robots, error]) as fetch:
                report = self.run_source()
                self.assertEqual(fetch.call_count, 2)
                self.assertTrue(report["errors"])
                self.assertIn(str(error), report["source_error"])
        self.payload = {"error": "unavailable"}
        self.assertTrue(self.run_source()["errors"])
        self.assertFalse(self.path.exists())

    def test_provider_failure_isolation(self):
        class Broken(sources.GenMyMemeProvider):
            def records(self):
                raise TimeoutError("offline")

        with patch.dict(sources.PROVIDERS, {"broken": Broken}):
            report = sources.run_sources(["broken", "genmymeme"], index_path=self.path, config_path=self.config)
        self.assertTrue(report["sources"][0]["errors"])
        self.assertEqual(report["sources"][1]["accepted"], 1)
        self.assertEqual(report["index_size"], 1)

    def test_cli_reports_and_uses_selected_index(self):
        output = StringIO()
        with redirect_stdout(output):
            status = sources.main(["--provider", "genmymeme", "--limit", "1", "--index", str(self.path),
                                   "--config", str(self.config)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["sources"][0]["received"], 1)
