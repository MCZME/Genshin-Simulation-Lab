# 元素附着、ICD 与反应设计规范

> 状态：生效
> 文档定位：元素附着、元素附着 ICD 和元素反应能力的工程准入、边界与验收规范。

最后更新：2026-08-03

本文规定新增或修改 Aura、元素附着 ICD、Reaction 及其跨系统协调能力时必须遵守的工程规则。本文不拥有具体反应的倍率、元素量、持续时间、Gate 或角色例外；具体稳定语义以对应架构设计、契约和验证入口为准。

## 1. 正式文档分工

元素机制文档按唯一职责分工：

| 文档类型 | 唯一职责 | 不应承载 |
| --- | --- | --- |
| 架构设计 | 状态所有权、领域模型、依赖、流程和不变量 | 版本实施步骤和重复契约字段 |
| 稳定契约 | 稳定 key、字段、公式输入、失败边界、序列化和兼容要求 | 完整设计解释和临时推导 |
| 决策记录 | 已确认的选择、原因、替代方案和冻结结论 | 领域文档的完整副本 |
| 本工程规范 | 进入设计、实现、组装和验证的准入条件 | 具体反应数值和机制真值 |

当前元素反应正式入口是[元素反应架构文档索引](../架构/系统/元素反应/文档索引.md)和[元素反应契约文档索引](../契约/元素反应/文档索引.md)。月绽放、月感电和月结晶已经拥有正式架构、契约和第一条生产切片；正式角色 Content、角色技能资源消费和部分外围入口仍按对应文档记录的边界推进。

## 2. 机制真值与证据

元素机制和数值只能按以下顺序进入正式设计：

1. 项目维护者确认的资料、数据和行为判断。
2. 与确认内容一致的正式架构和稳定契约。
3. 能够复现契约的单元测试、集成测试和 golden case。
4. 生产代码，用于核对实现是否落地，不能反向创造未确认的机制真值。

AI 记忆、旧项目代码、旧测试、第三方实现和外部资料只能用于发现问题、准备讨论或交叉核对，不能单独成为正式规则。来源不足时必须标注“草案”或“待确认”，不得猜测倍率、元素量、持续时间、衰减、Gate、范围、优先级、角色能力或特殊目标例外。

正式文档、代码和测试不应长期保留两套对外语义。出现冲突时，先根据确认资料和 golden case 判定真值，再同步修正架构、契约、实现和测试；不能用模糊兼容描述掩盖冲突。

## 3. 领域所有权与依赖边界

元素机制必须遵守领域自治。各领域的唯一真值如下：

| 领域 | 唯一拥有 | 明确不拥有 |
| --- | --- | --- |
| `core/elements/` | `Element`、`AuraKind`、精确元素量、主体/来源/Link 等中立语义 | 领域状态、反应公式和数据库数据 |
| Aura | Component、逐来源贡献、元素量投影、衰减、同元素更新、Reaction Link | ICD 窗口、反应候选、伤害和其他领域状态 |
| Aura ICD | Binding、窗口、序列游标和元素施加系数 | Aura 元素量、Reaction Gate、攻击冷却和反应判定 |
| Reaction | Definition、Profile、候选、DecisionSequence、occurrence、ReactionState、Gate、资源和强类型 Effect | Aura 元素量、最终伤害、空间索引和其他领域 Store |
| Damage | Profile、属性读取、公式、中间量和 DamageResult | 反应成立判断、Aura/ICD 状态和反应候选 |
| Coordination | 跨领域证据冻结、计划准备、统一校验、提交边界和事实顺序 | 长期领域状态、领域公式和万能调度 |
| Space、Buff、Shield、Health | 各自领域的实体、状态和公式 | Reaction 的内部状态和跨领域候选顺序 |

`core/systems/<domain>/` 不得 import 另一个领域的具体 Runtime 或 Store，也不得直接修改另一个领域的状态。跨领域只读条件使用中立模型或窄 Protocol；跨领域写入统一通过 `core/coordination/` 的限定用途协调器完成。

`content/` 可以提供类型化 Impact、元素施加意图、ICD Binding、来源观察和队伍能力证据，但不得注册全局 Reaction Definition、拥有 ReactionState 或直接修改 Aura/Reaction Store。

