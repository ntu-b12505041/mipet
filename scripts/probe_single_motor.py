"""Standalone one-motor TB6612 hardware probe.

This script intentionally does not import mipet_car.motor or config.py, so it
can verify the wiring even if the project configuration is wrong.
"""

import argparse
import sys
import time


PIN_TABLE = {
    "a": {
        "name": "A / left",
        "in1_gpio": 5,
        "in1_pin": 29,
        "in2_gpio": 6,
        "in2_pin": 31,
        "pwm_gpio": 12,
        "pwm_pin": 32,
        "out": "AO1 / AO2",
    },
    "b": {
        "name": "B / right",
        "in1_gpio": 20,
        "in1_pin": 38,
        "in2_gpio": 21,
        "in2_pin": 40,
        "pwm_gpio": 13,
        "pwm_pin": 33,
        "out": "BO1 / BO2",
    },
}
STBY_GPIO = 16
STBY_PIN = 36


def _print_wiring(channel: str) -> None:
    pins = PIN_TABLE[channel]
    print("=== Wiring expected by this probe ===")
    print("Pi pin 1  / 3.3V     -> TB6612 VCC")
    print("Pi GND              -> TB6612 GND")
    print("Battery +           -> TB6612 VM")
    print("Battery -           -> TB6612 GND")
    print(f"Pi pin {STBY_PIN:<2} / GPIO{STBY_GPIO:<2} -> TB6612 STBY")
    print(f"Pi pin {pins['in1_pin']:<2} / GPIO{pins['in1_gpio']:<2} -> TB6612 IN1")
    print(f"Pi pin {pins['in2_pin']:<2} / GPIO{pins['in2_gpio']:<2} -> TB6612 IN2")
    print(f"Pi pin {pins['pwm_pin']:<2} / GPIO{pins['pwm_gpio']:<2} -> TB6612 PWM")
    print(f"Motor two wires     -> TB6612 {pins['out']}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe one TB6612 motor channel directly.")
    parser.add_argument("--channel", choices=["a", "b"], default="a")
    parser.add_argument("--direction", choices=["forward", "backward"], default="forward")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--yes", action="store_true", help="Skip safety prompt.")
    args = parser.parse_args()

    speed = max(0.0, min(float(args.speed), 1.0))
    pins = PIN_TABLE[args.channel]
    _print_wiring(args.channel)

    try:
        from gpiozero import DigitalOutputDevice, PWMOutputDevice
    except Exception as exc:
        print("gpiozero import failed.")
        print("Install it on Raspberry Pi with:")
        print("  sudo apt update")
        print("  sudo apt install -y python3-gpiozero")
        print("If you are inside a venv, create/use it with --system-site-packages.")
        print(f"Error: {exc}")
        return 1

    print("gpiozero import ok. This only proves Python can control GPIO.")
    print("It does NOT prove the wires are correct yet.")
    print()

    if not args.yes:
        print("Safety: lift the car so the wheel cannot run away.")
        try:
            input("Press Enter to energize the motor, or Ctrl+C to cancel.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return 2

    standby = None
    in1 = None
    in2 = None
    pwm = None
    try:
        standby = DigitalOutputDevice(STBY_GPIO, active_high=True, initial_value=False)
        in1 = DigitalOutputDevice(pins["in1_gpio"], active_high=True, initial_value=False)
        in2 = DigitalOutputDevice(pins["in2_gpio"], active_high=True, initial_value=False)
        pwm = PWMOutputDevice(
            pins["pwm_gpio"],
            active_high=True,
            initial_value=0.0,
            frequency=1000,
        )

        standby.on()
        if args.direction == "forward":
            in1.on()
            in2.off()
        else:
            in1.off()
            in2.on()
        pwm.value = speed

        print(
            f"Running channel {args.channel.upper()} ({pins['name']}) "
            f"{args.direction} at speed={speed:.2f} for {args.seconds:.1f}s"
        )
        print(
            f"GPIO state: STBY={STBY_GPIO}=1, "
            f"IN1=GPIO{pins['in1_gpio']}={int(in1.value)}, "
            f"IN2=GPIO{pins['in2_gpio']}={int(in2.value)}, "
            f"PWM=GPIO{pins['pwm_gpio']}={pwm.value:.2f}"
        )
        time.sleep(max(0.0, args.seconds))
        print("Stopping.")
    finally:
        for device in (pwm, in1, in2):
            if device is not None:
                device.off()
                device.close()
        if standby is not None:
            standby.off()
            standby.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
