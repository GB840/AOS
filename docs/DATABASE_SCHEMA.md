# AOS v5.0 数据库 Schema（42 张表 · 单一真相层）

> 本文件由 `scripts/gen_schema_doc.py` 从 `src/core/database/models/*.py` 的 SQLModel 定义**自动内省**生成，与代码严格一致，修改模型后重跑脚本即可更新，不会漂移。

AOS 全部结构化状态存于**单一 SQLite 数据库**（`config.SQLITE_DB_PATH`，WAL 模式，并开启外键约束），是系统唯一真相来源。全文检索（FTS5）由 `memory` 层的虚拟表提供，不计入下方 42 张 ORM 表。

**表总数：42**

分层与 `README` 的架构叙事一致：
- **基础设施层 (infra)**
- **生态层 (ecosystem)**
- **进化层 (evolution)**
- **经济层 (economy)**
- **免疫层 (immune)**

## 基础设施层 (infra)

### `users` — `User`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| username | TEXT | Y |  |  |  |
| display_name | TEXT | Y |  |  |  |
| role | TEXT | Y |  |  | server_default='operator' |
| is_active | BOOLEAN | Y |  |  | server_default=TRUE |

### `agents` — `Agent`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  |  |  |
| name | TEXT | Y |  |  |  |
| kind | TEXT | Y |  |  | server_default='core' |
| status | TEXT | Y |  |  | server_default='inactive' |
| endpoint | TEXT | Y |  |  |  |
| config_json | TEXT | Y |  |  | server_default='{}' |

### `threads` — `Thread`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| thread_id | TEXT | N | Y |  |  |
| title | TEXT | Y |  |  |  |
| metadata | TEXT | Y |  |  | server_default='{}' |

### `messages` — `Message`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| thread_id | TEXT | Y |  | threads.thread_id |  |
| role | TEXT | Y |  |  |  |
| content | TEXT | N |  |  |  |
| tool_calls | TEXT | Y |  |  |  |

### `checkpoints` — `Checkpoint`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| thread_id | TEXT | N | Y |  |  |
| checkpoint_ns | TEXT | N | Y |  |  |
| checkpoint_id | TEXT | N | Y |  |  |
| parent_checkpoint_id | TEXT | Y |  |  |  |
| type | TEXT | Y |  |  |  |
| checkpoint | BLOB | N |  |  |  |
| metadata | TEXT | Y |  |  | server_default='{}' |

### `conversations` — `Conversation`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| session_id | TEXT | Y |  |  |  |
| role | TEXT | N |  |  |  |
| content | TEXT | N |  |  |  |
| metadata | TEXT | Y |  |  | server_default='{}' |

### `knowledge` — `Knowledge`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| title | TEXT | N |  |  |  |
| content | TEXT | N |  |  |  |
| source | TEXT | Y |  |  | server_default='' |
| tags | TEXT | Y |  |  | server_default='[]' |
| metadata | TEXT | Y |  |  | server_default='{}' |

### `tasks` — `Task`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | TEXT | N | Y |  |  |
| type | TEXT | N |  |  |  |
| status | TEXT | Y |  |  | server_default='pending' |
| input | TEXT | Y |  |  | server_default='{}' |
| output | TEXT | Y |  |  | server_default='{}' |
| error | TEXT | Y |  |  | server_default='' |

### `audit_log` — `AuditLog`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| event_type | TEXT | N |  |  |  |
| user_id | TEXT | Y |  |  | server_default='system' |
| agent_id | TEXT | Y |  |  | server_default='' |
| details | TEXT | Y |  |  | server_default='{}' |
| timestamp | TEXT | Y |  |  | server_default=CURRENT_TIMESTAMP |

### `notifications` — `Notification`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| channel | TEXT | Y |  |  | server_default='in_app' |
| payload_json | TEXT | Y |  |  | server_default='{}' |
| read | BOOLEAN | Y |  |  | server_default=FALSE |

### `event_store` — `EventStore`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| aggregate_type | TEXT | Y |  |  |  |
| aggregate_id | TEXT | Y |  |  |  |
| seq | INTEGER | Y |  |  | server_default='0' |
| event_type | TEXT | Y |  |  |  |
| payload_json | TEXT | Y |  |  | server_default='{}' |

### `snapshots` — `Snapshot`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| aggregate_type | TEXT | Y |  |  |  |
| aggregate_id | TEXT | Y |  |  |  |
| version | INTEGER | Y |  |  | server_default='0' |
| state_json | TEXT | Y |  |  | server_default='{}' |