## 4. 稳定身份与精度

同一元素命中的伤害、元素施加、ICD、Reaction 和后续 Effect 必须能够稳定关联。至少区分以下身份：

- `impact_ref`：范围级 Impact 的共同因果来源。
- `interaction_id`：一个目标级元素交互。
- `request_id`、`application_id`：请求和元素施加的幂等身份。
- `operation_id`、`batch_id`：计划提交和事务批次的幂等身份。
- `work_id`、`parent_work_id`：帧内工作及其因果链。
- `occurrence_ref`、`effect_group_ref`、`effect_ref`：Reaction 成立和后续效果身份。
- `ElementalStateLinkRef`：Aura Component 与 ReactionState 的关系，不替代任一侧状态身份。

稳定身份不得来自显示名称、目录顺序、Python 对象地址或未声明的字符串拼接规则。范围 Impact 必须共享 `impact_ref`，不同目标必须使用不同 `interaction_id`；同一批次中的排序必须由明确的 `order` 或稳定 tie-break 冻结。

所有元素量使用 `AuraAmount` 等精确模型保存和计算。领域内部不得把精确元素量退化为浮点真值，不得用显示投影替代贡献账本或 Component 状态。

## 5. 元素交互的标准流程

一次普通元素交互必须经过以下阶段：

```text
Impact / target identity
-> frame normalization
-> Aura ICD plan
-> ICD 后实际元素预算
-> Aura read-only observation
-> Reaction candidate / DecisionSequence
-> Aura exact transition and Reaction plans
-> inline Effect and Damage preflight
-> seal / cross-domain validation
-> callback-free commit
-> fixed-order fact publication
-> next settlement round work
```

### 5.1 帧规范化

`ElementalStateFrameCoordinator` 是帧级 Aura、ICD 和 Reaction 状态同步入口：

- 帧 `F` 的本帧元素工作开始前，先规范化需要处理到 `F` 的领域状态。
- 同一帧重复规范化必须幂等；帧回退和跳过领域声明的 `next_required_frame` 必须失败。
- 查询不得隐式推进时间；所有时间推进都必须经过明确的帧或生命周期入口。
- due 的周期根、状态生命周期和 Reaction 资源工作必须冻结为强类型工作，再交给结算协调器处理。

Aura 的 `STANDARD` 自然衰减由 Aura 领域按其精确 Profile 处理；`STATE_LINKED` 和 `REACTION_MANAGED` 的消费、Link 或生命周期变化必须经过对应的跨领域计划。

### 5.2 ICD 与元素预算

带 Binding 的命中进入 `AuraIcdBatchPlanner`。ICD 只解析窗口和系数，不读取 Aura、伤害或 Reaction 状态：

- 有效系数为 `elemental_amount * icd_coefficient` 的结果输入后续 Aura/Reaction 流程。
- 系数为零时仍推进 ICD 游标并提交 ICD 事实，但不创建普通元素施加请求，也不触发依赖正元素预算的普通 Reaction。
- 没有 Binding 时使用明确的无冷却语义，不创建虚假的 ICD Record。
- ICD 窗口不因命中延长；窗口边界和序列游标以 Aura ICD 契约为准。
- ICD 计划不能脱离同一 `ElementalInteractionBatch` 单独提交。

元素量为零只禁止 Aura ICD、元素附着和依赖正元素预算的元素交互；独立的 `strike_type=BLUNT` 等已确认强类型证据仍可进入状态型 Reaction。

### 5.3 Aura 与 Reaction

Reaction 读取 Aura 的不可变观察和 ICD 后后手预算，决定候选、方向、顺序和消费语义；Aura 根据 Reaction 的强类型 transition 执行精确元素变化并返回结果。

- Reaction 不读取或持有 Aura Runtime、Record 或 MutationPlan。
- Aura 不判断 `reaction_key`，不读取 Damage 公式，也不构造 Reaction occurrence。
- 无匹配候选、后手预算为零、元素量不足或业务资格不满足，是类型化正常结果。
- 候选满足时，普通变体与月变体的排他关系、capability 准入和严格元素签名必须由 Reaction 公共候选组件明确表达，不依赖 Registry 注册顺序。
- 当前 Impact 的增幅或激化修正只能作用于该目标级 Impact 已携带的关联伤害。
- Reaction 新产生的 Damage、范围 Effect、周期 Effect 或空间影响必须形成后续 settlement round 或未来帧工作，不能在当前结算递归执行。

