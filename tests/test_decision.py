import unittest

from mipet_car.config import DriveConfig
from mipet_car.decision import DriveState, calculate_motor_speed, decide


class DummyLine:
    def __init__(self, found=True, offset=0.0, frame_width=640):
        self.found = found
        self.offset = offset
        self.frame_width = frame_width


class DummySign:
    def __init__(self, detected=False, method="none"):
        self.detected = detected
        self.method = method


class DummyFood:
    def __init__(self, detected=False, label="banana", score=0.8):
        self.detected = detected
        self.label = label
        self.score = score


class DecisionTests(unittest.TestCase):
    def test_center_line_goes_straight(self):
        command = calculate_motor_speed(0, 640, DriveConfig(base_speed=0.4, max_speed=0.8))
        self.assertEqual(command.state, DriveState.FOLLOW_LINE)
        self.assertAlmostEqual(command.left_speed, command.right_speed)

    def test_left_offset_slows_left_wheel(self):
        command = calculate_motor_speed(-160, 640, DriveConfig(base_speed=0.4, max_speed=0.8, kp=0.5))
        self.assertEqual(command.state, DriveState.TURN_LEFT)
        self.assertLess(command.left_speed, command.right_speed)

    def test_right_offset_slows_right_wheel(self):
        command = calculate_motor_speed(160, 640, DriveConfig(base_speed=0.4, max_speed=0.8, kp=0.5))
        self.assertEqual(command.state, DriveState.TURN_RIGHT)
        self.assertGreater(command.left_speed, command.right_speed)

    def test_sign_has_priority(self):
        command = decide(DummyLine(found=True, offset=0), DummySign(detected=True, method="aruco"))
        self.assertEqual(command.state, DriveState.STOP_SIGN_DETECTED)
        self.assertEqual(command.left_speed, 0.0)
        self.assertEqual(command.right_speed, 0.0)

    def test_food_has_priority_over_line_and_sign(self):
        command = decide(
            DummyLine(found=True, offset=0),
            DummySign(detected=True, method="aruco"),
            DummyFood(detected=True, label="banana", score=0.9),
        )
        self.assertEqual(command.state, DriveState.FOOD_DETECTED)
        self.assertEqual(command.left_speed, 0.0)
        self.assertEqual(command.right_speed, 0.0)

    def test_line_lost_stops(self):
        command = decide(DummyLine(found=False), DummySign(detected=False))
        self.assertEqual(command.state, DriveState.LINE_LOST)
        self.assertEqual(command.left_speed, 0.0)
        self.assertEqual(command.right_speed, 0.0)

    def test_old_decide_signature_still_accepts_drive_config(self):
        command = decide(
            DummyLine(found=True, offset=160),
            DummySign(detected=False),
            DriveConfig(base_speed=0.4, max_speed=0.8, kp=0.5),
        )
        self.assertEqual(command.state, DriveState.TURN_RIGHT)


if __name__ == "__main__":
    unittest.main()
