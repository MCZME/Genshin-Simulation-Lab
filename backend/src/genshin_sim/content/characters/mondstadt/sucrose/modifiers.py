"""砂糖内容修饰：固有天赋 Buff 定义、前夜礼标记 Buff 与伤害修饰 provider。

三组产物按**作用面**分道：

- **A1 触媒置换术 / A4 小小的慧风**：限时**元素精通**提升，作用对象是队伍中的
  角色主体（逐个投放），由 Buff 定义承载、``hooks.py`` 在触发帧发放。
  - A1 = 固定 +50 精通（``FLAT_ADD``），来源是被扩散元素对应的元素类型匹配，
    本身不是「基于其他属性折算」的转化效果，故产物标记保持默认（可被二次转化）。
  - A4 = 砂糖快照精通的 20%（``FLAT_ADD``，数值在触发帧算好后随申请携带），
    属转化效果：产物标记 ``reconvertible=False``（不可被二次转化），避免被另一
    次「读精通再折算」的效果二次吸收（实施规划 §11.4、属性系统契约 §11.4）。
  - 两者均为覆盖刷新（重触发刷新时长、不叠数值）。

- **魔女的前夜礼（``passive:9``）两档**：作用面是「普通攻击 / 重击 / 下落攻击 /
  元素战技 / 元素爆发」五类**伤害**，不是某个属性——项目属性面板没有
  「普攻伤害加成」这类键，把比例写成属性词条会连带作用到反应伤害上，故数值
  经伤害系统的 ``DAMAGE_BONUS_ADD`` 词条进入伤害加成加算区；Buff 只承载
  「窗口开着」这一事实（``marker_only``，不带属性词条），由 provider 读存在性
  贡献词条（炉火融炼之心 4 件套·星烁增伤窗口同款形态）。两档独立计时、
  互不覆盖，同帧并存时各自贡献、加算叠加。

- **C6 魔导增强（+8.57142%）**：作用面是**对应元素伤害加成**，它**是**属性
  （``BONUS_DAMAGE_<element>``），故走普通 Buff 定义。对应元素由触发帧的染色
  结果决定，而 Buff 定义的词条集合是静态的，因此定义一次声明八条元素词条、
  投放时只给对应元素那一条填数值、其余填 ``0.0``（框架要求
  ``modifier_values`` 与模板逐条匹配，不能省略）。

- **C6 染色增伤（+20%，命座第六层本体）**：与魔导增强同形态（属性面、八条
  元素词条、投放时只填对应元素），区别只在数值来源与投放范围——数值取资产
  ``c6`` 效果行、投放给**队伍中所有角色（含砂糖自己）**。
"""

from __future__ import annotations

from genshin_sim.content.characters.mondstadt.sucrose.data import (
    SUCROSE_A1_BUFF_DEFINITION_KEY,
    SUCROSE_A1_CONFLICT_KEY,
    SUCROSE_A1_MASTERY_TERM_KEY,
    SUCROSE_A1_MECHANIC_KEY,
    SUCROSE_A4_BUFF_DEFINITION_KEY,
    SUCROSE_A4_CONFLICT_KEY,
    SUCROSE_A4_MASTERY_TERM_KEY,
    SUCROSE_A4_MECHANIC_KEY,
    SUCROSE_C6_AUDIT_TAG,
    SUCROSE_C6_BUFF_DEFINITION_KEY,
    SUCROSE_C6_CONFLICT_KEY,
    SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY,
    SUCROSE_C6_MAGE_ENHANCEMENT_CONFLICT_KEY,
    SUCROSE_C6_MAGE_ENHANCEMENT_MECHANIC_KEY,
    SUCROSE_C6_MECHANIC_KEY,
    SUCROSE_CHARACTER_HANDLER_KEY,
    SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
    SUCROSE_PASSIVE_A1_HANDLER_KEY,
    SUCROSE_PASSIVE_A4_HANDLER_KEY,
    SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
    SUCROSE_WITCHES_EVE_AUDIT_TAG,
    SUCROSE_WITCHES_EVE_DAMAGE_TAGS,
    SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY,
    SUCROSE_WITCHES_EVE_LARGE_CONFLICT_KEY,
    SUCROSE_WITCHES_EVE_LARGE_MECHANIC_KEY,
    SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY,
    SUCROSE_WITCHES_EVE_SMALL_CONFLICT_KEY,
    SUCROSE_WITCHES_EVE_SMALL_MECHANIC_KEY,
)
from genshin_sim.content.definitions.content_unit import ContentUnitValidationError
from genshin_sim.core.attributes import (
    ELEMENT_TO_DAMAGE_BONUS_KEY,
    STAT_ELEMENTAL_MASTERY,
    AttributeSubjectKind,
    AttributeSubjectRef,
    ModifierStage,
    RuntimeSourceKind,
    RuntimeSourceRef,
)
from genshin_sim.core.elements import Element
from genshin_sim.core.systems.buff import (
    BuffApplicationPolicy,
    BuffAttributeModifierTemplate,
    BuffDefinition,
    BuffModifierValue,
    BuffValueRefreshPolicy,
)
from genshin_sim.core.systems.buff.protocols import TargetBuffPresenceReadPort
from genshin_sim.core.systems.damage import (
    DamageModifierProviderSpec,
    DamageModifierStage,
    DamageModifierTerm,
)
from genshin_sim.core.systems.damage.keys import FORMULA_KEY_GENERAL
from genshin_sim.core.systems.damage.models import DamageQuery
from genshin_sim.core.systems.damage.resolver import DamageResolutionScope