### `cold_memories` — `ColdMemory`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| original_id | TEXT | Y |  |  |  |
| kind | TEXT | Y |  |  | server_default='conversation' |
| data_blob | BLOB | N |  |  |  |
| encoding | TEXT | Y |  |  | server_default='zlib' |

## 生态层 (ecosystem)

### `skills` — `Skill`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| name | TEXT | Y |  |  |  |
| version | TEXT | Y |  |  | server_default='0.1.0' |
| kind | TEXT | Y |  |  | server_default='python' |
| entry | TEXT | Y |  |  |  |
| description | TEXT | Y |  |  |  |
| enabled | BOOLEAN | Y |  |  | server_default=TRUE |

### `skill_versions` — `SkillVersion`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| skill_id | INTEGER | Y |  | skills.id |  |
| version | TEXT | N |  |  |  |
| changelog | TEXT | Y |  |  |  |
| artifact_path | TEXT | Y |  |  |  |

### `tool_registry` — `ToolRegistry`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| name | TEXT | Y |  |  |  |
| kind | TEXT | Y |  |  | server_default='function' |
| entry | TEXT | Y |  |  |  |
| schema_json | TEXT | Y |  |  | server_default='{}' |
| enabled | BOOLEAN | Y |  |  | server_default=TRUE |

### `mcp_connectors` — `McpConnector`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| name | TEXT | Y |  |  |  |
| transport | TEXT | Y |  |  | server_default='stdio' |
| endpoint | TEXT | Y |  |  |  |
| status | TEXT | Y |  |  | server_default='disconnected' |
| config_json | TEXT | Y |  |  | server_default='{}' |

### `agent_cards` — `AgentCard`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| strategy_json | TEXT | Y |  |  | server_default='{}' |
| model_draft | TEXT | Y |  |  |  |
| model_final | TEXT | Y |  |  |  |

### `subagent_registry` — `SubagentRegistry`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| display_name | TEXT | Y |  |  |  |
| capabilities | TEXT | Y |  |  | server_default='[]' |

### `knowledge_graph_nodes` — `KnowledgeGraphNode`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| label | TEXT | Y |  |  |  |
| type | TEXT | Y |  |  |  |
| properties_json | TEXT | Y |  |  | server_default='{}' |

### `knowledge_graph_edges` — `KnowledgeGraphEdge`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| from_node_id | INTEGER | Y |  | knowledge_graph_nodes.id |  |
| to_node_id | INTEGER | Y |  | knowledge_graph_nodes.id |  |
| relation | TEXT | Y |  |  |  |
| weight | FLOAT | Y |  |  | server_default='1.0' |

### `agency_roles` — `AgencyRole`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| role_name | TEXT | Y |  |  |  |
| description | TEXT | Y |  |  |  |
| permissions_json | TEXT | Y |  |  | server_default='{}' |

### `capability_registry` — `CapabilityRegistry`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| name | TEXT | Y |  |  |  |
| description | TEXT | Y |  |  |  |
| owner_agent_id | TEXT | Y |  | agents.agent_id |  |

## 进化层 (evolution)

### `task_fingerprints` — `TaskFingerprint`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| fingerprint_hash | TEXT | Y |  |  |  |
| intent_summary | TEXT | Y |  |  |  |
| template_json | TEXT | Y |  |  | server_default='{}' |
| hit_count | INTEGER | Y |  |  | server_default='0' |

### `orchestration_specs` — `OrchestrationSpec`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| spec_name | TEXT | Y |  |  |  |
| spec_json | TEXT | Y |  |  | server_default='{}' |
| auto_generated | BOOLEAN | Y |  |  | server_default=TRUE |

### `workflow_definitions` — `WorkflowDefinition`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| skill_id | INTEGER | Y |  | skills.id |  |
| name | TEXT | Y |  |  |  |
| dag_json | TEXT | Y |  |  | server_default='{}' |
| enabled | BOOLEAN | Y |  |  | server_default=TRUE |

### `evolution_log` — `EvolutionLog`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| layer | TEXT | Y |  |  | server_default='L1' |
| event_type | TEXT | Y |  |  |  |
| from_version | TEXT | Y |  |  |  |
| to_version | TEXT | Y |  |  |  |
| payload_json | TEXT | Y |  |  | server_default='{}' |

### `learning_experiences` — `LearningExperience`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| task_fingerprint_id | INTEGER | Y |  | task_fingerprints.id |  |
| outcome | TEXT | Y |  |  | server_default='success' |
| reward | FLOAT | Y |  |  | server_default='0.0' |
| experience_json | TEXT | Y |  |  | server_default='{}' |

