# AOS Skills Index

> Auto-generated: 2026-07-11 | Total: 314 files | Source: AST scan + import trace

## Legend

| Status | Meaning |
|--------|---------|
| **USED** | Directly imported by core system (brain.py / hermes / api / web / subagents) |
| **INFRA** | Skill framework infrastructure (registered in package API, not consumed by core yet) |
| **DORMANT** | Never referenced outside own file |
| **ROLE** | Agency role (registered via agency_roles/__init__.py) |

---

## Top-Level Skills (src/skills/*.py) — 44 files

### USED (33) — Core system integration

| Skill | Size | Integration Point |
|-------|------|-------------------|
| \_\_init\_\_.py | 6,394 | brain.py:748, hermes/agent.py:18-19 |
| skill_creator.py | 6,619 | hermes/agent.py:253 |
| find_skills.py | 3,113 | hermes/agent.py:254 |
| superpowers.py | 4,078 | hermes/agent.py:255 |
| j_stack.py | 24,715 | hermes/agent.py:256 |
| frontend_design.py | 16,875 | hermes/agent.py:257 |
| ui_ux_promax.py | 28,360 | hermes/agent.py:258 |
| duckduckgo_search.py | 3,105 | hermes/agent.py:259, api/main.py:236 |
| loop_engineering.py | 17,799 | brain.py:749, api/main.py (4 refs), subagents/, web/app.py |
| vimax.py | 19,244 | brain.py:750, api/main.py (2 refs), subagents/ |
| ruflo.py | 20,849 | brain.py:751, api/main.py (3 refs), subagents/ |
| pixelle_video.py | 15,807 | brain.py:752, api/main.py (3 refs), subagents/ |
| uitars.py | 14,695 | brain.py:759, api/main.py:1230 |
| codebase_memory.py | 25,942 | brain.py:753 |
| searxng.py | 10,773 | brain.py:754 |
| lightrag.py | 15,122 | brain.py:755 |
| jina_reader.py | 18,180 | brain.py:756 |
| ollama.py | 22,166 | brain.py:757 |
| viitor_voice.py | 16,586 | brain.py:758 |
| zvec.py | 18,390 | brain.py:760 |
| llama_cpp.py | 22,828 | brain.py:761 |
| comfyui.py | 23,572 | brain.py:762 |
| codebase_memory_mcp.py | 24,310 | brain.py:763 |
| agency_agents.py | 41,251 | brain.py:764 |
| omni_route.py | 34,620 | brain.py:765 |
| open_montage.py | 29,626 | brain.py:766 |
| video_use.py | 22,475 | brain.py:767 |
| cognee.py | 27,889 | brain.py:768 |
| herdr.py | 23,903 | brain.py:769 |
| design_md.py | 12,144 | brain.py:770 |
| no_mistakes.py | 14,744 | brain.py:771 |
| lingbot_map.py | 13,598 | brain.py:772 |
| sandbox.py | 17,753 | web/app.py:3951 |

### INFRA (9) — Framework infrastructure, not consumed by core

| Skill | Size | Purpose |
|-------|------|---------|
| template.py | 4,700 | SkillTemplate, StageSpec, ToolSpec, TestCase |
| factory.py | 8,812 | SkillFactory, TemplateSkill — creation pipeline |
| adapter.py | 10,288 | SkillAdapter, AdapterRegistry — env adaptation |
| versioning.py | 10,702 | SkillVersionManager, SnapshotManager |
| composition.py | 10,926 | SkillCompositionEngine, SkillPipeline |
| learning.py | 10,527 | SkillLearningSystem, FeedbackRecord |
| marketplace.py | 11,312 | SkillMarketplace, SkillImporter |
| monitoring.py | 10,365 | SkillMonitor, SkillSpan, SkillMetric |
| engineering.py | 13,149 | EngineeringSkill, CodeQualityChecker |

> These 9 modules form a rich skill management infrastructure (versioning, composition, marketplace, monitoring, learning) that is fully wired into the skills package API but has no consumers in the core system yet. They represent **built-but-not-yet-integrated capabilities**.

### DORMANT (2) — Never referenced outside own file

| Skill | Size | Notes |
|-------|------|-------|
| safe_eval.py | 3,041 | Only imported by factory.py (security-motivated separation) |
| cli_helpers.py | 1,944 | Completely orphaned — skipped by skills_bridge.py, not in __init__.py |

---

## Agency Roles (src/skills/agency_roles/) — 270 files

### Framework (1)

| File | Purpose |
|------|---------|
| \_\_init\_\_.py | Static imports (269 roles) + lazy loading + register_agency_roles() |

### Internal Utility (1)

| File | Used By |
|------|---------|
| agent_tools.py | 短视频剪辑指导师.py (ToolBox) |

### Registered Roles (265)

All 265 role files are statically imported in `__init__.py` and registered via `register_agency_roles()`. They span 26 domains: humanities, engineering, finance, gaming, GIS, marketing, security, XR/AR, and more.

> No dormant roles found. All roles are actively registered. Runtime usage data (which roles are actually invoked during conversations) is not available — collecting this would require instrumentation at the SkillRegistry.execute() level.

---

## Summary

| Category | Count | % |
|----------|-------|---|
| USED by core system | 34 | 10.8% |
| INFRA (built, not consumed) | 9 | 2.9% |
| DORMANT | 2 | 0.6% |
| ROLE (registered) | 266 | 84.7% |
| Framework | 3 | 1.0% |
| **Total** | **314** | **100%** |

### Key Observations

1. **Very low dormancy rate** (0.6%) — the codebase is well-connected
2. **265 agency roles are all registered** but runtime invocation data is unknown
3. **9 INFRA modules** represent unrealized capability — they could be activated when core system needs versioning/composition/marketplace/monitoring
4. **cli_helpers.py** is the only truly orphaned file — safe to remove or integrate
5. **Three integration points** drive skill usage: hermes/agent.py (7 meta skills), brain.py (20 domain skills), brain_registration.py (265 agency roles)
