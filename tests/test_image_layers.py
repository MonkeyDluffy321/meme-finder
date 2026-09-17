"""Local model and pixel-level regressions for generic image layers."""

from dataclasses import FrozenInstanceError, replace
from io import BytesIO
import unittest

from PIL import Image, ImageChops, PngImagePlugin

from utils.creator import CreatorDraft, CreatorError, ImageLayer, MAX_IMAGE_LAYERS
from utils.rendering import render_draft, export_png


def picture(color="blue", size=(100, 100), metadata=False):
    image = Image.new("RGB", size, color)
    info = PngImagePlugin.PngInfo()
    exif = Image.Exif()
    if metadata:
        info.add_text("private", "PRIVATE SOURCE")
        exif[315] = "PRIVATE AUTHOR"
    buffer = BytesIO()
    image.save(buffer, format="PNG", pnginfo=info, exif=exif)
    return buffer.getvalue()


def pixels(draft):
    with Image.open(BytesIO(export_png(draft))) as image:
        return image.copy()


class ImageLayerModelTests(unittest.TestCase):
    def setUp(self):
        self.draft = CreatorDraft.from_bytes(picture("gray", (200, 200)))

    def test_default_add_update_remove_and_immutability(self):
        self.assertEqual(self.draft.image_layers, ())
        added = self.draft.add_image_layer(picture(), source_label="Image A")
        updated = added.update_image_layer(1, x=-0.5, width=0.4, height=0.2, rotation=45, opacity=50, fit="cover")
        self.assertEqual(added.image_layers[0].x, 0.1)
        self.assertEqual(updated.image_layers[0].x, -0.5)
        self.assertEqual(updated.revision, 2)
        self.assertEqual(updated.remove_image_layer(1).image_layers, ())
        self.assertEqual(self.draft.image_layers, ())
        with self.assertRaises(FrozenInstanceError):
            updated.image_layers[0].opacity = 0

    def test_stable_ids_independent_of_caption_ids_and_positions(self):
        draft = self.draft.add_image_layer(picture()).add_image_layer(picture("red"))
        draft = draft.remove_image_layer(1).add_image_layer(picture("green"))
        self.assertEqual([layer.id for layer in draft.image_layers], [2, 3])
        self.assertEqual(draft.next_image_id, 4)
        self.assertEqual(draft.captions[0].id, 1)

    def test_limit(self):
        draft = self.draft
        for _ in range(MAX_IMAGE_LAYERS):
            draft = draft.add_image_layer(picture())
        with self.assertRaises(CreatorError):
            draft.add_image_layer(picture())
        self.assertEqual(len(draft.remove_image_layer(1).add_image_layer(picture()).image_layers), 8)

    def test_invalid_ranges(self):
        cases = {"x": [-1.1, 1.1, True, float("nan")], "y": [float("inf"), "0"],
                 "width": [0, -1, 1.1, None], "height": [0, 2, False],
                 "rotation": [-181, 181, float("nan"), True],
                 "opacity": [-1, 101, 1.5, True], "fit": ["stretch", None, []],
                 "source_label": ["", "a/b", "C:\\secret.png", "bad\nlabel", "x" * 201]}
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(CreatorError):
                    self.draft.add_image_layer(picture(), **{field: value})

    def test_replacement_preserves_id_order_and_placement(self):
        draft = self.draft.add_image_layer(picture(), x=-0.2, opacity=30, rotation=20)
        draft = draft.add_image_layer(picture("green"))
        updated = draft.replace_image_layer(1, picture("red"), source_label="Replacement")
        old, new = draft.image_layers[0], updated.image_layers[0]
        self.assertNotEqual(old.digest, new.digest)
        self.assertEqual((new.id, new.x, new.opacity, new.rotation), (1, -0.2, 30, 20))
        self.assertEqual(updated.image_layers[1], draft.image_layers[1])
        self.assertEqual(updated.next_image_id, draft.next_image_id)
        self.assertEqual(updated.revision, draft.revision + 1)

    def test_bad_ids_unknown_settings_and_invalid_draft(self):
        draft = self.draft.add_image_layer(picture())
        for value in (0, True, "1", 99):
            with self.assertRaises(CreatorError):
                draft.update_image_layer(value, x=0.2)
            with self.assertRaises(CreatorError):
                draft.remove_image_layer(value)
            with self.assertRaises(CreatorError):
                draft.replace_image_layer(value, picture())
        for field in ("id", "image_png", "digest", "path"):
            with self.assertRaises(CreatorError):
                draft.update_image_layer(1, **{field: "invalid"})
        for settings in ({"image_layers": []}, {"image_layers": ("bad",)},
                         {"image_layers": draft.image_layers * 2}, {"next_image_id": 1}):
            with self.assertRaises(CreatorError):
                replace(draft, **settings)

    def test_normalizes_metadata_and_does_not_expose_bytes(self):
        raw = picture(metadata=True)
        layer = ImageLayer(1, raw)
        self.assertNotIn(b"PRIVATE", layer.image_png)
        with Image.open(BytesIO(layer.image_png)) as image:
            self.assertFalse(image.info)
            self.assertFalse(image.getexif())
        self.assertNotIn(repr(layer.image_png), repr(layer))
        with self.assertRaises(CreatorError):
            ImageLayer(1, b"bad")

    def test_normalizes_orientation_size_and_source_transparency(self):
        exif = Image.Exif()
        exif[274] = 6
        buffer = BytesIO()
        Image.new("RGB", (2000, 1000), "red").save(buffer, format="JPEG", exif=exif)
        layer = ImageLayer(1, buffer.getvalue())
        with Image.open(BytesIO(layer.image_png)) as image:
            self.assertEqual(image.size, (800, 1600))
            self.assertFalse(image.getexif())
        buffer = BytesIO()
        Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(buffer, format="PNG")
        layer = ImageLayer(1, buffer.getvalue())
        with Image.open(BytesIO(layer.image_png)) as image:
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))


