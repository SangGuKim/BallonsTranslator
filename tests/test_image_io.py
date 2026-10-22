import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ballontranslator.utils.io_utils import imread, imwrite


class ImageIOTest(unittest.TestCase):
    def test_webp_exif_orientation_is_applied_to_pixels(self):
        source = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
        transforms = {
            1: source,
            2: source[:, ::-1],
            3: source[::-1, ::-1],
            4: source[::-1],
            5: source.transpose(1, 0, 2),
            6: np.rot90(source, -1),
            7: source.transpose(1, 0, 2)[::-1, ::-1],
            8: np.rot90(source, 1),
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.webp'
            for orientation, expected in transforms.items():
                with self.subTest(orientation=orientation):
                    exif = Image.Exif()
                    exif[274] = orientation
                    Image.fromarray(source).save(path, lossless=True, exif=exif)
                    original_bytes = path.read_bytes()
                    loaded = imread(path)
                    np.testing.assert_array_equal(loaded, expected)
                    gray = imread(path, cv2.IMREAD_GRAYSCALE)
                    np.testing.assert_array_equal(
                        gray, np.array(Image.fromarray(expected).convert('L')),
                    )
                    self.assertEqual(path.read_bytes(), original_bytes)

    def test_rotated_webp_outputs_store_oriented_pixels_without_exif(self):
        source = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.webp'
            exif = Image.Exif()
            exif[274] = 8
            Image.fromarray(source).save(path, lossless=True, exif=exif)
            loaded = imread(path)
            mask = loaded[:, :, 0]
            for name, pixels in (('inpainted', loaded), ('mask', mask)):
                output = Path(directory) / (name + '.png')
                imwrite(str(output), pixels)
                with Image.open(output) as image:
                    self.assertEqual(image.size, (2, 4))
                    self.assertNotIn(274, image.getexif())
                    np.testing.assert_array_equal(np.array(image), pixels)

    def test_project_uses_rotated_dimensions_and_reloads_derived_pixels(self):
        from unittest.mock import patch
        from ballontranslator.utils.config import pcfg
        from ballontranslator.utils.proj_imgtrans import ProjImgTrans

        source = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
        expected = np.rot90(source)
        with tempfile.TemporaryDirectory() as directory, patch.object(
            pcfg, 'intermediate_imgsave_ext', '.png',
        ):
            path = Path(directory) / 'page.webp'
            exif = Image.Exif()
            exif[274] = 8
            Image.fromarray(source).save(path, lossless=True, exif=exif)
            project = ProjImgTrans(directory)
            project.set_current_img('page.webp')
            np.testing.assert_array_equal(project.img_array, expected)
            self.assertEqual(project.mask_array.shape, (4, 2))
            np.testing.assert_array_equal(project.read_img('page.webp'), expected)
            self.assertEqual(project._image_info['page.webp']['width'], 2)
            self.assertEqual(project._image_info['page.webp']['height'], 4)
            mask = expected[:, :, 0].copy()
            project.save_mask('page.webp', mask)
            project.save_inpainted('page.webp', expected)
            project.set_current_img(None)
            np.testing.assert_array_equal(
                project.load_inpainted_by_imgname('page.webp'), expected,
            )
            reloaded = ProjImgTrans(directory)
            reloaded.set_current_img('page.webp')
            np.testing.assert_array_equal(reloaded.mask_array, mask)
            np.testing.assert_array_equal(reloaded.inpainted_array, expected)

    def test_imread_normalizes_16_bit_grayscale_png_to_uint8_rgb(self):
        source = np.array(
            [[0, 256], [32768, 65535]],
            dtype=np.uint16,
        )
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / 'gray16.png'
            Image.fromarray(source).save(image_path)

            loaded = imread(str(image_path))

        self.assertEqual(loaded.dtype, np.uint8)
        self.assertEqual(loaded.shape, (2, 2, 3))
        np.testing.assert_array_equal(
            loaded[:, :, 0],
            np.array([[0, 1], [128, 255]], dtype=np.uint8),
        )
        np.testing.assert_array_equal(loaded[:, :, 0], loaded[:, :, 1])
        np.testing.assert_array_equal(loaded[:, :, 1], loaded[:, :, 2])


if __name__ == '__main__':
    unittest.main()
