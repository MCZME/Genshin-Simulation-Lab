"""苍古自由之誓被动的事件钩子：奋起之符与「千年的大乐章·抗争之歌」。"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.team import PLAYER_TEAM_SCOPE
from genshin_sim.content.weapons.sword.freedom_sworn.data import (
    FREEDOM_SWORN_SONG_ATK_TERM_KEY,
    SIGILS_REQUIRED,
)
from genshin_sim.core.attributes import AttributeSubjectRef, RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff import ApplyBuffRequest, BuffModifierValue

_SIGILS_REQUIRED = SIGILS_REQUIRED


class FreedomSwornSigilHook:
    """装备者触发元素反应积攒奋起之符，满 2 枚消耗并开启全队抗争之歌。"""

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        slot: int,
        song_atk_percent: float,
        song_duration_frames: int,
        sigil_interval_frames: int,
        sigil_lockout_frames: int,
        definition_key: str,
        source_key: str,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("奋起之符 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("奋起之符 owner_ref 必须是非空字符串")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot <= 0:
            raise ContentUnitValidationError("奋起之符必须绑定正整数队伍槽位")
        if song_duration_frames <= 0:
            raise ContentUnitValidationError("抗争之歌持续帧数必须为正")
        if sigil_interval_frames <= 0:
            raise ContentUnitValidationError("奋起之符触发间隔帧数必须为正")
        if sigil_lockout_frames <= 0:
            raise ContentUnitValidationError("奋起之符锁定帧数必须为正")
        self._handler_key = handler_key
        self._owner_ref = owner_ref
        self._owner_subject_ref = AttributeSubjectRef.character(owner_ref)
        self._team_subject_ref = AttributeSubjectRef.team(PLAYER_TEAM_SCOPE)
        self._slot = slot
        self._song_atk_percent = song_atk_percent
        self._song_duration_frames = song_duration_frames
        self._sigil_interval_frames = sigil_interval_frames
        self._sigil_lockout_frames = sigil_lockout_frames
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        # 触发窗口保存为钩子实例字段：符数、最近获得符的帧、锁定截止帧。
        self._sigil_count = 0
        self._last_sigil_frame: int | None = None
        self._lockout_until_frame = 0
        # hook_key 与 state_key 都带用途后缀：同一效果单元可以有多个钩子，
        # 共用键会让解锁条件与内容状态段相互覆盖。
        self.hook_key = f"{handler_key}:{owner_ref}:sigils"
        self.state_key = f"{handler_key}:sigils"
        self.subscriptions = ("REACTION_OCCURRED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        occurrence = getattr(getattr(event, "payload", None), "occurrence", None)
        if occurrence is None:
            return HookResult()
        source_key = getattr(getattr(occurrence, "source_ref", None), "source_key", None)
        if source_key != self._owner_ref:
            return HookResult()
        if frame < self._lockout_until_frame:
            return HookResult()
        if self._last_sigil_frame is not None and frame - self._last_sigil_frame < (
            self._sigil_interval_frames
        ):
            return HookResult()
        self._last_sigil_frame = frame
        self._sigil_count += 1
        if self._sigil_count < _SIGILS_REQUIRED:
            return HookResult()
        self._sigil_count = 0
        self._lockout_until_frame = frame + self._sigil_lockout_frames
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}",
                    frame=frame,
                    order=0,
                    definition_key=self._definition_key,
                    target_ref=self._team_subject_ref,
                    source_context=self._source_context,
                    duration_frames=self._song_duration_frames,
                    applier_ref=self._owner_subject_ref,
                    modifier_values=(
                        BuffModifierValue(
                            term_key=FREEDOM_SWORN_SONG_ATK_TERM_KEY,
                            value=self._song_atk_percent,
                        ),
                    ),
                ),
            )
        )
