"""TB6612 motor driver control."""

from dataclasses import dataclass
import logging
from typing import Optional

from .config import MotorConfig

LOGGER = logging.getLogger(__name__)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def normalize_speed(speed: float) -> float:
    """Normalize a speed value to 0.0..1.0.

    Values larger than 1 are treated as percentages, so 50 means 0.50.
    """

    speed = float(speed)
    if abs(speed) > 1.0:
        speed = speed / 100.0
    return clamp(abs(speed), 0.0, 1.0)


class MotorHardwareError(RuntimeError):
    """Raised when GPIO motor hardware cannot be initialized."""


class _MockOutputDevice:
    def __init__(self, pin: int, label: str) -> None:
        self.pin = pin
        self.label = label
        self.value = 0.0

    def on(self) -> None:
        self.value = 1.0

    def off(self) -> None:
        self.value = 0.0

    def close(self) -> None:
        self.off()


class _MockPWMOutputDevice(_MockOutputDevice):
    pass


@dataclass(frozen=True)
class MotorSnapshot:
    left_in1: float
    left_in2: float
    left_pwm: float
    right_in1: float
    right_in2: float
    right_pwm: float
    standby: float


class _MotorChannel:
    def __init__(self, in1, in2, pwm, label: str) -> None:
        self._in1 = in1
        self._in2 = in2
        self._pwm = pwm
        self.label = label

    def run(self, signed_speed: float) -> None:
        signed_speed = clamp(float(signed_speed), -1.0, 1.0)
        if signed_speed > 0:
            self._in1.on()
            self._in2.off()
        elif signed_speed < 0:
            self._in1.off()
            self._in2.on()
        else:
            self._in1.off()
            self._in2.off()

        self._pwm.value = abs(signed_speed)

    def stop(self) -> None:
        self.run(0.0)

    def close(self) -> None:
        self.stop()
        self._in1.close()
        self._in2.close()
        self._pwm.close()


class MotorDriver:
    """High-level differential drive wrapper for TB6612.

    Positive speed means forward. Negative speed means backward.
    """

    def __init__(
        self,
        config: Optional[MotorConfig] = None,
        *,
        dry_run: bool = False,
        allow_mock_fallback: bool = True,
    ) -> None:
        self.config = config or MotorConfig()
        self.dry_run = dry_run
        self._closed = False
        self._using_mock = dry_run

        output_cls = None
        pwm_cls = None
        if not dry_run:
            try:
                from gpiozero import DigitalOutputDevice, PWMOutputDevice

                output_cls = DigitalOutputDevice
                pwm_cls = PWMOutputDevice
            except Exception as exc:
                if not allow_mock_fallback:
                    raise MotorHardwareError(
                        "gpiozero is not available; install it on Raspberry Pi or use dry_run=True."
                    ) from exc
                LOGGER.warning("gpiozero unavailable; falling back to dry-run motor outputs.")
                self._using_mock = True

        if self._using_mock:
            output_cls = lambda pin, **_: _MockOutputDevice(pin, f"GPIO{pin}")
            pwm_cls = lambda pin, **_: _MockPWMOutputDevice(pin, f"PWM{pin}")

        pins = self.config.pins
        output_kwargs = {"active_high": self.config.active_high}
        pwm_kwargs = {
            "active_high": self.config.active_high,
            "frequency": self.config.pwm_frequency,
            "initial_value": 0.0,
        }

        self._standby = output_cls(pins.standby, **output_kwargs)
        self._left = _MotorChannel(
            output_cls(pins.left_in1, **output_kwargs),
            output_cls(pins.left_in2, **output_kwargs),
            pwm_cls(pins.left_pwm, **pwm_kwargs),
            "left",
        )
        self._right = _MotorChannel(
            output_cls(pins.right_in1, **output_kwargs),
            output_cls(pins.right_in2, **output_kwargs),
            pwm_cls(pins.right_pwm, **pwm_kwargs),
            "right",
        )

        self._standby.on()
        self.stop()

    @property
    def using_mock(self) -> bool:
        return self._using_mock

    def set_speed(self, left_speed: float, right_speed: float) -> None:
        self._ensure_open()
        self._standby.on()
        self._left.run(clamp(left_speed, -1.0, 1.0))
        self._right.run(clamp(right_speed, -1.0, 1.0))

    def forward(self, speed: float) -> None:
        speed = normalize_speed(speed)
        self.set_speed(speed, speed)

    def backward(self, speed: float) -> None:
        speed = normalize_speed(speed)
        self.set_speed(-speed, -speed)

    def turn_left(self, speed: float, inner_ratio: float = 0.0) -> None:
        speed = normalize_speed(speed)
        inner_ratio = clamp(inner_ratio, 0.0, 1.0)
        self.set_speed(speed * inner_ratio, speed)

    def turn_right(self, speed: float, inner_ratio: float = 0.0) -> None:
        speed = normalize_speed(speed)
        inner_ratio = clamp(inner_ratio, 0.0, 1.0)
        self.set_speed(speed, speed * inner_ratio)

    def stop(self) -> None:
        if self._closed:
            return
        self._left.stop()
        self._right.stop()

    def standby(self) -> None:
        self.stop()
        self._standby.off()

    def snapshot(self) -> MotorSnapshot:
        return MotorSnapshot(
            left_in1=self._left._in1.value,
            left_in2=self._left._in2.value,
            left_pwm=self._left._pwm.value,
            right_in1=self._right._in1.value,
            right_in2=self._right._in2.value,
            right_pwm=self._right._pwm.value,
            standby=self._standby.value,
        )

    def close(self) -> None:
        if self._closed:
            return
        self.stop()
        self._standby.off()
        self._left.close()
        self._right.close()
        self._standby.close()
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise MotorHardwareError("MotorDriver is already closed.")

    def __enter__(self) -> "MotorDriver":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

