# 元素附着 ICD 系统设计

> 状态：生效
> 实现覆盖：Definition Registry、精确系数序列、攻击者与目标隔离、固定窗口、批量虚拟计划、版本化提交和稳定快照。真实角色完整 ICD 数据仍属于 content 数据迁移范围。

最后更新：2026-08-02

## 1. 系统定位

`core/systems/aura_icd/` 是元素附着冷却领域。它在一次命中进入 Aura 之前，根据攻击者共享作用域、目标、标签和 Definition 解析本次元素施加系数。

Aura ICD 只回答：

```text
本次命中使用哪个序列位置
-> 得到多少元素施加系数
-> 窗口和游标如何推进
```

它不拥有：

- 元素战技或元素爆发冷却。
- 攻击触发间隔和协同攻击频率。
- Reaction Damage Gate、成立 Gate 或环境反应间隔。
- Aura 当前元素量、衰减、同元素叠加或 Reaction 语义。
- 角色、武器和技能的具体 Binding 数据。

因此目录使用 `aura_icd`，不建立含义过宽的通用 `icd` Store。

## 2. 代码组织与状态所有权

当前目录结构为：

```text
core/systems/aura_icd/
├── __init__.py
├── enums.py
├── models.py
└── runtime.py
```

- `enums.py` 保存 `IcdOutcome`。
- `models.py` 保存 Definition、Registry、Binding、Key、请求、Record、决议、计划、回执和快照。
- `runtime.py` 保存 `AuraIcdBatchPlanner`、`AuraIcdRuntime`、默认 Definition 和冲突错误。

当前没有独立 Resolver、Store 或 Snapshot serializer 文件。`AuraIcdRuntime` 内置 Record 索引、版本、规范化帧和幂等身份，是该领域唯一状态所有者和写入口。

## 3. Definition 与 Registry

`IcdDefinition` 保存：

```text
definition_key
reset_interval_frames
application_sequence: tuple[AuraAmount, ...]
```

规则：

- `definition_key` 是稳定代码 key，不使用显示名称绑定行为。
- `reset_interval_frames` 是正整数帧数。
- `application_sequence` 非空，元素为精确且非负的 `AuraAmount`。
- 序列位置可以返回 `0`、`1` 或其他精确系数。
- 游标超过序列末尾后持续使用最后一个系数，不循环。

`IcdDefinitionRegistry` 在组装时注册 Definition，拒绝重复 key 和缺失引用。生产组装完成后把 Registry 视为只读，不在仿真过程中动态注册或从网络、SQLite 读取 Definition。

默认 Definition：

- `icd.standard`：150 帧窗口，有限的 `1, 0, 0` 重复序列；有限序列结束后保持末尾 `0`，直到窗口重置。
- `icd.none`：可显式绑定的无冷却 Definition。
- 无 Binding：直接返回系数 `1` 和 `NO_COOLDOWN`，不创建 Record。

## 4. Binding 与共享身份

`IcdBinding` 保存：

```text
label_key
definition_key
```

`label_key` 表达一组命中是否共享同一游标，`definition_key` 选择窗口与系数序列。具体攻击由 content 绑定稳定 key，运行时不根据技能显示名称推断。

`AuraIcdAttackerRef.scope_key` 表达攻击者共享作用域。content 可以让同一角色的多个命中共享，也可以让创建物或独立实例使用不同作用域。共享规则必须显式声明，不能由 Aura ICD 沿创建者链猜测。

运行态主键为：

```text
IcdKey
├── attacker_ref
├── defender_ref
├── label_key
└── definition_key
```

因此以下维度默认隔离：

- 不同攻击者作用域。
- 不同目标。
- 不同 label。
- 不同 Definition。

同一范围 Impact 的多个目标会形成不同 IcdKey，但仍使用同一个范围级 `impact_ref` 进行因果审计。

## 5. 请求与决议

`IcdImpactRequest` 至少保存：

```text
request_id
impact_ref
frame
order
attacker_ref
defender_ref
binding?
```

`request_id` 用于幂等，`order` 固定同一 batch 内的命中顺序，`impact_ref` 关联同一次 Impact。Aura ICD 不读取攻击元素、基础元素量或伤害字段；即使命中最终没有元素施加，只要存在 Binding，游标仍按命中推进。

`IcdResolution` 保存：

- 请求、Impact、帧和顺序。
- 攻击者、目标、label 和 Definition。
- `IcdOutcome` 与实际使用的 sequence index。
- 精确 `coefficient`。
- 窗口开始帧与重置帧。

`allows_application` 只是 `coefficient != 0` 的只读投影。它不表示一定形成 Aura 或 Reaction；后续流程仍可能因元素量、Aura Profile 或其他领域校验失败。

## 6. Record 与解析算法

`IcdRecord` 保存：

```text
key
window_started_frame
resets_at_frame
next_sequence_index
last_hit_frame
revision
```

无 Binding：

```text
coefficient = 1
outcome = NO_COOLDOWN
不创建 Record
```

有 Binding 且没有活动 Record：

```text
sequence_index = 0
coefficient = sequence[0]
window_started_frame = frame
resets_at_frame = frame + reset_interval_frames
next_sequence_index = 1
outcome = WINDOW_STARTED
```

有活动 Record：

```text
sequence_index = min(next_sequence_index, len(sequence) - 1)
coefficient = sequence[sequence_index]
next_sequence_index = min(sequence_index + 1, len(sequence))
outcome = SEQUENCE_RESOLVED
```

