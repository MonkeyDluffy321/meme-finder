from dataclasses import FrozenInstanceError, replace
from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image

from utils.creator import Caption, CreatorDraft, CreatorError, MAX_CAPTIONS, MAX_TEXT_LENGTH


def image_bytes(size=(320, 240), mode="RGB", fmt="PNG", **options):
    buffer = BytesIO()
    Image.new(mode, size, "white").save(buffer, format=fmt, **options)
    return buffer.getvalue()


class CreatorTests(unittest.TestCase):
    def setUp(self):
        self.draft = CreatorDraft.from_bytes(image_bytes())

    def test_default_draft(self):
        draft = self.draft
        self.assertEqual((draft.width, draft.height), (320, 240))
        self.assertEqual(draft.source_kind, "upload")
        self.assertIsNone(draft.template_id)
        self.assertEqual(draft.captions, (Caption(1),))
        self.assertEqual(draft.next_caption_id, 2)
        self.assertEqual(draft.revision, 0)
        self.assertEqual(len(draft.digest), 64)

    def test_template_metadata(self):
        draft = CreatorDraft.from_bytes(image_bytes(), source_kind="template",
                                        source_label="Two Buttons", template_id="two-buttons")
        self.assertEqual(draft.template_id, "two-buttons")
        self.assertEqual(draft.source_label, "Two Buttons")

    def test_add_and_remove_are_immutable(self):
        added = self.draft.add_caption(text="second", x=0.2)
        self.assertEqual(len(self.draft.captions), 1)
        self.assertEqual(added.captions[1].text, "second")
        removed = added.remove_caption(1)
        self.assertEqual([c.id for c in removed.captions], [2])
        self.assertEqual(len(added.captions), 2)
        self.assertEqual(removed.revision, 2)

    def test_removed_ids_are_never_reused(self):
        draft = self.draft.add_caption().remove_caption(2).add_caption()
        self.assertEqual([c.id for c in draft.captions], [1, 3])
        self.assertEqual(draft.next_caption_id, 4)

    def test_remove_all_then_add(self):
        draft = self.draft.remove_caption(1)
        self.assertEqual(draft.captions, ())
        self.assertEqual(draft.add_caption().captions[0].id, 2)

    def test_update_preserves_id_order_and_source(self):
        draft = self.draft.add_caption(text="second")
        updated = draft.update_caption(1, text="changed", alignment="right", fill_color="#12ab34")
        self.assertEqual([c.id for c in updated.captions], [1, 2])
        self.assertEqual(updated.captions[0].text, "changed")
        self.assertEqual(draft.captions[0].text, "")
        self.assertEqual(updated.digest, draft.digest)
        self.assertEqual(updated.base_png, draft.base_png)
        self.assertEqual(updated.revision, draft.revision + 1)

    def test_frozen_models(self):
        with self.assertRaises(FrozenInstanceError):
            self.draft.revision = 2
        with self.assertRaises(FrozenInstanceError):
            self.draft.captions[0].text = "mutated"

    def test_caption_count_limit(self):
        draft = self.draft
        for _ in range(MAX_CAPTIONS - 1):
            draft = draft.add_caption()
        with self.assertRaises(CreatorError):
            draft.add_caption()
        self.assertEqual(len(draft.remove_caption(1).add_caption().captions), MAX_CAPTIONS)
        with self.assertRaises(CreatorError):
            replace(draft, captions=tuple(Caption(i) for i in range(1, MAX_CAPTIONS + 2)),
                    next_caption_id=MAX_CAPTIONS + 2)

    def test_text_limit(self):
        self.assertEqual(len(Caption(1, text="a" * MAX_TEXT_LENGTH).text), MAX_TEXT_LENGTH)
        with self.assertRaises(CreatorError):
            Caption(1, text="a" * (MAX_TEXT_LENGTH + 1))

    def test_invalid_settings(self):
        cases = {"x": [-0.1, 1.1, float("nan"), float("inf"), True, "0"],
                 "y": [-1, 2, None], "width": [0, -1, 1.1],
                 "font_size": [0, 7, 201, 12.5, True, "40"],
                 "outline_width": [-1, 13, 1.5, False],
                 "alignment": ["justify", None, []],
                 "fill_color": ["white", "#fff", "#GG0000", None],
                 "outline_color": ["#00000000", "red"],
                 "text": [None, 2, "bad\x00text", "\ud800", "bad\x7f"]}
        for name, values in cases.items():
            for value in values:
                with self.subTest(name=name, value=repr(value)), self.assertRaises(CreatorError):
                    Caption(1, **{name: value})

    def test_boundary_settings_and_line_breaks(self):
        caption = Caption(1, text="a\r\nb\t漢字", x=1, y=0, width=1,
                          font_size=200, outline_width=12)
        self.assertEqual(caption.x, 1)

    def test_invalid_ids_and_missing_caption(self):
        for value in (0, -1, True, "1", None):
            with self.subTest(value=value), self.assertRaises(CreatorError):
                Caption(value)
        for value in (99, True, "1"):
            for operation in (self.draft.remove_caption, self.draft.update_caption):
                with self.assertRaises(CreatorError):
                    operation(value)
        with self.assertRaises(CreatorError):
            replace(self.draft, captions=(Caption(1), Caption(1)))
        for value in (1, 0, True):
            with self.assertRaises(CreatorError):
                replace(self.draft, next_caption_id=value)

    def test_unknown_settings_and_id_changes_fail_safely(self):
        for settings in ({"id": 99}, {"font_path": "private/path"}):
            with self.assertRaises(CreatorError):
                self.draft.add_caption(**settings)
            with self.assertRaises(CreatorError):
                self.draft.update_caption(1, **settings)

    def test_invalid_draft_settings(self):
        for settings in ({"source_kind": "url"}, {"source_label": ""},
                         {"source_label": "a\nb"}, {"source_label": "x" * 201},
                         {"template_id": "unexpected"}, {"source_kind": "template"},
                         {"source_kind": "template", "template_id": "../bad"},
                         {"captions": [Caption(1)]}, {"captions": ("bad",)},
                         {"revision": -1}, {"revision": True}):
            with self.subTest(settings=settings), self.assertRaises(CreatorError):
                replace(self.draft, **settings)

    def test_factory_normalizes_orientation_and_dimensions(self):
        exif = Image.Exif()
        exif[274] = 6
        draft = CreatorDraft.from_bytes(image_bytes((2000, 1000), fmt="JPEG", exif=exif))
        self.assertEqual((draft.width, draft.height), (800, 1600))
        with Image.open(BytesIO(draft.base_png)) as image:
            self.assertEqual(image.mode, "RGB")
            self.assertFalse(image.getexif())

    def test_sources_reject_corrupt_unsupported_or_unnormalized_images(self):
        for data in (b"", b"not an image", image_bytes(fmt="GIF")):
            with self.assertRaises(CreatorError):
                CreatorDraft.from_bytes(data)
        for data in (b"bad", image_bytes(fmt="JPEG"), image_bytes(mode="RGBA"),
                     image_bytes((1601, 1))):
            with self.assertRaises(CreatorError):
                CreatorDraft(data)

    def test_private_content_not_in_representations(self):
        draft = replace(self.draft, source_label="PRIVATE FILE NAME").update_caption(1, text="PRIVATE CAPTION")
        self.assertNotIn("PRIVATE", repr(draft))
        self.assertNotIn(repr(draft.base_png), repr(draft))

    def test_decompression_bomb_warning_becomes_safe_error(self):
        with patch("utils.creator.Image.MAX_IMAGE_PIXELS", 50000):
            with self.assertRaises(CreatorError) as error:
                CreatorDraft(self.draft.base_png)
        self.assertEqual(str(error.exception), "The draft image could not be decoded safely.")


if __name__ == "__main__":
    unittest.main()
