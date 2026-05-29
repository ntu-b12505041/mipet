"""Configuration values for the MiPet car."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class MotorPins:
    """GPIO pin mapping for a TB6612 dual motor driver."""

    left_in1: int = 17
    left_in2: int = 27
    left_pwm: int = 18
    right_in1: int = 23
    right_in2: int = 24
    right_pwm: int = 13
    standby: int = 22


@dataclass(frozen=True)
class MotorConfig:
    pins: MotorPins = MotorPins()
    pwm_frequency: int = 1000
    active_high: bool = True


@dataclass(frozen=True)
class CameraConfig:
    source: str = "0"
    backend: str = "opencv"
    width: int = 640
    height: int = 480
    fps: int = 30


@dataclass(frozen=True)
class LineDetectionConfig:
    mode: str = "black"
    roi_top_ratio: float = 0.55
    roi_bottom_ratio: float = 0.95
    black_value_max: int = 85
    min_area: float = 400.0
    morph_kernel_size: int = 5
    color_lower_hsv: Tuple[int, int, int] = (20, 80, 80)
    color_upper_hsv: Tuple[int, int, int] = (40, 255, 255)


@dataclass(frozen=True)
class SignDetectionConfig:
    mode: str = "both"
    red_area_min: float = 1000.0
    red_area_ratio_min: float = 0.012
    red_min_saturation: int = 80
    red_min_value: int = 60
    morph_kernel_size: int = 5
    aruco_dictionary: str = "DICT_4X4_50"
    target_aruco_ids: Tuple[int, ...] = (0,)


@dataclass(frozen=True)
class FoodDetectionConfig:
    model_path: str = ""
    labels_path: str = ""
    score_threshold: float = 0.50
    target_labels: Tuple[str, ...] = ("banana", "apple", "orange", "bottle", "cup", "bowl")
    input_mean: float = 127.5
    input_std: float = 127.5


@dataclass(frozen=True)
class DriveConfig:
    base_speed: float = 0.35
    max_speed: float = 0.60
    kp: float = 0.65
    max_turn: float = 0.45
    deadband_px: float = 22.0