每次符合 Binding 的命中都会更新 `last_hit_frame`、推进游标并增加 revision，包括系数为零和不携带元素的命中。命中不会延长 `resets_at_frame`；窗口始终从第一次命中计算。

## 7. 时间语义

`AuraIcdRuntime.update_frame()` 先拒绝帧回退，再删除满足以下条件的 Record：

```text
resets_at_frame <= frame
```

因此窗口是半开区间：

```text
window_started_frame <= frame < resets_at_frame
```

`frame == resets_at_frame` 时旧 Record 已失效，下一次命中从序列位置 `0` 重新开始。重复规范化同一帧无副作用。

活动 ICD 窗口不会单独延长仿真，`AuraIcdRuntime.is_idle()` 始终返回 true。只有其他领域需要推进时间时，ICD 才随帧规范化自然清理。

## 8. Batch Planner 与提交

生产元素流程使用 `AuraIcdBatchPlanner`：

```text
AuraIcdRuntime.begin_batch(frame, batch_id)
-> Planner.prepare(request)
-> Planner.seal()
-> IcdMutationPlan
-> AuraIcdRuntime.validate(plan)
-> AuraIcdRuntime.commit_prevalidated(plan)
```

Planner 在工作副本上依次解析请求。后一个命中读取前一个命中形成的虚拟 Record，因此同帧多命中和多目标顺序确定，真实 Runtime 在 commit 前保持不变。

`IcdMutationPlan` 保存：

- 稳定 `operation_id` 和计划帧。
- request identity 集合。
- batch 开始时的 Store version。
- 完整 Record 后值投影与删除 key。
- 按 order 排序的决议。

校验拒绝 stale version、重复 operation、重复 request、错误计划帧，以及 Planner 内重复 request/order 或 seal 后写入。只有 Record 投影实际变化时 Runtime version 才增加；无 Binding 的请求仍记录 operation/request 幂等身份。

## 9. 与 Aura 和 Reaction 的协调

跨系统顺序为：

```text
Impact
-> Aura ICD 解析精确系数
-> 计算 ICD 后元素预算
-> Aura Planner 提供虚拟 AuraView
-> Reaction Planner 判定
-> Aura Planner 执行普通附着或精确消费
-> 所有计划统一校验
-> 无回调提交
-> 发布事实
```

系数为零时：

- ICD 游标仍提交。
- 不创建普通 Aura 请求。
- 不触发依赖正入射元素量的普通元素反应。
- `strike_type` 等独立强类型证据仍可进入状态型 Reaction。

系数为正时，Aura 使用基础元素量与系数得到精确原始量。非标准正结果必须由已注册 Aura Application Profile 或显式精确衰减档案支持；不能由 ICD 自行选择近似 AuraStrength。

Aura、Reaction 或其他同批计划失败时，ICD 也不能单独提交。ICD 不访问 Aura/Reaction Runtime，也不感知最终伤害或反应结果。

## 10. Content 与组装

content 负责声明：

- 具体攻击使用的 `IcdBinding`。
- 可共享或隔离的 `AuraIcdAttackerRef`。
- Definition 与 label 的稳定 key。
- 攻击基础元素量和对应 Aura Application Profile。

组装阶段必须校验：

- Definition key 唯一。
- Binding 引用存在。
- 窗口为正整数，序列非空。
- 可能产生的正系数结果存在可解析的 Aura Profile。
- 共享作用域、label 和具体内容绑定没有自相矛盾。

运行时不访问 Wiki、SQLite、application 服务或远程数据。真实角色完整 ICD 表属于 content 和资产数据迁移，不改变 Runtime 契约。

## 11. 事实、快照与错误

Aura ICD 决议通过 `AURA_ICD_RESOLVED` 事实审计。Runtime 本身只返回计划与提交回执；生产协调器在完整跨领域提交后按 interaction order 发布事实。

`IcdSnapshot` 保存规范化帧和稳定排序的活动 Record。排序键由攻击者作用域、目标 kind/id、label 和 Definition 组成。Snapshot 不保存 Definition 副本，也不形成第二份状态真值。

以下情况必须显式失败：

- 非法 Definition、空序列或非法窗口。
- Binding 引用未注册 Definition。
- 非法攻击者、目标、request 或 Impact identity。
- 请求帧未规范化或帧回退。
- 重复 request、order、operation。
- stale Store version。
- 正系数结果没有可用 Aura Profile。

批量失败不能留下部分游标推进。

## 12. 当前边界与验证入口

当前正式实现不包含完整角色、敌人和环境 ICD 数据，也不定义攻击触发冷却、Reaction Gate 或结果库 schema。这些是内容和外围契约边界，不是 Aura ICD 状态机的未完成分支。

验证入口：

- `tests/unit/core/systems/aura_icd/test_icd_runtime.py`
- `tests/unit/core/coordination/elemental_reaction/`
- `tests/golden/reactions/test_elemental_pipeline.py`
- 各具体反应的纵向 golden case

Aura 状态与精确衰减见[元素附着系统设计](./元素附着系统设计.md)，跨领域事务见[元素反应协调器设计](../协调/元素反应协调器设计.md)，机制真值规则见[元素附着、ICD 与反应设计规范](../../工程/元素附着、ICD与反应设计规范.md)。