def build_a1_mastery_buff_definition() -> BuffDefinition:
    """A1 触媒置换术：与被扩散元素同元素的角色 +50 元素精通（覆盖刷新）。"""

    return BuffDefinition(
        definition_key=SUCROSE_A1_BUFF_DEFINITION_KEY,
        mechanic_key=SUCROSE_A1_MECHANIC_KEY,
        handler_key=SUCROSE_PASSIVE_A1_HANDLER_KEY,
        conflict_key=SUCROSE_A1_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=SUCROSE_A1_MASTERY_TERM_KEY,
                target_key=STAT_ELEMENTAL_MASTERY,
                stage=ModifierStage.FLAT_ADD,
            ),
        ),
        tags=frozenset({SUCROSE_CHARACTER_HANDLER_KEY, SUCROSE_PASSIVE_A1_HANDLER_KEY}),
        display_name="触媒置换术·元素精通",
    )


def build_a4_mastery_buff_definition() -> BuffDefinition:
    """A4 小小的慧风：全队（除砂糖）按砂糖快照精通 20% 提升精通（覆盖刷新）。

    产物标记 ``reconvertible=False``：该加成的数值由「读砂糖精通再折算」得出，
    属转化效果，不能再被另一次同类折算读入（实施规划 §11.4）。
    """

    return BuffDefinition(
        definition_key=SUCROSE_A4_BUFF_DEFINITION_KEY,
        mechanic_key=SUCROSE_A4_MECHANIC_KEY,
        handler_key=SUCROSE_PASSIVE_A4_HANDLER_KEY,
        conflict_key=SUCROSE_A4_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=(
            BuffAttributeModifierTemplate(
                term_key=SUCROSE_A4_MASTERY_TERM_KEY,
                target_key=STAT_ELEMENTAL_MASTERY,
                stage=ModifierStage.FLAT_ADD,
                reconvertible=False,
            ),
        ),
        tags=frozenset({SUCROSE_CHARACTER_HANDLER_KEY, SUCROSE_PASSIVE_A4_HANDLER_KEY}),
        display_name="小小的慧风·元素精通",
    )


def build_witches_eve_small_buff_definition() -> BuffDefinition:
    """前夜礼小型风灵档：只承载「15s 窗口开着」这一事实的标记 Buff。

    数值由伤害 provider 贡献（五类伤害加成在伤害账单侧，不经过属性系统），
    故 ``marker_only=True`` 且不声明任何属性词条（框架双向校验）。
    """

    return BuffDefinition(
        definition_key=SUCROSE_WITCHES_EVE_SMALL_BUFF_DEFINITION_KEY,
        mechanic_key=SUCROSE_WITCHES_EVE_SMALL_MECHANIC_KEY,
        handler_key=SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
        conflict_key=SUCROSE_WITCHES_EVE_SMALL_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        marker_only=True,
        tags=frozenset({SUCROSE_CHARACTER_HANDLER_KEY, SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY}),
        display_name="魔女的前夜礼·小型风灵增伤窗口",
    )


def build_witches_eve_large_buff_definition() -> BuffDefinition:
    """前夜礼大型风灵档：只承载「20s 窗口开着」这一事实的标记 Buff。

    与小型档各自独立计时、互不覆盖（独立冲突键），同帧并存时两档各自贡献。
    """

    return BuffDefinition(
        definition_key=SUCROSE_WITCHES_EVE_LARGE_BUFF_DEFINITION_KEY,
        mechanic_key=SUCROSE_WITCHES_EVE_LARGE_MECHANIC_KEY,
        handler_key=SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY,
        conflict_key=SUCROSE_WITCHES_EVE_LARGE_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        marker_only=True,
        tags=frozenset({SUCROSE_CHARACTER_HANDLER_KEY, SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY}),
        display_name="魔女的前夜礼·大型风灵增伤窗口",
    )