## 6. 事务、提交与事实

一个共同因果来源的 `ElementalInteractionBatch` 是主元素交互的原子边界；它不是整个 Action，也不自动覆盖后续 root chain。一个范围 Impact 的全部直接目标属于同一批次，任一目标的技术计划失败时整批不提交。

各领域分别通过 BatchPlanner 在工作副本或虚拟投影上准备：

```text
AuraIcdBatchPlanner
AuraBatchPlanner
ReactionBatchPlanner
ReactionState / Gate / Resource plans
inline Aura / Status / Space / Damage plans
```

首次写入前必须完成：

- 所有目标、关系、capability、来源观察和稳定排序冻结。
- batch、frame、root、interaction、request、operation 和 effect identity 一致且唯一。
- 各领域 Store version、完整前值、Link、Profile、Definition 和 adapter 校验通过。
- `CurrentImpactDamageAdjustment` 指向真实的目标级 Impact 和关联伤害。
- ReactionState、Aura Component 和空间实体的最终 Link 投影不会悬空。
- 所有正常业务阻止已经转换为类型化结果，不会在 commit 阶段失败。

commit 阶段只能应用已校验计划：

- 不查询属性、Aura、空间或数据库。
- 不重新计算公式或调用 handler。
- 不发布 Event。
- 不同步重入协调器、Planner 或 Store。
- 不依赖补偿写入维持原子性。

提交后的事实按元素交互契约规定的固定顺序发布。`EventEngine` 只发布和记录已经发生的事实，不是 Aura、ICD、Reaction 或 Damage 的当前结算入口。事实产生的后续行为必须转化为明确的下一 settlement round 或未来帧工作。已提交批次不可因后续 round 失败而回滚。

## 7. Reaction 机制组织

全局反应规则位于 `core/systems/reaction/mechanics/<mechanic_key>/`，并通过显式 bootstrap 注册：

- `ReactionDefinition`、稳定 `reaction_key`、`handler_key`、方向和 Profile 必须在组装阶段完成注册与校验。
- 禁止自动扫描、隐式导入注册或依赖目录顺序决定候选。
- 简单无状态机制可以只保留 `mechanic.py`；复杂机制按真实交互、状态、资源或空间实体拆分。
- 机制目录之间不得互相调用具体 Runtime、Store 或 handler。
- 两个以上机制确实共享且由 Reaction Runtime 拥有的稳定语义，才允许扩展公共模型或候选组件。
- 只有公式相似不足以合并机制目录，也不足以新增公共字段。

Reaction Effect 使用强类型判别联合表达当前 Impact 修正、派生 Damage Impact、元素传播、状态、控制、空间实体和资源变化。Reaction 不直接调用 Damage、Aura、Space、Buff 或 Health Runtime。

## 8. Link、周期和资源状态

凡是 Aura 与 ReactionState、ReactionState 与 Space 实体或 Reaction 与资源共享生命周期，必须把两侧写入放入同一跨领域计划：

- 创建、刷新、消费、到期、来源替换和移除都校验两侧完整最终投影。
- Link 必须成对出现；任何一侧终止都必须原子清理另一侧的 Link 或 binding。
- 周期状态保存游标、`next_required_frame` 和必要的捕获来源观察；周期工作不得伪造新的 occurrence。
- `ScheduledStateTickCause`、`ReactionEffectCause` 和 occurrence cause 必须保持身份语义，不互相冒充。
- Reaction 资源由 Reaction 自己拥有；消费和生产使用资源计划，不能由角色 Content 直接修改 ReactionState。
- 状态、Gate、资源和空间实体的事实必须在领域提交完成后发布，并保留稳定因果引用。

月反应的 capability、参与者冻结、草露资源、雷暴云、月笼和谐奏等具体字段由对应正式设计与契约拥有；本规范只要求它们遵守同样的计划、Link、身份和提交规则。

## 9. Content、组装与失败前置

