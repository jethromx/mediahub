#!/usr/bin/env python3
"""
Tests de las funciones puras de los scripts de mediahub.

Ejecutar desde la raíz del proyecto:
    python3 -m unittest discover tests
(o)  python3 tests/test_scripts.py
"""

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


tag_music  = _load("tag_music")
youtube_dl = _load("youtube_dl")


class TestTagMusicNorm(unittest.TestCase):
    def test_lowercase_and_accents(self):
        self.assertEqual(tag_music.norm("Tití Me Preguntó"), "titi me pregunto")

    def test_strips_feat(self):
        self.assertEqual(tag_music.norm("Bad Bunny (feat. Chencho)"), "bad bunny")
        self.assertEqual(tag_music.norm("Song [feat. X]"), "song")

    def test_collapses_punctuation_and_spaces(self):
        self.assertEqual(tag_music.norm("  A.B   C! "), "a b c")

    def test_empty(self):
        self.assertEqual(tag_music.norm(""), "")
        self.assertEqual(tag_music.norm(None), "")


class TestTagMusicParseFilename(unittest.TestCase):
    def test_artist_title_split(self):
        self.assertEqual(tag_music.parse_filename("Soda Stereo - De Musica Ligera"),
                         ("Soda Stereo", "De Musica Ligera"))

    def test_unicode_dashes(self):
        self.assertEqual(tag_music.parse_filename("Artist – Title"),
                         ("Artist", "Title"))

    def test_no_separator(self):
        self.assertEqual(tag_music.parse_filename("solo_titulo"), ("", "solo_titulo"))


class TestTagMusicReconcileLedger(unittest.TestCase):
    def test_marks_completed_and_tagged(self):
        ledger = {"Soda Stereo — De Música Ligera": {
            "artist": "Soda Stereo", "track": "De Música Ligera", "status": "requested"}}
        changed = tag_music.reconcile_ledger(
            ledger, {}, "soda stereo", "de musica ligera", Path("/x/y.mp3"))
        e = ledger["Soda Stereo — De Música Ligera"]
        self.assertTrue(changed)
        self.assertEqual(e["status"], "completed")
        self.assertTrue(e["tagged"])
        self.assertEqual(e["file_path"], "/x/y.mp3")

    def test_no_match_no_change(self):
        ledger = {"A — B": {"artist": "A", "track": "B", "status": "requested"}}
        changed = tag_music.reconcile_ledger(ledger, {}, "C", "D", Path("/z.mp3"))
        self.assertFalse(changed)
        self.assertEqual(ledger["A — B"]["status"], "requested")


class TestYoutubeCleanTitle(unittest.TestCase):
    def test_strips_official_video(self):
        self.assertEqual(
            youtube_dl.clean_title("Soda Stereo - De Música Ligera (Official Video)",
                                   "Soda Stereo"),
            ("Soda Stereo", "De Música Ligera"))

    def test_topic_channel_as_artist(self):
        self.assertEqual(
            youtube_dl.clean_title("Tití Me Preguntó", "Bad Bunny - Topic"),
            ("Bad Bunny", "Tití Me Preguntó"))

    def test_vevo_channel(self):
        artist, track = youtube_dl.clean_title("PROVENZA (Official Video)", "KAROLGVEVO")
        self.assertEqual(track, "PROVENZA")


class TestYoutubeSafeName(unittest.TestCase):
    def test_sanitizes(self):
        self.assertEqual(youtube_dl.safe_name("AC/DC: Back?"), "AC_DC_ Back")

    def test_truncates(self):
        self.assertLessEqual(len(youtube_dl.safe_name("x" * 200, max_len=20)), 20)

    def test_fallback_when_empty(self):
        self.assertEqual(youtube_dl.safe_name("///"), "audio")


if __name__ == "__main__":
    unittest.main(verbosity=2)
