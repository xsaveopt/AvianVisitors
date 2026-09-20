import io
import json
import tempfile
import types
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

import photos


def quiet(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


class TestSlugify(unittest.TestCase):
    CASES = [
        ("Pica pica", "pica-pica"),
        ("Cyanistes caeruleus", "cyanistes-caeruleus"),
        ("  Parus major  ", "parus-major"),
        ("Anna's Hummingbird", "anna-s-hummingbird"),
        ("Sylvia (Curruca) communis", "sylvia-curruca-communis"),
        ("---x---", "x"),
        ("", ""),
    ]

    def test_table(self):
        for raw, expected in self.CASES:
            with self.subTest(raw):
                self.assertEqual(photos.slugify(raw), expected)


class TestParseSpeciesLine(unittest.TestCase):
    CASES = [
        ("Pica pica|Eurasian Magpie", ("Pica pica", "Eurasian Magpie")),
        ("Pica pica_Eurasian Magpie", ("Pica pica", "Eurasian Magpie")),
        ("Pica pica,Eurasian Magpie", ("Pica pica", "Eurasian Magpie")),
        ("  Pica pica | Eurasian Magpie  ", ("Pica pica", "Eurasian Magpie")),
        ("Pica pica|Magpie|extra", ("Pica pica", "Magpie|extra")),
        ("Pica pica", ("Pica pica", "Pica pica")),
        ("# a comment", None),
        ("   # indented comment", None),
        ("", None),
        ("   ", None),
        ("Magpie", None),
    ]

    def test_table(self):
        for line, expected in self.CASES:
            with self.subTest(line):
                self.assertEqual(photos.parse_species_line(line), expected)

    def test_the_first_separator_present_wins(self):
        self.assertEqual(photos.parse_species_line("a_b|c"), ("a_b", "c"))

    def test_a_half_empty_pair_falls_through_to_the_bare_binomial_rule(self):
        for line in ("Pica pica|", "|Eurasian Magpie"):
            with self.subTest(line):
                self.assertEqual(photos.parse_species_line(line), (line, line))

    def test_a_half_empty_pair_without_a_space_is_dropped(self):
        self.assertIsNone(photos.parse_species_line("Pica|"))


class TestParseSpeciesList(unittest.TestCase):
    def test_counts_only_unparseable_content_lines(self):
        lines = ["Pica pica|Eurasian Magpie", "", "# note", "Magpie", "Parus major|Great Tit", "   "]
        out, skipped = photos.parse_species_list(lines)
        self.assertEqual(out, [("Pica pica", "Eurasian Magpie"), ("Parus major", "Great Tit")])
        self.assertEqual(skipped, 1)

    def test_an_empty_file(self):
        self.assertEqual(photos.parse_species_list([]), ([], 0))

    def test_comments_alone_are_not_skips(self):
        self.assertEqual(photos.parse_species_list(["# one", "  # two", ""]), ([], 0))


class TestStripHtml(unittest.TestCase):
    CASES = [
        ('<a href="/x">Jane Doe</a>', "Jane Doe"),
        ("<span>  Jane   Doe </span>", "Jane Doe"),
        ("plain", "plain"),
        ("", ""),
        (None, ""),
        ("<b>a</b> <i>b</i>", "a b"),
    ]

    def test_table(self):
        for raw, expected in self.CASES:
            with self.subTest(repr(raw)):
                self.assertEqual(photos._strip_html(raw), expected)


class TestWikiCredit(unittest.TestCase):
    def test_reads_the_file_metadata(self):
        info = {
            "extmetadata": {
                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                "Artist": {"value": '<a href="/u">Jane Doe</a>'},
                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
            },
            "descriptionurl": "https://commons.example/File:Pica.jpg",
            "url": "https://upload.example/Pica.jpg",
        }
        self.assertEqual(
            photos._wiki_credit(info, "https://thumb.example/Pica.jpg"),
            {
                "license": "CC BY-SA 4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                "attribution": "Jane Doe",
                "url": "https://commons.example/File:Pica.jpg",
                "image_url": "https://upload.example/Pica.jpg",
            },
        )

    def test_falls_back_to_credit_when_there_is_no_artist(self):
        info = {"extmetadata": {"Credit": {"value": "<p>Own work</p>"}}}
        self.assertEqual(photos._wiki_credit(info, "src")["attribution"], "Own work")

    def test_unknowns_and_the_source_url_fill_the_gaps(self):
        credit = photos._wiki_credit({}, "src")
        self.assertEqual(credit["license"], "unknown")
        self.assertEqual(credit["attribution"], "unknown")
        self.assertEqual(credit["license_url"], "")
        self.assertEqual((credit["url"], credit["image_url"]), ("src", "src"))

    def test_an_empty_artist_still_reads_as_unknown(self):
        info = {"extmetadata": {"Artist": {"value": "<span></span>"}}}
        self.assertEqual(photos._wiki_credit(info, "src")["attribution"], "unknown")


class TestSmallHelpers(unittest.TestCase):
    NORM = [("Pica_pica", "pica pica"), ("  File:A_B.jpg ", "file:a b.jpg"), ("Already lower", "already lower")]
    MIN_SIDE = [({"width": 800, "height": 600}, 600), ({"width": 300, "height": 900}, 300), ({}, 0), ({"width": 800}, 0)]
    SNIFF = [
        (b"\x89PNG\r\n\x1a\nrest", ".png"),
        (b"\xff\xd8\xff\xe0rest", ".jpg"),
        (b"GIF89a", None),
        (b"", None),
        (b"\x89PN", None),
    ]

    def test_norm(self):
        for raw, expected in self.NORM:
            with self.subTest(raw):
                self.assertEqual(photos._norm(raw), expected)

    def test_min_side(self):
        for info, expected in self.MIN_SIDE:
            with self.subTest(str(info)):
                self.assertEqual(photos._min_side(info), expected)

    def test_sniff(self):
        for data, expected in self.SNIFF:
            with self.subTest(repr(data[:4])):
                self.assertEqual(photos._sniff(data), expected)


class TestNonPhotoFilter(unittest.TestCase):
    REJECTED = [
        "file:pica pica range map.png",
        "file:distribution of pica.jpg",
        "file:pica sonogram.png",
        "file:pica egg.jpg",
        "file:pica nest.jpg",
        "file:pica skeleton.jpg",
        "file:naturalis specimen.jpg",
        "file:pica.svg",
        "file:pica song.ogg",
        "file:pica.gif",
        "file:pica.tiff",
        "file:commons logo.png",
    ]
    KEPT = [
        "file:pica pica perched.jpg",
        "file:eurasian magpie in flight.png",
        "file:pica pica close-up.jpeg",
    ]

    def test_non_photographs_are_rejected(self):
        for key in self.REJECTED:
            with self.subTest(key):
                self.assertIsNotNone(photos._NON_PHOTO.search(key))

    def test_photographs_are_kept(self):
        for key in self.KEPT:
            with self.subTest(key):
                self.assertIsNone(photos._NON_PHOTO.search(key))


class TestGet(unittest.TestCase):
    def fetch(self, outcome):
        opener = MagicMock()
        if isinstance(outcome, Exception):
            opener.side_effect = outcome
        else:
            opener.return_value.__enter__.return_value.read.return_value = outcome
        with patch.object(photos.urllib.request, "urlopen", opener):
            return photos._get("https://example/x", 30), opener

    def test_returns_the_body(self):
        body, _opener = self.fetch(b"payload")
        self.assertEqual(body, b"payload")

    def test_identifies_the_project(self):
        _body, opener = self.fetch(b"payload")
        self.assertEqual(opener.call_args[0][0].headers["User-agent"], photos.USER_AGENT)
        self.assertEqual(opener.call_args[1]["timeout"], 30)

    def test_network_failures_are_swallowed(self):
        failures = [
            urllib.error.HTTPError("https://example/x", 404, "gone", {}, None),
            urllib.error.URLError("unreachable"),
            TimeoutError("slow"),
        ]
        for failure in failures:
            with self.subTest(type(failure).__name__):
                body, _opener = self.fetch(failure)
                self.assertIsNone(body)

    def test_other_errors_still_propagate(self):
        with self.assertRaises(ValueError):
            self.fetch(ValueError("bug"))


class TestWriteCredits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "credits.json"

    def test_writes_readable_json_with_a_trailing_newline(self):
        photos.write_credits(self.path, {"pica-pica": {"attribution": "Jane"}})
        text = self.path.read_text()
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(json.loads(text), {"pica-pica": {"attribution": "Jane"}})

    def test_non_ascii_is_kept_verbatim(self):
        photos.write_credits(self.path, {"a": "Müller & Cía"})
        self.assertIn("Müller & Cía", self.path.read_text())

    def test_no_temporary_file_survives(self):
        photos.write_credits(self.path, {})
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ["credits.json"])

    def test_a_second_write_replaces_the_first(self):
        photos.write_credits(self.path, {"a": 1})
        photos.write_credits(self.path, {"b": 2})
        self.assertEqual(json.loads(self.path.read_text()), {"b": 2})


