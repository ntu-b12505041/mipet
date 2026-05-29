"""Decision logic and state machine for the MiPet car."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .config import DriveConfig
from .motor import clamp


class DriveState(str, Enum):
    START = "START"
    FOLLOW_LINE = "FOLLOW_LINE"
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    STOP_SIGN_DETECTED = "STOP_SIGN_DETECTED"
    FOOD_DETECTED = "FOOD_DETECTED"
    LINE_LOST = "LINE_LOST"


@dataclass(frozen=True)
class MotorCommand:
    left_speed: float
    right_speed: float
    state: DriveState
    reason: str = ""

    @staticmethod
    def stop(state: DriveState, reason: str) -> "MotorCommand":
        return MotorCommand(0.0, 0.0, state, reason)


def calculate_motor_speed(
    offset: Optional[float],
    frame_width: int,
    config: Optional[DriveConfig] = None,
) -> MotorCommand:
    config = config or DriveConfig()
    if offset is None:
        return MotorCommand.stop(DriveState.LINE_LOST, "line not found")

    if frame_width <= 0:
        raise ValueError("frame_width must be positive")

    state = DriveState.FOLLOW_LINE
    corrected_offset = float(offset)
    if abs(corrected_offset) <= config.deadband_px:
        corrected_offset = 0.0
    elif corrected_offset < 0:
        state = DriveState.TURN_LEFT
    else:
        state = DriveState.TURN_RIGHT

    normalized_offset = clamp(corrected_offset / (frame_width / 2.0), -1.0, 1.0)
    turn = clamp(config.kp * normalized_offset, -config.max_turn, config.max_turn)
    left_speed = clamp(config.base_speed + turn, 0.0, config.max_speed)
    right_speed = clamp(config.base_speed - turn, 0.0, config.max_speed)

    return MotorCommand(
        left_speed=left_speed,
        right_speed=right_speed,
        state=state,
        reason=f"offset={offset:.1f}, turn={turn:.2f}",
    )


def decide(line_result, sign_result, food_result=None, config: Optional[DriveConfig] = None) -> MotorCommand:
    if isinstance(food_result, DriveConfig) and config is None:
        config = food_result
        food_result = None

    if getattr(food_result, "detected", False):
        label = getattr(food_result, "label", "food")
        score = getattr(food_result, "score", 0.0)
        return MotorCommand.stop(DriveState.FOOD_DETECTED, f"{label} detected score={score:.2f}")

    if getattr(sign_result, "detected", False):
        method = getattr(sign_result, "method", "sign")
        return MotorCommand.stop(DriveState.STOP_SIGN_DETECTED, f"{method} detected")

    if not getattr(line_result, "found", False):
        return MotorCommand.stop(DriveState.LINE_LOST, "line not found")

    return calculate_motor_speed(
        getattr(line_result, "offset", None),
        getattr(line_result, "frame_width", 0),
        config,
    )
