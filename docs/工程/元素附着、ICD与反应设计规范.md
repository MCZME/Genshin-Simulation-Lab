# 元素附着、ICD 与反应设计规范

> 状态：生效（元素机制专题工程准入）。
> 文档定位：新增或修改 Aura、元素附着 ICD 和 Reaction 及其跨系统协调能力时的工程准入、边界与验收规范。
> 最后更新：2026-09-05。

本文规定新增或修改 Aura、元素附着 ICD、Reaction 及其跨系统协调能力时必须遵守的工程规则。本文不拥有具体反应的倍率、元素量、持续时间、Gate 或角色例外；具体稳定语义以对应架构设计、契约和验证入口为准。

## 1. 正式文档分工

元素机制文档按唯一职责分工：

| 文档类型 | 唯一职责 | 不应承载 |
| --- | --- | --- |
| 架构设计 | 状态所有权、领域模型、依赖、流程和不变量 | 版本实施步骤和重复契约字段 |
| 稳定契约 | 稳定 key、字段、公式输入、失败边界、序列化和兼容要求 | 完整设计解释和临时推导 |
| 决策记录 | 已确认的选择、原因、替代方案和冻结结论 | 领域文档的完整副本 |
| 本文（工程规范） | 进入设计、实现、组装和验证的准入条件 | 具体反应数值和机制真值 |

元素反应正式入口为[元素反应系统边界与领域模型](../架构/系统/元素反应/系统边界与领域模型.md)和[元素反应公共模型契约](../契约/元素反应/公共模型契约.md)；本文不维护领域细节。

## 2. 领域所有权与依赖边界

各领域的唯一真值如下：

| 领域 | 唯一拥有 | 明确不拥有 |
| --- | --- | --- |
| `core/elements/` | `Element`、`AuraKind`、精确元素量、主体/来源/Link 等中立语义 | 领域状态、反应公式和数据库数据 |
| Aura | Component、逐来源贡献、元素量投影、衰减、同元素更新、Reaction Link | ICD 窗口、反应候选、伤害和其他领域状态 |
| Aura ICD | Binding、窗口、序列游标和元素施加系数 | Aura 元素量、Reaction Gate、攻击冷却和反应判定 |
| Reaction | Definition、Profile、候选、DecisionSequence、occurrence、ReactionState、Gate、资源和强类型 Effect | Aura 元素量、最终伤害、空间索引和其他领域 Store |
| Damage | Profile、属性读取、公式、中间量和 DamageResult | 反应成立判断、Aura/ICD 状态和反应候选 |
| Coordination | 跨领域证据冻结、计划准备、统一校验、提交边界和事实顺序 | 长期领域状态、领域公式和万能调度 |
| Space、Buff、Shield、Health | 各自领域的实体、状态和公式 | Reaction 的内部状态和跨领域候选顺序 |

`content/` 可以提供类型化 Impact、元素施加意图、ICD Binding、来源观察和队伍能力证据，但不得注册全局 Reaction Definition、拥有 ReactionState 或直接修改 Aura/Reaction Store。

## 3. 稳定身份与精度

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

## 4. 元素交互的标准流程

一次普通元素交互必须经过以下高层阶段：

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

帧规范化、ICD 与元素预算、Aura/Reaction 观察与消费、跨领域提交与事实顺序的具体规则分别由[元素附着系统设计](../架构/系统/元素附着系统设计.md)、[元素附着 ICD 系统设计](../架构/系统/元素附着ICD系统设计.md)、[元素反应系统边界与领域模型](../架构/系统/元素反应/系统边界与领域模型.md)、[元素反应协调器设计](../架构/协调/元素反应协调器设计.md)与对应契约承载。

## 5. Reaction 机制组织

全局反应规则位于 `core/systems/reaction/mechanics/<mechanic_key>/`，并通过显式 bootstrap 注册：

- `ReactionDefinition`、稳定 `reaction_key`、`handler_key`、方向和 Profile 必须在组装阶段完成注册与校验。
- 禁止自动扫描、隐式导入注册或依赖目录顺序决定候选。
- 简单无状态机制可以只保留 `mechanic.py`；复杂机制按真实交互、状态、资源或空间实体拆分。
- 机制目录之间不得互相调用具体 Runtime、Store 或 handler。
- 两个以上机制确实共享且由 Reaction Runtime 拥有的稳定语义，才允许扩展公共模型或候选组件。
- 只有公式相似不足以合并机制目录，也不足以新增公共字段。

Reaction Effect 使用强类型判别联合表达当前 Impact 修正、派生 Damage Impact、元素传播、状态、控制、空间实体和资源变化。Reaction 不直接调用 Damage、Aura、Space、Buff 或 Health Runtime。