组装阶段必须显式构造并校验：

- Aura、Aura ICD 和 Reaction 的 Registry。
- Definition、Profile、Binding、Application Profile、Gate、Damage Profile 和 handler 的稳定引用。
- `ReactionEligibilityReadPort`、来源观察、状态计划、scheduled root、Link validator、Space/Damage/Buff/Health adapter。
- 角色 Content 声明的 capability 与生产端口之间的完整映射。
- `ElementalSubjectRef`、来源身份、ReactionState、Aura Link 和空间实体引用的类型一致性。

以下问题必须在组装阶段或计划准备阶段报错，不能延迟到仿真运行中才表现为“无反应”：

- 缺少资产、Definition、handler、Profile、Binding、Application Profile、Gate 或 adapter。
- 重复稳定 key、重复注册或无法唯一选择 Profile/公式。
- JSON 或配置格式错误，或字段值无法满足契约。
- capability provider 声明支持能力，但对应端口无法准备计划。
- Reaction Effect、状态计划、资源计划或 scheduled root 没有唯一适配器。
- Link、稳定身份、Store version 或最终投影不一致。

格式正确但业务资格不满足可以返回类型化正常阻止；缺注册、stale plan、身份冲突、不变量破坏和 commit 阶段业务失败必须是技术错误，不能静默降级为无 Aura、无 Reaction 或无 Effect。

## 10. 验收标准

### 10.1 公共能力

新增或修改 Aura、ICD、Reaction 公共能力时，至少覆盖：

- 正常路径、零值、边界帧、帧回退和 required frame。
- 同帧多命中、多目标、稳定排序和虚拟状态可见性。
- 重复 request、operation、work、stale version 和计划 seal 后写入。
- 任一领域计划失败时的批量零提交。
- Link、Gate、资源、周期状态和空间实体的原子生命周期。
- 快照、事实顺序、因果链和 Event 写保护。

### 10.2 具体机制

每个生产 Reaction 至少需要：

- 对应正式架构设计和稳定契约。
- 机制单元测试、跨领域集成测试和至少一个纵向 golden case。
- 正常成立、正常阻止、关键元素量/状态边界和明确技术失败路径。
- 对候选顺序、并行/排他关系、来源观察时点、Gate、周期或派生 Effect 的验证。
- golden case 中记录来源、初始状态、帧、稳定 key、中间状态、计划结果和预期事实；不能只断言最终伤害数字。

测试通过只证明已覆盖路径满足当前预期，不代表未确认或未覆盖的游戏机制已经实现。

## 11. 扩展准入与文档维护

新增机制或公共能力前必须说明：

- 现有领域模型无法表达的具体缺口。
- 新状态、公式、资源和身份的唯一所有者。
- 新字段的默认值、校验、序列化和兼容边界。
- 跨领域计划的事务范围、事实顺序和失败语义。
- 至少两个机制是否真实共享拟扩展的公共能力。
- 对应单元、集成和 golden case 的验收方式。

改动以下内容时必须同步更新对应正式文档：

- Aura、ICD、Reaction 或协调器的职责、依赖和事务边界。
- 稳定 key、配置字段、状态模型、序列化或结果审计。
- Damage、Space、Buff、Health 或 Content 的跨领域端口。
- 事实类型、事实顺序、settlement round 或快照模型。

当前规范不记录版本实施时间线、历史评估或已删除方案。尚未形成结论的内容放入明确标记的草案、待确认或临时文档；一旦进入生产契约，应迁入对应架构、契约和测试，并从临时资料中移除重复真值。

## 12. 关联文档

- [元素附着系统设计](../架构/系统/元素附着系统设计.md)
- [元素附着 ICD 系统设计](../架构/系统/元素附着ICD系统设计.md)
- [元素反应架构文档索引](../架构/系统/元素反应/文档索引.md)
- [元素反应契约文档索引](../契约/元素反应/文档索引.md)
- [元素反应协调器设计](../架构/协调/元素反应协调器设计.md)
- [伤害系统设计](../架构/系统/伤害系统设计.md)
- [系统自治与跨系统协调](../决策/系统自治与跨系统协调.md)
- [项目决策记录](../决策/项目决策记录.md)
