from dataclasses import replace
from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, PngImagePlugin

from utils.creator import Caption, CreatorDraft
from utils.rendering import (RenderingError, export_jpg, export_png, layout_caption,
                             load_font, render_draft, wrap_text)


def draft_with(*captions, size=(400, 300), metadata=False):
    buffer = BytesIO()
    info = PngImagePlugin.PngInfo()
    if metadata:
        info.add_text("private", "PRIVATE SENTINEL")
    exif = Image.Exif()
    if metadata:
        exif[315] = "PRIVATE AUTHOR"
    Image.new("RGB", size, "#808080").save(buffer, format="PNG", pnginfo=info, exif=exif)
    return CreatorDraft(buffer.getvalue(), captions=tuple(captions),
                        next_caption_id=max((c.id for c in captions), default=0) + 1)


def decoded(data):
    with Image.open(BytesIO(data)) as image:
        image.load()
        return image.copy()


def changed_box(image):
    return ImageChops.difference(image, Image.new("RGB", image.size, "#808080")).getbbox()


def pixel_colors(image):
    return {color for count, color in image.getcolors(image.width * image.height)}


class RenderingTests(unittest.TestCase):
    def test_no_caption_preserves_pixels(self):
        draft = draft_with()
        result = render_draft(draft)
        self.assertEqual(decoded(result.png).tobytes(), decoded(draft.base_png).tobytes())
        self.assertEqual(result.overflow_caption_ids, ())

    def test_empty_caption_does_not_require_font(self):
        with patch("utils.rendering.load_font", side_effect=AssertionError("unused")):
            image = decoded(export_png(draft_with(Caption(1, text=" \n\t"))))
        self.assertIsNone(changed_box(image))

    def test_multiple_captions_in_separate_regions(self):
        draft = draft_with(Caption(1, text="FIRST", x=0.1, y=0.1, width=0.4),
                           Caption(2, text="SECOND", x=0.5, y=0.6, width=0.5))
        image = decoded(export_png(draft))
        self.assertIsNotNone(changed_box(image.crop((0, 0, 400, 150))))
        self.assertIsNotNone(changed_box(image.crop((0, 150, 400, 300))))

    def test_positions_translate_ink(self):
        caption = Caption(1, text="Test", x=0, y=0, width=0.5, alignment="left")
        first = changed_box(decoded(export_png(draft_with(caption))))
        second = changed_box(decoded(export_png(draft_with(replace(caption, x=0.25, y=0.2)))))
        self.assertEqual(tuple(b-a for a, b in zip(first, second)), (100, 60, 100, 60))

    def test_fractional_coordinates_floor_to_pixels(self):
        layout = layout_caption(Caption(1, text="A", x=0.123, y=0.321, width=0.555), (101, 99))
        self.assertEqual(layout.clip_box, (12, 31, 68, 99))

    def test_wrapping_fits_measured_box(self):
        caption = Caption(1, text="one two three four five", width=0.25, font_size=24)
        layout = layout_caption(caption, (400, 300))
        self.assertGreater(len(layout.lines), 1)
        self.assertTrue(all(line.width <= 100 for line in layout.lines))
        self.assertEqual(" ".join(line.text for line in layout.lines), caption.text)

    def test_explicit_newlines_and_blank_lines(self):
        font = load_font(24)
        self.assertEqual(wrap_text("first\r\n\r\nlast\n", font, 400), ("first", "", "last", ""))
        layout = layout_caption(Caption(1, text="A\n\nB"), (400, 300))
        self.assertEqual(layout.lines[2].y - layout.lines[0].y,
                         2 * (layout.lines[1].y - layout.lines[0].y))

    def test_horizontal_whitespace_collapses(self):
        self.assertEqual(wrap_text("  first\t  second  ", load_font(24), 400), ("first second",))

    def test_alignment_changes_pixels_and_measured_placement(self):
        positions = []
        for alignment in ("left", "center", "right"):
            caption = Caption(1, text="Test", x=0, y=0, width=1, alignment=alignment)
            line = layout_caption(caption, (400, 300)).lines[0]
            box = changed_box(decoded(export_png(draft_with(caption))))
            self.assertLessEqual(abs(box[0] - line.x), 1)
            positions.append(box[0])
            if alignment == "right":
                self.assertLessEqual(abs(box[2] - 400), 1)
        self.assertLess(positions[0], positions[1])
        self.assertLess(positions[1], positions[2])

    def test_outline_and_fill_colors_are_rendered(self):
        caption = Caption(1, text="TEST", fill_color="#FF0000", outline_color="#0000FF", outline_width=4)
        image = decoded(export_png(draft_with(caption)))
        colors = pixel_colors(image)
        self.assertIn((255, 0, 0), colors)
        self.assertIn((0, 0, 255), colors)
        plain = decoded(export_png(draft_with(replace(caption, outline_width=0))))
        self.assertNotIn((0, 0, 255), pixel_colors(plain))

    def test_outline_included_in_wrapping_and_bounds(self):
        caption = Caption(1, text="WW WW WW", width=0.3, outline_width=12)
        layout = layout_caption(caption, (400, 300))
        self.assertTrue(all(line.width <= 120 for line in layout.lines))
        self.assertGreater(len(layout.lines), 1)

    def test_long_word_splits_without_losing_characters(self):
        text = "abcdefghij" * 20
        lines = wrap_text(text, load_font(24), 60, 2)
        self.assertEqual("".join(lines), text)
        self.assertGreater(len(lines), 10)
        self.assertTrue(all(line for line in lines))

    def test_tiny_box_oversized_glyph_progresses_and_clips(self):
        caption = Caption(1, text="WWW", width=0.001, x=0, y=0, alignment="left")
        layout = layout_caption(caption, (400, 300))
        self.assertEqual([line.text for line in layout.lines], ["W", "W", "W"])
        result = render_draft(draft_with(caption))
        self.assertEqual(result.overflow_caption_ids, (1,))
        image = decoded(result.png)
        self.assertIsNone(changed_box(image.crop((1, 0, 400, 300))))

    def test_bottom_overflow_is_reported_and_canvas_not_expanded(self):
        caption = Caption(1, text="A\nB\nC", y=0.95)
        result = render_draft(draft_with(caption))
        self.assertEqual(result.overflow_caption_ids, (1,))
        self.assertEqual(decoded(result.png).size, (400, 300))
        self.assertIsNone(changed_box(decoded(result.png).crop((0, 0, 400, 285))))

    def test_right_edge_overflow_and_exact_boundary(self):
        for x, y in ((1, 0), (0, 1)):
            result = render_draft(draft_with(Caption(1, text="TEST", x=x, y=y)))
            self.assertEqual(result.overflow_caption_ids, (1,))
            self.assertIsNone(changed_box(decoded(result.png)))
        result = render_draft(draft_with(Caption(1, text="TEST", x=0.95, width=0.5)))
        self.assertEqual(result.overflow_caption_ids, (1,))

    def test_overlap_uses_caption_order(self):
        red = Caption(1, text="TEST", fill_color="#FF0000", outline_width=0)
        blue = replace(red, id=2, fill_color="#0000FF")
        top_blue = decoded(export_png(draft_with(red, blue)))
        top_red = decoded(export_png(draft_with(blue, red)))
        self.assertIn((0, 0, 255), pixel_colors(top_blue))
        self.assertNotIn((255, 0, 0), pixel_colors(top_blue))
        self.assertIn((255, 0, 0), pixel_colors(top_red))

    def test_font_size_changes_ink_dimensions(self):
        boxes = [changed_box(decoded(export_png(draft_with(Caption(1, text="TEST", font_size=size)))))
                 for size in (20, 60)]
        self.assertGreater(boxes[1][2] - boxes[1][0], boxes[0][2] - boxes[0][0])
        self.assertGreater(boxes[1][3] - boxes[1][1], boxes[0][3] - boxes[0][1])

    def test_png_decodes_with_expected_dimensions_and_mode(self):
        for size in ((1, 1), (200, 1200), (1200, 200)):
            result = render_draft(draft_with(Caption(1, text="Test"), size=size))
            self.assertTrue(result.png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual((result.width, result.height), size)
            image = decoded(result.png)
            self.assertEqual(image.size, size)
            self.assertEqual(image.mode, "RGB")

    def test_metadata_is_removed_even_from_direct_draft(self):
        draft = draft_with(Caption(1, text="Public caption"), metadata=True)
        self.assertIn(b"PRIVATE", draft.base_png)
        for export in (export_png, export_jpg):
            data = export(draft)
            self.assertNotIn(b"PRIVATE", data)
            image = decoded(data)
            self.assertFalse(image.getexif())
            self.assertNotIn("private", image.info)
            self.assertNotIn("icc_profile", image.info)
            self.assertNotIn("exif", image.info)

    def test_export_matches_preview_and_does_not_mutate_source(self):
        draft = draft_with(Caption(1, text="Hello"))
        original = draft.base_png
        first = render_draft(draft)
        self.assertEqual(export_png(draft), first.png)
        self.assertEqual(render_draft(draft), first)
        self.assertEqual(draft.base_png, original)
        self.assertIsNone(changed_box(decoded(original)))

    def test_jpg_decodes_and_approximates_png(self):
        draft = draft_with(Caption(1, text="JPG"))
        jpg = export_jpg(draft)
        self.assertTrue(jpg.startswith(b"\xff\xd8"))
        image = decoded(jpg)
        self.assertEqual(image.size, (400, 300))
        self.assertEqual(image.mode, "RGB")
        difference = ImageChops.difference(image, decoded(export_png(draft)))
        self.assertLess(sum(difference.tobytes()) / (400 * 300 * 3), 5)

    def test_unavailable_font_and_decode_failures_are_safe(self):
        draft = draft_with(Caption(1, text="Test"))
        with patch("utils.rendering.ImageFont.load_default", side_effect=OSError("PRIVATE")):
            with self.assertRaises(RenderingError) as error:
                render_draft(draft)
            self.assertNotIn("PRIVATE", str(error.exception))
        with patch("utils.rendering.Image.open", side_effect=OSError("PRIVATE")):
            with self.assertRaises(RenderingError) as error:
                render_draft(draft)
            self.assertNotIn("PRIVATE", str(error.exception))

    def test_invalid_draft_fails_safely(self):
        with self.assertRaises(RenderingError):
            render_draft(None)

    def test_scalable_font_available(self):
        self.assertEqual(load_font(24).getname(), ("Aileron", "Regular"))


if __name__ == "__main__":
    unittest.main()
