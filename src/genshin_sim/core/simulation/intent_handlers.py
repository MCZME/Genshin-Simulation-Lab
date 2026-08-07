"""统一意图队列的内置类型适配器。

适配器把意图载荷转发到既有领域入口，供内容 hook 与后续分发路径迁移使用。
"""

from __future__ import annotations

from typing import Protocol

from genshin_sim.core.contracts.intents import IntentEnvelope
from genshin_sim.core.impacts.models import ImpactRequest
from genshin_sim.core.systems.buff.models import ApplyBuffRequest
from genshin_sim.core.systems.cooldown.models import CooldownMutationBatchRequest


class ImpactRequestDispatcherPort(Protocol):
    def dispatch_requests(
        self,
        context: object,
        requests: tuple[ImpactRequest, ...],
    ) -> None: ...


class ImpactIntentHandler:
    """把 IMPACT 意图转发到既有影响请求分发器。"""

    def __init__(self, dispatcher: ImpactRequestDispatcherPort) -> None:
        self.dispatcher = dispatcher

    def handle(self, context: object, intent: IntentEnvelope) -> None:
        request = intent.payload
        if not isinstance(request, ImpactRequest):
            raise TypeError(f"IMPACT 意图载荷必须是 ImpactRequest，实际 {type(request).__name__}")
        self.dispatcher.dispatch_requests(context, (request,))


class BuffApplyPort(Protocol):
    def apply(self, request: ApplyBuffRequest) -> object: ...


class BuffIntentHandler:
    """把 BUFF 意图转发到 BuffRuntime.apply。"""

    def __init__(self, runtime: BuffApplyPort) -> None:
        self.runtime = runtime

    def handle(self, context: object, intent: IntentEnvelope) -> None:
        del context
        request = intent.payload
        if not isinstance(request, ApplyBuffRequest):
            raise TypeError(f"BUFF 意图载荷必须是 ApplyBuffRequest，实际 {type(request).__name__}")
        self.runtime.apply(request)


class CooldownBatchPort(Protocol):
    def mutate_batch(self, request: CooldownMutationBatchRequest) -> object: ...


class CooldownIntentHandler:
    """把 COOLDOWN 意图转发到 CooldownRuntime.mutate_batch。"""

    def __init__(self, runtime: CooldownBatchPort) -> None:
        self.runtime = runtime

    def handle(self, context: object, intent: IntentEnvelope) -> None:
        del context
        request = intent.payload
        if not isinstance(request, CooldownMutationBatchRequest):
            raise TypeError(
                "COOLDOWN 意图载荷必须是 CooldownMutationBatchRequest，"
                f"实际 {type(request).__name__}"
            )
        self.runtime.mutate_batch(request)