# C6 魔导增强的元素词条顺序：固定按元素枚举顺序声明，投放侧按同一顺序填值，
# 保证「同一元素 → 同一 term_key」的稳定映射（不受字典遍历顺序影响）。
MAGE_ENHANCEMENT_ELEMENTS = (
    Element.PHYSICAL,
    Element.PYRO,
    Element.HYDRO,
    Element.ELECTRO,
    Element.CRYO,
    Element.ANEMO,
    Element.GEO,
    Element.DENDRO,
)


def mage_enhancement_term_key(element: Element) -> str:
    """C6 魔导增强内某元素对应的词条键。"""

    return f"{SUCROSE_C6_MAGE_ENHANCEMENT_MECHANIC_KEY}.bonus.{element.value}"


def build_c6_mage_enhancement_buff_definition() -> BuffDefinition:
    """C6 魔导增强：魔导角色额外获得对应元素伤害加成（覆盖刷新）。

    一次声明八条元素词条，投放时只给对应元素那一条填数值、其余填 ``0.0``
    （``modifier_values`` 必须与模板逐条匹配，不能省略）；这样「哪个元素」由
    **投放侧**决定，Buff 定义本身保持静态。
    """

    return BuffDefinition(
        definition_key=SUCROSE_C6_MAGE_ENHANCEMENT_BUFF_DEFINITION_KEY,
        mechanic_key=SUCROSE_C6_MAGE_ENHANCEMENT_MECHANIC_KEY,
        # 归属 C6 命座单元：Buff 定义的 handler_key 必须与贡献它的内容单元一致
        # （装配期按此校验归属），故取命座 handler 而非角色 handler。
        handler_key=SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
        conflict_key=SUCROSE_C6_MAGE_ENHANCEMENT_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=tuple(
            BuffAttributeModifierTemplate(
                term_key=mage_enhancement_term_key(element),
                target_key=ELEMENT_TO_DAMAGE_BONUS_KEY[element.value],
                stage=ModifierStage.FLAT_ADD,
                audit_tags=(SUCROSE_WITCHES_EVE_AUDIT_TAG,),
            )
            for element in MAGE_ENHANCEMENT_ELEMENTS
        ),
        tags=frozenset({SUCROSE_CHARACTER_HANDLER_KEY}),
        display_name="混元熵增论·魔导增强",
    )


def mage_enhancement_modifier_values(
    element: Element,
    bonus: float,
) -> tuple[BuffModifierValue, ...]:
    """按染色元素组装 C6 魔导增强的 ``modifier_values``（其余元素填 0）。"""

    return tuple(
        BuffModifierValue(
            mage_enhancement_term_key(candidate),
            bonus if candidate is element else 0.0,
        )
        for candidate in MAGE_ENHANCEMENT_ELEMENTS
    )


def c6_damage_bonus_term_key(element: Element) -> str:
    """C6 染色增伤内某元素对应的词条键（与魔导增强各自独立的一套）。"""

    return f"{SUCROSE_C6_MECHANIC_KEY}.bonus.{element.value}"


def build_c6_damage_bonus_buff_definition() -> BuffDefinition:
    """C6 混元熵增论本体：全队（含砂糖）对应元素伤害加成（覆盖刷新）。

    与魔导增强同形态：作用面是属性（``BONUS_DAMAGE_<element>``），一次声明八条
    元素词条，投放时只给染色元素那一条填数值、其余 ``0.0``。两者用不同的
    定义键与冲突键，因此互不覆盖、可并存（魔导增强是**额外**加成）。
    """

    return BuffDefinition(
        definition_key=SUCROSE_C6_BUFF_DEFINITION_KEY,
        mechanic_key=SUCROSE_C6_MECHANIC_KEY,
        handler_key=SUCROSE_CONSTELLATION_C6_HANDLER_KEY,
        conflict_key=SUCROSE_C6_CONFLICT_KEY,
        target_kinds=frozenset({AttributeSubjectKind.CHARACTER}),
        application_policy=BuffApplicationPolicy.REFRESH,
        value_refresh_policy=BuffValueRefreshPolicy.REPLACE_LATEST,
        max_stacks=1,
        attribute_modifiers=tuple(
            BuffAttributeModifierTemplate(
                term_key=c6_damage_bonus_term_key(element),
                target_key=ELEMENT_TO_DAMAGE_BONUS_KEY[element.value],
                stage=ModifierStage.FLAT_ADD,
                audit_tags=(SUCROSE_C6_AUDIT_TAG,),
            )
            for element in MAGE_ENHANCEMENT_ELEMENTS
        ),
        tags=frozenset({SUCROSE_CHARACTER_HANDLER_KEY, SUCROSE_CONSTELLATION_C6_HANDLER_KEY}),
        display_name="混元熵增论·对应元素伤害加成",
    )


