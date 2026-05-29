import unittest

from mipet_car.motor import MotorDriver


class MotorDriverTests(unittest.TestCase):
    def test_forward_sets_both_channels_forward(self):
        with MotorDriver(dry_run=True) as motor:
            motor.forward(0.5)
            snapshot = motor.snapshot()

        self.assertEqual(snapshot.left_in1, 1.0)
        self.assertEqual(snapshot.left_in2, 0.0)
        self.assertEqual(snapshot.right_in1, 1.0)
        self.assertEqual(snapshot.right_in2, 0.0)
        self.assertAlmostEqual(snapshot.left_pwm, 0.5)
        self.assertAlmostEqual(snapshot.right_pwm, 0.5)

    def test_turn_left_slows_left_channel(self):
        with MotorDriver(dry_run=True) as motor:
            motor.turn_left(0.4)
            snapshot = motor.snapshot()

        self.assertEqual(snapshot.left_pwm, 0.0)
        self.assertAlmostEqual(snapshot.right_pwm, 0.4)


if __name__ == "__main__":
    unittest.main()

