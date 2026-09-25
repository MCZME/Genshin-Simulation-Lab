"""超越之匙被动的事件钩子。

``TranscendenceStackingHook`` 只读事实，只产出下一轮结算要消费的请求：
装备者重击每次命中敌人时叠一层「超越」。层数条件之外没有额外门槛，因此不需要
注入目标状态只读端口；「超越」自身是纯层数载体（marker Buff），星超导增伤由
伤害修饰 provider 读层数换算。

触发窗口保存为钩子实例字段（与白湖冬羽一致）：``ContentCompiler`` 对每个宿主
只允许一个内容状态挂载，武器挂载到宿主体上会与宿主角色自身的状态段冲突；一旦
引入快照恢复或重放，窗口必须迁到内容状态挂载。
"""

from __future__ import annotations

from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.content.models import HookResult
from genshin_sim.content.weapons.claymore.a_teaspoon_of_transcendence.data import (
    CHARGED_ATTACK_MAIN_ATTACK_TAG,
    ENEMY_TARGET_PREFIX,
    FRAMES_PER_SECOND,
    STACK_TRIGGER_INTERVAL_SECONDS,
)
from genshin_sim.core.attributes import RuntimeSourceKind, RuntimeSourceRef
from genshin_sim.core.systems.buff import ApplyBuffRequest

_STACK_TRIGGER_INTERVAL_FRAMES = round(STACK_TRIGGER_INTERVAL_SECONDS * FRAMES_PER_SECOND)


class TranscendenceStackingHook:
    """装备者重击命中敌人时叠一层「超越」。

    每次命中恰好追加一层；层已满时由 Buff 的 ``stack_refresh`` 策略刷新共享期限，
    钩子不需要感知层数。
    """

    def __init__(
        self,
        *,
        handler_key: str,
        owner_ref: str,
        duration_frames: int,
        definition_key: str,
        source_key: str,
    ) -> None:
        if not isinstance(handler_key, str) or not handler_key.strip():
            raise ContentUnitValidationError("超越 handler_key 必须是非空字符串")
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("超越 owner_ref 必须是非空字符串")
        if duration_frames <= 0:
            raise ContentUnitValidationError("超越持续帧数必须为正")
        self._handler_key = handler_key
        self._owner_ref = owner_ref
        self._duration_frames = duration_frames
        self._definition_key = definition_key
        self._source_context = RuntimeSourceRef(RuntimeSourceKind.CONTENT, source_key)
        self._last_proc_frame: int | None = None
        # hook_key 与 state_key 都带用途后缀：同一效果单元可以有多个钩子，
        # 共用键会让解锁条件与内容状态段相互覆盖。
        self.hook_key = f"{handler_key}:{owner_ref}:transcendence"
        self.state_key = f"{handler_key}:transcendence"
        self.subscriptions = ("DAMAGE_RESOLVED",)
        self.priority = 0

    @property
    def owner_ref(self) -> str:
        return self._owner_ref

    @property
    def last_proc_frame(self) -> int | None:
        """最近一次成功叠层的帧；仅供测试与结果投影读取。"""

        return self._last_proc_frame

    def handle(self, event: object, context: object) -> HookResult:
        del context
        frame = getattr(event, "frame", 0)
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return HookResult()
        result = getattr(getattr(event, "payload", None), "result", None)
        if result is None:
            return HookResult()
        if not self._is_owner_result(result):
            return HookResult()
        if not self._is_charged_attack_hit_on_enemy(result):
            return HookResult()
        if self._last_proc_frame is not None and frame - self._last_proc_frame < (
            _STACK_TRIGGER_INTERVAL_FRAMES
        ):
            return HookResult()
        self._last_proc_frame = frame
        return HookResult(
            buff_requests=(
                ApplyBuffRequest(
                    request_id=f"hook:{self.hook_key}:{frame}",
                    frame=frame,
                    order=0,
                    definition_key=self._definition_key,
                    target_ref=result.source_ref,
                    source_context=self._source_context,
                    duration_frames=self._duration_frames,
                    applier_ref=result.source_ref,
                ),
            )
        )

    def _is_owner_result(self, result: object) -> bool:
        source_ref = getattr(result, "source_ref", None)
        return getattr(source_ref, "entity_id", None) == self._owner_ref

    @staticmethod
    def _is_charged_attack_hit_on_enemy(result: object) -> bool:
        if getattr(result, "main_attack_tag", None) != CHARGED_ATTACK_MAIN_ATTACK_TAG:
            return False
        target_id = getattr(getattr(result, "target_ref", None), "entity_id", None)
        return isinstance(target_id, str) and target_id.startswith(ENEMY_TARGET_PREFIX)