class ImageLayerRenderingTests(unittest.TestCase):
    def setUp(self):
        self.draft = CreatorDraft.from_bytes(picture("gray", (200, 200)))

    def test_single_layer_position_dimensions_and_png(self):
        draft = self.draft.add_image_layer(picture(), x=0.25, y=0.25, width=0.5, height=0.5)
        image = pixels(draft)
        self.assertEqual(image.size, (200, 200))
        self.assertEqual(image.getpixel((50, 50)), (0, 0, 255))
        self.assertEqual(image.getpixel((149, 149)), (0, 0, 255))
        self.assertEqual(image.getpixel((150, 150)), (128, 128, 128))
        self.assertEqual(export_png(draft), render_draft(draft).png)

    def test_multiple_images_draw_in_list_order(self):
        draft = self.draft.add_image_layer(picture("red"), width=0.8, height=0.8)
        draft = draft.add_image_layer(picture("blue"), x=0.3, y=0.3)
        self.assertEqual(pixels(draft).getpixel((80, 80)), (0, 0, 255))
        reversed_draft = replace(draft, image_layers=tuple(reversed(draft.image_layers)))
        self.assertEqual(pixels(reversed_draft).getpixel((80, 80)), (255, 0, 0))

    def test_contain_preserves_ratio_and_leaves_transparent_padding(self):
        draft = self.draft.add_image_layer(picture(size=(100, 50)), x=0, y=0, width=0.5, height=0.5)
        image = pixels(draft)
        self.assertEqual(image.getpixel((50, 10)), (128, 128, 128))
        self.assertEqual(image.getpixel((50, 25)), (0, 0, 255))
        self.assertEqual(image.getpixel((50, 74)), (0, 0, 255))
        self.assertEqual(image.getpixel((50, 75)), (128, 128, 128))

    def test_cover_center_crops(self):
        source = Image.new("RGB", (100, 50), "red")
        source.paste("blue", (25, 0, 75, 50))
        buffer = BytesIO()
        source.save(buffer, format="PNG")
        draft = self.draft.add_image_layer(buffer.getvalue(), x=0, y=0, width=0.5, height=0.5, fit="cover")
        image = pixels(draft)
        self.assertEqual(image.getpixel((50, 5)), (0, 0, 255))
        self.assertEqual(image.getpixel((10, 50)), (0, 0, 255))

    def test_rotation_about_box_center(self):
        draft = self.draft.add_image_layer(picture(size=(100, 50)), x=0.25, y=0.25,
                                           width=0.5, height=0.25, rotation=90)
        image = pixels(draft)
        difference = ImageChops.difference(image, Image.new("RGB", image.size, "gray"))
        self.assertEqual(difference.getbbox(), (75, 25, 125, 125))
        rotated = pixels(draft.update_image_layer(1, rotation=45))
        self.assertNotEqual(rotated.tobytes(), image.tobytes())

    def test_opacity_zero_half_and_full(self):
        draft = self.draft.add_image_layer(picture("white"), x=0, y=0, width=1, height=1)
        self.assertEqual(pixels(draft).getpixel((50, 50)), (255, 255, 255))
        half = pixels(draft.update_image_layer(1, opacity=50)).getpixel((50, 50))
        self.assertTrue(all(191 <= channel <= 192 for channel in half))
        self.assertEqual(pixels(draft.update_image_layer(1, opacity=0)).getpixel((50, 50)), (128, 128, 128))

    def test_negative_and_far_edge_clipping(self):
        draft = self.draft.add_image_layer(picture(), x=-0.25, y=-0.25, width=0.5, height=0.5)
        image = pixels(draft)
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 255))
        self.assertEqual(image.getpixel((50, 50)), (128, 128, 128))
        for position in (-1, 1):
            outside = pixels(draft.update_image_layer(1, x=position, y=position))
            self.assertIsNone(ImageChops.difference(outside, Image.new("RGB", outside.size, "gray")).getbbox())
        corner = pixels(draft.update_image_layer(1, x=0.9, y=0.9, rotation=45))
        self.assertEqual(corner.size, (200, 200))

    def test_captions_draw_above_images_and_overflow_still_reports(self):
        draft = self.draft.add_image_layer(picture("blue"), x=0, y=0, width=1, height=1)
        draft = draft.update_caption(1, text="TOP", fill_color="#FF0000", outline_width=0)
        image = pixels(draft)
        self.assertIn((255, 0, 0), {color for _, color in image.getcolors(40000)})
        self.assertEqual(render_draft(draft.update_caption(1, y=1)).overflow_caption_ids, (1,))

    def test_metadata_does_not_reach_export_and_source_is_unchanged(self):
        draft = self.draft.add_image_layer(picture(metadata=True))
        source = draft.image_layers[0].image_png
        result = render_draft(draft)
        self.assertNotIn(b"PRIVATE", result.png)
        self.assertFalse(pixels(draft).getexif())
        self.assertEqual(draft.image_layers[0].image_png, source)

    def test_extreme_aspect_ratio_and_one_pixel_target(self):
        for fit in ("contain", "cover"):
            draft = self.draft.add_image_layer(picture(size=(1600, 1)), width=0.001, height=1, fit=fit)
            self.assertEqual(pixels(draft).size, (200, 200))


if __name__ == "__main__":
    unittest.main()
