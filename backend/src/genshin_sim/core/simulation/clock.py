from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class FrameClock:
    """仿真帧时钟。

    第 0 帧保留为初始化帧，用于完成仿真运行前的构造和装配。
    模拟器的常规帧推进从第 1 帧开始。
    """

    current_frame: int = 0
    frames_per_second: int = 60

    def advance(self, frames: int = 1) -> int:
        if frames < 0:
            msg = "推进帧数不能为负数"
            raise ValueError(msg)
        self.current_frame += frames
        return self.current_frame

    def reset(self) -> None:
        self.current_frame = 0