### `model_routing_history` — `ModelRoutingHistory`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| task_id | TEXT | Y |  | tasks.id |  |
| requested_capability | TEXT | Y |  |  |  |
| selected_model | TEXT | Y |  |  |  |
| fallback_used | BOOLEAN | Y |  |  | server_default=FALSE |
| latency_ms | INTEGER | Y |  |  |  |

### `performance_metrics` — `PerformanceMetric`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| component | TEXT | Y |  |  |  |
| metric_name | TEXT | Y |  |  |  |
| metric_value | FLOAT | Y |  |  | server_default='0.0' |
| metadata | TEXT | Y |  |  | server_default='{}' |

### `prompt_templates` — `PromptTemplate`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| name | TEXT | Y |  |  |  |
| template | TEXT | N |  |  |  |
| version | TEXT | Y |  |  | server_default='1' |

### `negotiation_sessions` — `NegotiationSession`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| initiator_agent_id | TEXT | Y |  | agents.agent_id |  |
| role_assignment_json | TEXT | Y |  |  | server_default='{}' |
| status | TEXT | Y |  |  | server_default='open' |

### `self_modification_proposals` — `SelfModificationProposal`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| proposer_agent_id | TEXT | Y |  | agents.agent_id |  |
| target | TEXT | Y |  |  |  |
| rationale | TEXT | Y |  |  |  |
| diff_json | TEXT | Y |  |  | server_default='{}' |
| status | TEXT | Y |  |  | server_default='proposed' |

## 经济层 (economy)

### `token_ledger` — `TokenLedger`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| task_id | TEXT | Y |  | tasks.id |  |
| model | TEXT | Y |  |  |  |
| prompt_tokens | INTEGER | Y |  |  | server_default='0' |
| completion_tokens | INTEGER | Y |  |  | server_default='0' |
| cost_usd | FLOAT | Y |  |  | server_default='0.0' |

### `cost_accounting` — `CostAccounting`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| task_id | TEXT | Y |  | tasks.id |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| total_cost_usd | FLOAT | Y |  |  | server_default='0.0' |
| currency | TEXT | Y |  |  | server_default='USD' |
| metadata | TEXT | Y |  |  | server_default='{}' |

### `reward_events` — `RewardEvent`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| task_id | TEXT | Y |  | tasks.id |  |
| amount | FLOAT | Y |  |  | server_default='0.0' |
| reason | TEXT | Y |  |  |  |
| kind | TEXT | Y |  |  | server_default='quality' |

### `budget_pools` — `BudgetPool`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| owner_agent_id | TEXT | Y |  | agents.agent_id |  |
| name | TEXT | Y |  |  |  |
| total_budget_usd | FLOAT | Y |  |  | server_default='0.0' |
| used_usd | FLOAT | Y |  |  | server_default='0.0' |
| period | TEXT | Y |  |  | server_default='monthly' |

### `economic_transactions` — `EconomicTransaction`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| budget_pool_id | INTEGER | Y |  | budget_pools.id |  |
| tx_type | TEXT | Y |  |  |  |
| amount_usd | FLOAT | Y |  |  | server_default='0.0' |
| memo | TEXT | Y |  |  |  |

## 免疫层 (immune)

### `compliance_records` — `ComplianceRecord`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| standard | TEXT | Y |  |  |  |
| check_name | TEXT | Y |  |  |  |
| passed | BOOLEAN | Y |  |  | server_default=TRUE |
| detail_json | TEXT | Y |  |  | server_default='{}' |

### `identity_vault` — `IdentityVault`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| aid | TEXT | Y |  |  |  |
| public_key | TEXT | Y |  |  |  |
| attestation_json | TEXT | Y |  |  | server_default='{}' |

### `semantic_firewall_rules` — `SemanticFirewallRule`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| name | TEXT | Y |  |  |  |
| category | TEXT | Y |  |  | server_default='injection' |
| pattern | TEXT | N |  |  |  |
| action | TEXT | Y |  |  | server_default='block' |
| enabled | BOOLEAN | Y |  |  | server_default=TRUE |

### `sandbox_policies` — `SandboxPolicy`

| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |
|---|---|---|---|---|---|
| created_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| updated_at | DATETIME | N |  |  | default=factory; server_default=CURRENT_TIMESTAMP |
| id | INTEGER | N | Y |  |  |
| agent_id | TEXT | Y |  | agents.agent_id |  |
| allowed_tools | TEXT | Y |  |  | server_default='[]' |
| denied_paths | TEXT | Y |  |  | server_default='[]' |
| max_execution_seconds | INTEGER | Y |  |  | server_default='300' |
| policy_json | TEXT | Y |  |  | server_default='{}' |
