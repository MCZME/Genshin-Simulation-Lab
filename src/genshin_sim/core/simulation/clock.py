from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FrameClock:
    """仿真帧时钟。"""

    current_frame: int = 0
    frames_per_second: int = 60

    def advance(self, frames: int = 1) -> int:
        if frames < 0:
            msg = "frames must be non-negative"
            raise ValueError(msg)
        self.current_frame += frames
        return self.current_frame

    def reset(self) -> None:
        self.current_frame = 0