class TestIngestRejections(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rejected_dir = self.root / "rejected"
        self.rejected_path = self.root / "rejected.json"

    def drop(self, name, body=b"avif"):
        self.rejected_dir.mkdir(parents=True, exist_ok=True)
        (self.rejected_dir / name).write_bytes(body)

    def ingest(self, rejected, credits):
        quiet(photos.ingest_rejections, self.rejected_dir, self.rejected_path, rejected, credits)
        return rejected

    def test_nothing_to_do_leaves_the_tree_alone(self):
        self.ingest({}, {})
        self.assertFalse(self.rejected_path.exists())
        self.assertFalse((self.rejected_dir / "processed").exists())

    def test_an_empty_directory_is_also_a_no_op(self):
        self.rejected_dir.mkdir()
        self.ingest({}, {})
        self.assertFalse(self.rejected_path.exists())

    def test_both_recorded_urls_are_blocked(self):
        self.drop("pica-pica.avif")
        credits = {"pica-pica": {"image_url": "https://img/pica.jpg", "url": "https://page/pica"}}
        rejected = self.ingest({}, credits)
        self.assertEqual(rejected, {"pica-pica": ["https://img/pica.jpg", "https://page/pica"]})

    def test_blank_urls_are_dropped(self):
        self.drop("pica-pica.avif")
        rejected = self.ingest({}, {"pica-pica": {"image_url": "https://img/pica.jpg", "url": ""}})
        self.assertEqual(rejected["pica-pica"], ["https://img/pica.jpg"])

    def test_earlier_blocks_are_kept_and_deduplicated(self):
        self.drop("pica-pica.avif")
        existing = {"pica-pica": ["https://img/pica.jpg", "https://old/one"]}
        rejected = self.ingest(existing, {"pica-pica": {"image_url": "https://img/pica.jpg", "url": "https://page/pica"}})
        self.assertEqual(rejected["pica-pica"], ["https://img/pica.jpg", "https://old/one", "https://page/pica"])

    def test_a_cutout_without_a_credit_blocks_nothing(self):
        self.drop("pica-pica.avif")
        rejected = self.ingest({}, {})
        self.assertEqual(rejected, {})
        self.assertTrue((self.rejected_dir / "processed" / "pica-pica.avif").is_file())

    def test_the_file_is_moved_out_of_the_way(self):
        self.drop("pica-pica.avif", b"one")
        self.ingest({}, {"pica-pica": {"image_url": "https://img/pica.jpg"}})
        self.assertFalse((self.rejected_dir / "pica-pica.avif").exists())
        self.assertEqual((self.rejected_dir / "processed" / "pica-pica.avif").read_bytes(), b"one")

    def test_a_repeat_rejection_is_archived_alongside(self):
        self.drop("pica-pica.avif", b"one")
        self.ingest({}, {"pica-pica": {"image_url": "https://a"}})
        self.drop("pica-pica.avif", b"two")
        self.ingest({}, {"pica-pica": {"image_url": "https://b"}})
        archived = sorted(p.name for p in (self.rejected_dir / "processed").iterdir())
        self.assertEqual(archived, ["pica-pica-1.avif", "pica-pica.avif"])

    def test_the_blocklist_is_written_out(self):
        self.drop("pica-pica.avif")
        self.ingest({}, {"pica-pica": {"image_url": "https://img/pica.jpg"}})
        self.assertEqual(json.loads(self.rejected_path.read_text()), {"pica-pica": ["https://img/pica.jpg"]})

    def test_only_cutouts_are_ingested(self):
        self.drop("notes.txt")
        self.ingest({}, {})
        self.assertFalse(self.rejected_path.exists())


class WikiQueryTestCase(unittest.TestCase):
    def query(self, fn, payload, title="Pica_pica"):
        raw = payload if payload is None or isinstance(payload, bytes) else json.dumps(payload).encode()
        get = MagicMock(return_value=raw)
        with patch.object(photos, "_get", get):
            return fn(title), get


class TestPageImages(WikiQueryTestCase):
    PAGES = {
        "query": {
            "pages": {
                "1": {"title": "File:Pica_pica.jpg", "imageinfo": [{"width": 800, "height": 600, "mime": "image/jpeg"}]},
                "2": {"title": "File:Range_map.png", "imageinfo": [{"width": 200, "height": 200, "mime": "image/png"}]},
                "3": {"title": "File:No_info.jpg", "imageinfo": []},
            }
        }
    }

    def test_keys_are_normalised_titles(self):
        images, _get = self.query(photos._page_images, self.PAGES)
        self.assertEqual(sorted(images), ["file:pica pica.jpg", "file:range map.png"])

    def test_the_first_imageinfo_entry_is_kept(self):
        images, _get = self.query(photos._page_images, self.PAGES)
        self.assertEqual(images["file:pica pica.jpg"]["width"], 800)

    def test_it_asks_for_a_capped_thumbnail(self):
        _images, get = self.query(photos._page_images, self.PAGES)
        self.assertIn(f"iiurlwidth={photos.WIKI_THUMB_WIDTH}", get.call_args[0][0])

    def test_a_failed_request_is_empty(self):
        self.assertEqual(self.query(photos._page_images, None)[0], {})

    def test_malformed_json_is_empty(self):
        self.assertEqual(self.query(photos._page_images, b"<html>")[0], {})

    def test_a_response_without_pages_is_empty(self):
        self.assertEqual(self.query(photos._page_images, {"query": {}})[0], {})


class TestLeadTitle(WikiQueryTestCase):
    def test_returns_the_normalised_file_title(self):
        payload = {"query": {"pages": {"1": {"pageimage": "Pica_pica_lead.jpg"}}}}
        self.assertEqual(self.query(photos._lead_title, payload)[0], "file:pica pica lead.jpg")

    def test_a_page_without_one_is_none(self):
        self.assertIsNone(self.query(photos._lead_title, {"query": {"pages": {"1": {}}}})[0])

    def test_a_failed_request_is_none(self):
        self.assertIsNone(self.query(photos._lead_title, None)[0])

    def test_malformed_json_is_none(self):
        self.assertIsNone(self.query(photos._lead_title, b"nope")[0])


class TestPageOrder(WikiQueryTestCase):
    def test_maps_each_file_to_its_position(self):
        payload = {"parse": {"images": ["First.jpg", "Second_one.png"]}}
        self.assertEqual(self.query(photos._page_order, payload)[0], {"file:first.jpg": 0, "file:second one.png": 1})

    def test_no_images_is_empty(self):
        self.assertEqual(self.query(photos._page_order, {"parse": {}})[0], {})

    def test_a_failed_request_is_empty(self):
        self.assertEqual(self.query(photos._page_order, None)[0], {})

    def test_malformed_json_is_empty(self):
        self.assertEqual(self.query(photos._page_order, b"nope")[0], {})


class TestFetchWiki(unittest.TestCase):
    def photo(self, width=800, height=600, mime="image/jpeg", url=None):
        info = {"width": width, "height": height, "mime": mime}
        if url:
            info["url"] = url
        return info

    def run_fetch(self, images, lead=None, order=None, evaluate=None, blocked=frozenset(), com="Eurasian Magpie"):
        seen = []

        def record(info, session, name):
            seen.append(name)
            return evaluate(info, name) if evaluate else None

        with (
            patch.object(photos, "_page_images", side_effect=lambda title: images.get(title, {})),
            patch.object(photos, "_lead_title", return_value=lead),
            patch.object(photos, "_page_order", return_value=order or {}),
            patch.object(photos, "_evaluate", side_effect=record),
            redirect_stdout(io.StringIO()),
        ):
            hit = photos.fetch_wiki("Pica pica", com, None, set(blocked))
        return hit, seen

    def test_the_lead_photo_is_tried_first(self):
        images = {
            "Pica_pica": {
                "file:b.jpg": self.photo(),
                "file:lead.jpg": self.photo(),
                "file:a.jpg": self.photo(),
            }
        }
        _hit, seen = self.run_fetch(images, lead="file:lead.jpg", order={"file:a.jpg": 0, "file:b.jpg": 1})
        self.assertEqual([name.split("] ")[1].split(" (")[0] for name in seen], ["lead.jpg", "a.jpg", "b.jpg"])

    def test_page_order_beats_files_missing_from_the_article(self):
        images = {"Pica_pica": {"file:unlisted.jpg": self.photo(), "file:second.jpg": self.photo()}}
        _hit, seen = self.run_fetch(images, order={"file:second.jpg": 3})
        self.assertTrue(seen[0].startswith("[#3]"))

    def test_the_first_usable_photo_wins(self):
        images = {"Pica_pica": {"file:a.jpg": self.photo(), "file:b.jpg": self.photo()}}
        hit, seen = self.run_fetch(images, order={"file:a.jpg": 0, "file:b.jpg": 1}, evaluate=lambda info, name: {"data": name})
        self.assertEqual(hit, {"data": seen[0]})
        self.assertEqual(len(seen), 1)

    def test_only_real_photo_mime_types_are_considered(self):
        images = {
            "Pica_pica": {
                "file:a.svg": self.photo(mime="image/svg+xml"),
                "file:b.jpg": self.photo(mime="image/jpeg"),
            }
        }
        _hit, seen = self.run_fetch(images)
        self.assertEqual(len(seen), 1)

    def test_small_frames_are_dropped(self):
        images = {"Pica_pica": {"file:tiny.jpg": self.photo(width=photos.MIN_FRAME - 1, height=900)}}
        _hit, seen = self.run_fetch(images)
        self.assertEqual(seen, [])

    def test_maps_and_diagrams_are_dropped(self):
        images = {"Pica_pica": {"file:range map.png": self.photo(mime="image/png")}}
        _hit, seen = self.run_fetch(images)
        self.assertEqual(seen, [])

    def test_previously_rejected_urls_are_skipped(self):
        images = {"Pica_pica": {"file:a.jpg": self.photo(url="https://img/a.jpg"), "file:b.jpg": self.photo(url="https://img/b.jpg")}}
        _hit, seen = self.run_fetch(images, blocked={"https://img/a.jpg"})
        self.assertEqual(len(seen), 1)
        self.assertIn("b.jpg", seen[0])

    def test_it_stops_at_the_matte_cap(self):
        images = {"Pica_pica": {f"file:{i}.jpg": self.photo() for i in range(photos.MATTE_CAP + 5)}}
        _hit, seen = self.run_fetch(images)
        self.assertEqual(len(seen), photos.MATTE_CAP)

    def test_the_common_name_article_is_the_fallback(self):
        images = {"Eurasian_Magpie": {"file:a.jpg": self.photo()}}
        _hit, seen = self.run_fetch(images, evaluate=lambda info, name: None)
        self.assertEqual(len(seen), 1)

    def test_no_article_at_all_returns_none(self):
        hit, seen = self.run_fetch({})
        self.assertIsNone(hit)
        self.assertEqual(seen, [])


class TestInatPhotos(unittest.TestCase):
    TAXON = {"results": [{"id": 12, "default_photo": {"id": 1}}]}
    FULL = {"results": [{"taxon_photos": [{"photo": {"id": 2}}, {}, {"photo": {"id": 3}}]}]}

    def run_lookup(self, responses):
        payloads = [None if r is None else (r if isinstance(r, bytes) else json.dumps(r).encode()) for r in responses]
        get = MagicMock(side_effect=payloads)
        with patch.object(photos, "_get", get):
            return photos._inat_photos("Pica pica"), get

    def test_default_photo_leads_the_gallery(self):
        found, _get = self.run_lookup([self.TAXON, self.FULL])
        self.assertEqual(found, (12, [{"id": 1}, {"id": 2}, {"id": 3}]))

    def test_a_missing_default_photo_is_fine(self):
        found, _get = self.run_lookup([{"results": [{"id": 12}]}, self.FULL])
        self.assertEqual(found[1], [{"id": 2}, {"id": 3}])

    def test_it_asks_for_a_single_species_match(self):
        _found, get = self.run_lookup([self.TAXON, self.FULL])
        self.assertIn("rank=species", get.call_args_list[0][0][0])

    def test_a_failed_lookup_is_none(self):
        self.assertIsNone(self.run_lookup([None])[0])

    def test_malformed_json_is_none(self):
        self.assertIsNone(self.run_lookup([b"<html>"])[0])

    def test_an_unknown_species_is_none(self):
        self.assertIsNone(self.run_lookup([{"results": []}])[0])

    def test_a_failed_gallery_still_returns_the_default(self):
        found, _get = self.run_lookup([self.TAXON, None])
        self.assertEqual(found, (12, [{"id": 1}]))

    def test_a_malformed_gallery_still_returns_the_default(self):
        found, _get = self.run_lookup([self.TAXON, b"<html>"])
        self.assertEqual(found, (12, [{"id": 1}]))


class TestFetchInat(unittest.TestCase):
    def photo(self, pid=1, code="cc-by", url="https://static/1/square.jpg", attribution="(c) Jane"):
        return {"id": pid, "license_code": code, "url": url, "attribution": attribution}

    def run_fetch(self, photo_list, licenses=("cc0", "cc-by"), blocked=frozenset(), body=b"\xff\xd8\xff\x00"):
        get = MagicMock(return_value=body)
        with (
            patch.object(photos, "_inat_photos", return_value=(12, photo_list) if photo_list is not None else None),
            patch.object(photos, "_get", get),
        ):
            return photos.fetch_inat("Pica pica", list(licenses), set(blocked)), get

    def test_builds_the_full_credit(self):
        hit, _get = self.run_fetch([self.photo()])
        self.assertEqual(
            hit,
            {
                "data": b"\xff\xd8\xff\x00",
                "ext": ".jpg",
                "source": "iNaturalist",
                "license": "cc-by",
                "license_url": photos.CC_URLS["cc-by"],
                "attribution": "(c) Jane",
                "url": "https://www.inaturalist.org/photos/1",
                "image_url": "https://static/1/large.jpg",
            },
        )

    def test_it_downloads_the_large_rendition(self):
        _hit, get = self.run_fetch([self.photo()])
        self.assertEqual(get.call_args[0][0], "https://static/1/large.jpg")

    def test_disallowed_licences_are_skipped(self):
        hit, _get = self.run_fetch([self.photo(code="cc-by-nd")])
        self.assertIsNone(hit)

    def test_a_missing_licence_is_skipped(self):
        hit, _get = self.run_fetch([{"id": 1, "url": "https://static/1/square.jpg"}])
        self.assertIsNone(hit)

    def test_licence_matching_ignores_case(self):
        hit, _get = self.run_fetch([self.photo(code="CC-BY")])
        self.assertEqual(hit["license"], "cc-by")

    def test_urls_without_a_square_rendition_are_skipped(self):
        hit, _get = self.run_fetch([self.photo(url="https://static/1/original.jpg")])
        self.assertIsNone(hit)

    def test_blocked_photos_are_skipped(self):
        hit, _get = self.run_fetch([self.photo()], blocked={"https://static/1/large.jpg"})
        self.assertIsNone(hit)

    def test_the_photo_page_can_be_blocked_too(self):
        hit, _get = self.run_fetch([self.photo()], blocked={"https://www.inaturalist.org/photos/1"})
        self.assertIsNone(hit)

    def test_an_undownloadable_photo_is_skipped(self):
        hit, _get = self.run_fetch([self.photo()], body=None)
        self.assertIsNone(hit)

    def test_a_body_that_is_not_an_image_is_skipped(self):
        hit, _get = self.run_fetch([self.photo()], body=b"<html>")
        self.assertIsNone(hit)

    def test_the_first_allowed_photo_wins(self):
        photo_list = [self.photo(pid=1, code="cc-by-nd"), self.photo(pid=2, url="https://static/2/square.jpg")]
        hit, _get = self.run_fetch(photo_list)
        self.assertEqual(hit["image_url"], "https://static/2/large.jpg")

    def test_an_unknown_species_is_none(self):
        hit, _get = self.run_fetch(None)
        self.assertIsNone(hit)

    def test_an_unmapped_licence_has_no_url(self):
        hit, _get = self.run_fetch([self.photo(code="cc-by-nc-nd")], licenses=("cc-by-nc-nd",))
        self.assertEqual(hit["license_url"], photos.CC_URLS["cc-by-nc-nd"])


class TestFetchPhoto(unittest.TestCase):
    def test_wikipedia_wins_when_it_has_something(self):
        with (
            patch.object(photos, "fetch_wiki", return_value={"source": "Wikimedia Commons"}),
            patch.object(photos, "fetch_inat") as inat,
        ):
            hit = quiet(photos.fetch_photo, "Pica pica", "Magpie", ["cc0"], None, set())
        self.assertEqual(hit["source"], "Wikimedia Commons")
        inat.assert_not_called()

    def test_it_falls_back_to_inaturalist(self):
        with (
            patch.object(photos, "fetch_wiki", return_value=None),
            patch.object(photos, "fetch_inat", return_value={"source": "iNaturalist"}) as inat,
        ):
            hit = quiet(photos.fetch_photo, "Pica pica", "Magpie", ["cc0"], None, {"https://x"})
        self.assertEqual(hit["source"], "iNaturalist")
        self.assertEqual(inat.call_args[0], ("Pica pica", ["cc0"], {"https://x"}))

    def test_neither_source_has_a_photo(self):
        with patch.object(photos, "fetch_wiki", return_value=None), patch.object(photos, "fetch_inat", return_value=None):
            self.assertIsNone(quiet(photos.fetch_photo, "Pica pica", "Magpie", ["cc0"], None, set()))


class TestEbirdFilter(unittest.TestCase):
    TAXONOMY = [
        {"speciesCode": "eurmag1", "sciName": "Pica pica", "comName": "Eurasian Magpie"},
        {"speciesCode": "gretit1", "sciName": "Parus major", "comName": "Great Tit"},
        {"speciesCode": "comrav", "sciName": "Corvus corax", "comName": "Common Raven"},
    ]

    def run_filter(self, species, region="NL", regional_codes=None, sci_to_com=None):
        codes = regional_codes if regional_codes is not None else {"NL": ["eurmag1", "gretit1"]}
        responses = [json.dumps(codes[reg.strip()]).encode() for reg in region.split(",") if reg.strip()]
        responses.append(json.dumps(self.TAXONOMY).encode())
        opener = MagicMock()
        opener.return_value.__enter__.return_value.read.side_effect = responses
        with patch.object(photos.urllib.request, "urlopen", opener), redirect_stdout(io.StringIO()):
            return photos.ebird_filter(species, region, "key", sci_to_com), opener

    def test_keeps_the_species_present_in_the_region(self):
        out, _opener = self.run_filter([("Pica pica", "Magpie"), ("Corvus corax", "Raven")])
        self.assertEqual(out, [("Pica pica", "Eurasian Magpie")])

    def test_the_ebird_common_name_replaces_the_local_one(self):
        out, _opener = self.run_filter([("Parus major", "Koolmees")])
        self.assertEqual(out, [("Parus major", "Great Tit")])

    def test_regions_are_unioned(self):
        codes = {"NL": ["eurmag1"], "BE": ["comrav"]}
        out, _opener = self.run_filter([("Pica pica", "Magpie"), ("Corvus corax", "Raven")], region="NL, BE", regional_codes=codes)
        self.assertEqual(sorted(out), [("Corvus corax", "Common Raven"), ("Pica pica", "Eurasian Magpie")])

    def test_the_api_token_is_sent(self):
        _out, opener = self.run_filter([])
        self.assertEqual(opener.call_args_list[0][0][0].headers["X-ebirdapitoken"], "key")

    def test_a_renamed_species_is_recovered_by_common_name(self):
        out, _opener = self.run_filter([("Pica pica pica", "Eurasian Magpie")])
        self.assertEqual(out, [("Pica pica pica", "Eurasian Magpie")])

    def test_recovery_can_come_from_the_supplied_map(self):
        out, _opener = self.run_filter([("Pica pica pica", "Pica pica pica")], sci_to_com={"Pica pica pica": "eurasian magpie"})
        self.assertEqual(out, [("Pica pica pica", "Eurasian Magpie")])

    def test_a_species_with_no_match_at_all_is_dropped(self):
        out, _opener = self.run_filter([("Nonexistent bird", "Nonexistent bird")])
        self.assertEqual(out, [])

    def test_an_empty_region_list_keeps_nothing(self):
        out, _opener = self.run_filter([("Pica pica", "Magpie")], region=" , ", regional_codes={})
        self.assertEqual(out, [])


class TestAvifOk(unittest.TestCase):
    def test_the_plugin_is_enough(self):
        with patch.dict("sys.modules", {"pillow_avif": types.ModuleType("pillow_avif")}):
            self.assertTrue(photos.avif_ok())

    def test_it_asks_pillow_when_the_plugin_is_missing(self):
        features = types.ModuleType("PIL.features")
        features.check = lambda name: name == "avif"
        pil = types.ModuleType("PIL")
        pil.features = features
        with patch.dict("sys.modules", {"pillow_avif": None, "PIL": pil, "PIL.features": features}):
            self.assertTrue(photos.avif_ok())

    def test_pillow_without_avif_support(self):
        features = types.ModuleType("PIL.features")
        features.check = lambda name: False
        pil = types.ModuleType("PIL")
        pil.features = features
        with patch.dict("sys.modules", {"pillow_avif": None, "PIL": pil, "PIL.features": features}):
            self.assertFalse(photos.avif_ok())


class TestLicenceTable(unittest.TestCase):
    def test_the_defaults_are_all_mapped(self):
        for code in photos.DEFAULT_LICENSES:
            with self.subTest(code):
                self.assertIn(code, photos.CC_URLS)

    def test_every_url_is_a_creative_commons_one(self):
        for code, url in photos.CC_URLS.items():
            with self.subTest(code):
                self.assertTrue(url.startswith("https://creativecommons.org/"))


if __name__ == "__main__":
    unittest.main()