## 6. Link、周期和资源状态

凡是 Aura 与 ReactionState、ReactionState 与 Space 实体或 Reaction 与资源共享生命周期，必须把两侧写入放入同一跨领域计划：

- 创建、刷新、消费、到期、来源替换和移除都校验两侧完整最终投影。
- Link 必须成对出现；任何一侧终止都必须原子清理另一侧的 Link 或 binding。
- 周期状态保存游标、`next_required_frame` 和必要的捕获来源观察；周期工作不得伪造新的 occurrence。
- `ScheduledStateTickCause`、`ReactionEffectCause` 和 occurrence cause 必须保持身份语义，不互相冒充。
- Reaction 资源由 Reaction 自己拥有；消费和生产使用资源计划，不能由角色 Content 直接修改 ReactionState。

月反应的 capability、参与者冻结、草露资源、雷暴云、月笼和谐奏等具体字段由对应正式设计与契约拥有；本文只要求它们遵守同样的计划、Link、身份和提交规则。

## 7. Content、组装与失败前置

组装阶段必须显式构造并校验：

- Aura、Aura ICD 和 Reaction 的 Registry。
- Definition、Profile、Binding、Application Profile、Gate、Damage Profile 和 handler 的稳定引用。
- `ReactionEligibilityReadPort`、来源观察、状态计划、scheduled root、Link validator、Space/Damage/Buff/Health adapter。
- 角色 Content 声明的 capability 与生产端口之间的完整映射。
- `ElementalSubjectRef`、来源身份、ReactionState、Aura Link 和空间实体引用的类型一致性。

以下元素接线不完整必须在组装阶段或计划准备阶段报错，不能延迟到仿真运行中才表现为“无反应”：

- Definition、Profile、Binding、Application Profile、Gate、Damage Profile 或 handler 缺失、重复注册或无法唯一选择。
- capability provider 声明支持能力，但对应端口无法准备计划。
- Reaction Effect、状态计划、资源计划或 scheduled root 没有唯一适配器。
- Link、稳定身份、Store version 或最终投影不一致。
- `ElementalSubjectRef`、来源身份、ReactionState、Aura Link 与空间实体引用的类型不一致。

格式正确但业务资格不满足可以返回类型化正常阻止；缺注册、stale plan、身份冲突、不变量破坏和 commit 阶段业务失败必须是技术错误，不能静默降级为无 Aura、无 Reaction 或无 Effect。

## 8. 验收标准

### 8.1 公共能力

新增或修改 Aura、ICD、Reaction 公共能力时，至少覆盖：

- 正常路径、零值、边界帧、帧回退和 required frame。
- 同帧多命中、多目标、稳定排序和虚拟状态可见性。
- 重复 request、operation、work、stale version 和计划 seal 后写入。
- 任一领域计划失败时的批量零提交。
- Link、Gate、资源、周期状态和空间实体的原子生命周期。
- 快照、事实顺序、因果链和 Event 写保护。

### 8.2 具体机制

每个生产 Reaction 至少需要：

- 对应正式架构设计和稳定契约。
- 机制单元测试、跨领域集成测试和至少一个纵向 golden case。
- 正常成立、正常阻止、关键元素量/状态边界和明确技术失败路径。
- 对候选顺序、并行/排他关系、来源观察时点、Gate、周期或派生 Effect 的验证。
- golden 记录来源、初始状态、帧、稳定 key、中间状态、计划结果和预期事实，不能只断言最终伤害数字。

测试通过只证明已覆盖路径满足当前预期，不代表未确认或未覆盖的游戏机制已经实现。

## 9. 扩展准入

新增机制或公共能力前必须说明：

- 现有领域模型无法表达的具体缺口。
- 新状态、公式、资源和身份的唯一所有者。
- 新字段的默认值、校验、序列化和兼容边界。
- 跨领域计划的事务范围、事实顺序和失败语义。
- 至少两个机制是否真实共享拟扩展的公共能力。

尚未形成结论的内容放入明确标记的草案、待确认或临时文档；一旦进入生产契约，应迁入对应架构、契约和测试。

## 10. 关联文档

- [元素附着系统设计](../架构/系统/元素附着系统设计.md)
- [元素附着 ICD 系统设计](../架构/系统/元素附着ICD系统设计.md)
- [元素反应系统边界与领域模型](../架构/系统/元素反应/系统边界与领域模型.md)
- [元素反应公共模型契约](../契约/元素反应/公共模型契约.md)
- [元素反应运行时与事务契约](../契约/元素反应/运行时与事务契约.md)
- [元素反应协调器设计](../架构/协调/元素反应协调器设计.md)
- [伤害系统设计](../架构/系统/伤害系统设计.md)