def c6_damage_bonus_modifier_values(
    element: Element,
    bonus: float,
) -> tuple[BuffModifierValue, ...]:
    """按染色元素组装 C6 本体增伤的 ``modifier_values``（其余元素填 0）。"""

    return tuple(
        BuffModifierValue(
            c6_damage_bonus_term_key(candidate),
            bonus if candidate is element else 0.0,
        )
        for candidate in MAGE_ENHANCEMENT_ELEMENTS
    )


class SucroseWitchesEveDamageBonusProvider:
    """魔女的前夜礼某一档：按标记 Buff 存在性贡献五类伤害加成。

    窗口存在性与时长由挂在**每个角色主体**上的标记 Buff 承载（小型档投全队、
    大型档投魔导角色），provider 只读存在性、不持有状态、不自行计时，因此
    覆盖刷新与否完全由 Buff 系统的 ``REFRESH`` 策略决定。

    自筛三条，缺一不可：

    - ``main_attack_tag`` 落在源站五类里——这是「只加成这五类伤害」的判据；
    - ``formula_key`` 为通用公式——``DAMAGE_BONUS_ADD`` 只在通用公式放行，
      越界阶段会被 ``validate_formula_modifier_stages`` 硬拒并让整次结算失败；
    - 伤害来源是**角色主体**——创建物（大型风灵）的伤害归属宿主角色，故风灵
      按拍输出同样吃到加成，与「元素爆发造成的伤害」口径一致。
    """

    def __init__(
        self,
        *,
        owner_ref: str,
        scope_key: str,
        buff_definition_key: str,
        bonus: float,
        display_name: str,
    ) -> None:
        if not isinstance(owner_ref, str) or not owner_ref.strip():
            raise ContentUnitValidationError("前夜礼增伤 owner_ref 必须是非空字符串")
        if not isinstance(scope_key, str) or not scope_key.strip():
            raise ContentUnitValidationError("前夜礼增伤 scope_key 必须是非空字符串")
        if not isinstance(buff_definition_key, str) or not buff_definition_key.strip():
            raise ContentUnitValidationError("前夜礼增伤 buff_definition_key 必须是非空字符串")
        if isinstance(bonus, bool) or not isinstance(bonus, int | float) or float(bonus) <= 0.0:
            raise ContentUnitValidationError("前夜礼增伤比例必须为正数")
        self._buff_definition_key = buff_definition_key
        self._bonus = float(bonus)
        self._provider_key = f"{SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY}.{scope_key}:{owner_ref}"
        self._source_ref = RuntimeSourceRef(
            RuntimeSourceKind.MECHANIC,
            f"{SUCROSE_PASSIVE_WITCHES_EVE_HANDLER_KEY}.{scope_key}",
        )
        self.provider_spec = DamageModifierProviderSpec(
            provider_key=self._provider_key,
            writes=frozenset({DamageModifierStage.DAMAGE_BONUS_ADD}),
            owner_ref=AttributeSubjectRef.character(owner_ref),
            display_name=display_name,
        )
        self._target_status_port: TargetBuffPresenceReadPort | None = None

    def bind_runtime_ports(
        self,
        *,
        target_status_port: TargetBuffPresenceReadPort,
    ) -> None:
        """装配期注入状态只读端口；未绑定时不贡献。"""

        self._target_status_port = target_status_port

    def contribute(
        self,
        query: DamageQuery,
        scope: DamageResolutionScope,
    ) -> tuple[DamageModifierTerm, ...]:
        del scope
        request = query.request
        if request.formula_key != FORMULA_KEY_GENERAL:
            return ()
        if request.main_attack_tag not in SUCROSE_WITCHES_EVE_DAMAGE_TAGS:
            return ()
        if request.source_ref.kind is not AttributeSubjectKind.CHARACTER:
            return ()
        port = self._target_status_port
        if port is None:
            return ()
        if not port.has_buff(
            target_ref=request.source_ref,
            definition_key=self._buff_definition_key,
            frame=request.frame,
        ):
            return ()
        return (
            DamageModifierTerm(
                stage=DamageModifierStage.DAMAGE_BONUS_ADD,
                value=self._bonus,
                provider_key=self._provider_key,
                source_ref=self._source_ref,
                audit_tags=(SUCROSE_WITCHES_EVE_AUDIT_TAG,),
            ),
        )
