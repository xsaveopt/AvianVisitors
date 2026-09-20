import io
import tarfile
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import archive


class ArchiveTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.illus = self.root / "illustrations"
        self.illus.mkdir()
        self.tar = self.root / "illustrations.tar"

    def cutout(self, name, body=b"avif"):
        path = self.illus / name
        path.write_bytes(body)
        return path

    def write_tar(self, entries, names=()):
        with tarfile.open(self.tar, "w") as tar:
            for name, body in entries:
                info = tarfile.TarInfo(name=name)
                info.size = len(body)
                tar.addfile(info, io.BytesIO(body))
            for name in names:
                tar.addfile(tarfile.TarInfo(name=name))


class TestTarFor(unittest.TestCase):
    CASES = [
        (Path("/a/b/illustrations"), Path("/a/b/illustrations.tar")),
        (Path("/a/b/cutouts"), Path("/a/b/cutouts.tar")),
        (Path("illustrations"), Path("illustrations.tar")),
    ]

    def test_table(self):
        for illus, expected in self.CASES:
            with self.subTest(str(illus)):
                self.assertEqual(archive.tar_for(illus), expected)

    def test_module_paths_agree(self):
        self.assertEqual(archive.tar_for(archive.ILLUS_DIR), archive.TAR_PATH)


class TestPack(ArchiveTestCase):
    def test_returns_the_number_packed(self):
        self.cutout("pica-pica.avif")
        self.cutout("parus-major.avif")
        self.assertEqual(archive.pack(self.illus), 2)

    def test_members_are_sorted_and_flat(self):
        for name in ("pica-pica.avif", "corvus-corax.avif", "parus-major.avif"):
            self.cutout(name)
        archive.pack(self.illus)
        with tarfile.open(self.tar) as tar:
            self.assertEqual(tar.getnames(), ["corvus-corax.avif", "parus-major.avif", "pica-pica.avif"])

    def test_metadata_is_zeroed(self):
        self.cutout("pica-pica.avif")
        archive.pack(self.illus)
        with tarfile.open(self.tar) as tar:
            member = tar.getmember("pica-pica.avif")
        self.assertEqual((member.mtime, member.mode, member.uid, member.gid), (0, 0o644, 0, 0))
        self.assertEqual((member.uname, member.gname), ("", ""))

    def test_an_unchanged_set_packs_to_the_same_bytes(self):
        self.cutout("pica-pica.avif")
        archive.pack(self.illus)
        first = self.tar.read_bytes()
        archive.pack(self.illus)
        self.assertEqual(self.tar.read_bytes(), first)

    def test_only_cutouts_are_packed(self):
        self.cutout("pica-pica.avif")
        (self.illus / "notes.txt").write_text("ignore me")
        (self.illus / "pica-pica.png").write_bytes(b"png")
        self.assertEqual(archive.pack(self.illus), 1)

    def test_an_empty_directory_writes_an_empty_tar(self):
        self.assertEqual(archive.pack(self.illus), 0)
        with tarfile.open(self.tar) as tar:
            self.assertEqual(tar.getnames(), [])

    def test_contents_survive_the_round_trip(self):
        self.cutout("pica-pica.avif", b"\x00\x01binary")
        archive.pack(self.illus)
        with tarfile.open(self.tar) as tar:
            self.assertEqual(tar.extractfile("pica-pica.avif").read(), b"\x00\x01binary")

    def test_no_temporary_file_is_left_behind(self):
        self.cutout("pica-pica.avif")
        archive.pack(self.illus)
        self.assertEqual(sorted(p.name for p in self.root.glob("*.tmp")), [])

    def test_a_failure_leaves_the_previous_tar_intact(self):
        self.cutout("pica-pica.avif")
        archive.pack(self.illus)
        before = self.tar.read_bytes()
        with patch.object(archive.tarfile, "open", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                archive.pack(self.illus)
        self.assertEqual(self.tar.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.root.glob("*.tmp")), [])


class TestUnpack(ArchiveTestCase):
    def test_no_tar_restores_nothing(self):
        self.assertEqual(archive.unpack(self.illus), 0)

    def test_restores_every_missing_cutout(self):
        self.write_tar([("pica-pica.avif", b"one"), ("parus-major.avif", b"two")])
        self.assertEqual(archive.unpack(self.illus), 2)
        self.assertEqual((self.illus / "pica-pica.avif").read_bytes(), b"one")

    def test_existing_files_are_left_untouched(self):
        self.cutout("pica-pica.avif", b"mine")
        self.write_tar([("pica-pica.avif", b"theirs"), ("parus-major.avif", b"two")])
        self.assertEqual(archive.unpack(self.illus), 1)
        self.assertEqual((self.illus / "pica-pica.avif").read_bytes(), b"mine")

    def test_non_cutouts_and_nested_names_are_skipped(self):
        self.write_tar([("notes.txt", b"x"), ("nested/pica-pica.avif", b"y"), ("ok.avif", b"z")], names=("adir",))
        self.assertEqual(archive.unpack(self.illus), 1)
        self.assertEqual(sorted(p.name for p in self.illus.iterdir()), ["ok.avif"])

    def test_the_directory_is_created_when_missing(self):
        target = self.root / "fresh"
        self.write_tar([("pica-pica.avif", b"one")])
        self.assertEqual(archive.unpack(target, self.tar), 1)
        self.assertTrue((target / "pica-pica.avif").is_file())

    def test_an_explicit_tar_path_wins(self):
        other = self.root / "elsewhere.tar"
        with tarfile.open(other, "w") as tar:
            info = tarfile.TarInfo(name="pica-pica.avif")
            info.size = 3
            tar.addfile(info, io.BytesIO(b"one"))
        self.assertEqual(archive.unpack(self.illus, other), 1)

    def test_no_temporary_file_is_left_behind(self):
        self.write_tar([("pica-pica.avif", b"one")])
        archive.unpack(self.illus)
        self.assertEqual(sorted(p.name for p in self.illus.glob("*.tmp")), [])


class TestMain(ArchiveTestCase):
    def run_main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = archive.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_pack_reports_the_count(self):
        self.cutout("pica-pica.avif")
        code, out, _err = self.run_main(["pack", "--illustrations", str(self.illus)])
        self.assertEqual(code, 0)
        self.assertIn("packed 1 cutout(s)", out)
        self.assertTrue(self.tar.is_file())

    def test_unpack_reports_the_count(self):
        self.write_tar([("pica-pica.avif", b"one")])
        code, out, _err = self.run_main(["unpack", "--illustrations", str(self.illus)])
        self.assertEqual(code, 0)
        self.assertIn("restored 1 cutout(s)", out)

    def test_unpack_without_a_tar_fails(self):
        code, _out, err = self.run_main(["unpack", "--illustrations", str(self.illus)])
        self.assertEqual(code, 1)
        self.assertIn("no tar at", err)

    def test_an_unknown_action_is_rejected(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            archive.main(["squash"])


if __name__ == "__main__":
    unittest.main()
