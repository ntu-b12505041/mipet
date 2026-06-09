import importlib.util
import unittest


CV2_AVAILABLE = importlib.util.find_spec("cv2") is not None
NUMPY_AVAILABLE = importlib.util.find_spec("numpy") is not None


@unittest.skipUnless(CV2_AVAILABLE and NUMPY_AVAILABLE, "OpenCV and numpy are optional in local tests")
class VisionTests(unittest.TestCase):
    def test_detects_black_line_offset(self):
        import cv2
        import numpy as np

        from mipet_car.config import LineDetectionConfig
        from mipet_car.vision_line import detect_line

        frame = np.full((240, 320, 3), 255, dtype=np.uint8)
        cv2.rectangle(frame, (60, 150), (100, 230), (0, 0, 0), -1)

        result = detect_line(frame, LineDetectionConfig(min_area=50))

        self.assertTrue(result.found)
        self.assertLess(result.offset, 0)

    def test_detects_thin_black_line_with_morphology(self):
        import cv2
        import numpy as np

        from mipet_car.config import LineDetectionConfig
        from mipet_car.vision_line import detect_line

        frame = np.full((240, 320, 3), 255, dtype=np.uint8)
        cv2.line(frame, (150, 0), (145, 239), (0, 0, 0), 5)

        result = detect_line(
            frame,
            LineDetectionConfig(min_area=100, morph_kernel_size=7),
        )

        self.assertTrue(result.found)
        self.assertLess(result.offset, 0)

    def test_detects_red_sign(self):
        import cv2
        import numpy as np

        from mipet_car.config import SignDetectionConfig
        from mipet_car.vision_sign import detect_stop_sign

        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.rectangle(frame, (120, 40), (200, 120), (0, 0, 255), -1)

        result = detect_stop_sign(frame, SignDetectionConfig(mode="red", red_area_min=100))

        self.assertTrue(result.detected)
        self.assertEqual(result.method, "red")


if __name__ == "__main__":
    unittest.main()
