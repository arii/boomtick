# Changelog

## [0.21.0](https://github.com/arii/boomtick/compare/cli-v0.20.2...cli-v0.21.0) (2026-11-14)


### Features

* add LangGraph.js workflows package with run_workflow MCP gateway ([#1263](https://github.com/arii/boomtick/issues/1263)) ([ad3b686](https://github.com/arii/boomtick/commit/ad3b68612750e2d39e6d65ebcff6aad650112e91))
* consolidate MCP tool surface with typed schemas and explicit modes ([#1259](https://github.com/arii/boomtick/issues/1259)) ([5a4d93c](https://github.com/arii/boomtick/commit/5a4d93c7f280e2862bfb383b1c5166cf0becec44))


### Bug Fixes

* audit batch [#1231](https://github.com/arii/boomtick/issues/1231) [#1232](https://github.com/arii/boomtick/issues/1232) [#1233](https://github.com/arii/boomtick/issues/1233) [#1234](https://github.com/arii/boomtick/issues/1234) [#1235](https://github.com/arii/boomtick/issues/1235) + [#1236](https://github.com/arii/boomtick/issues/1236) verified cuts ([#1237](https://github.com/arii/boomtick/issues/1237)) ([4a200e4](https://github.com/arii/boomtick/commit/4a200e44875c2b55e93e3ced05f87480dc87f245))
* repair the two failing optional CI jobs (preflight test on py3.14, verify:schemas venv) ([#1266](https://github.com/arii/boomtick/issues/1266)) ([8d15065](https://github.com/arii/boomtick/commit/8d150656f82e8552a9d1b75219dc90f65e5d27e9))

## [0.20.2](https://github.com/arii/boomtick/compare/cli-v0.20.1...cli-v0.20.2) (2026-11-08)


### Bug Fixes

* cwd-independent verify-scope test paths (closes [#1217](https://github.com/arii/boomtick/issues/1217)) ([#1221](https://github.com/arii/boomtick/issues/1221)) ([178a2a3](https://github.com/arii/boomtick/commit/178a2a3f1369f49578a67947b8883a938bdf1173))
* declare RAG backend deps (chromadb + sentence-transformers) ([#1212](https://github.com/arii/boomtick/issues/1212)) ([037c8fc](https://github.com/arii/boomtick/commit/037c8fcb1b3ca182194c600118ae9d7a35ac01ef))
* fail loud on repo-resolve and sessions-unknown gate + provider scorecard ([#1216](https://github.com/arii/boomtick/issues/1216)) ([1aae0ba](https://github.com/arii/boomtick/commit/1aae0ba3a90270eb330c28396bebdd825649f78f))
* mark audit downgrades loudly (closes [#1215](https://github.com/arii/boomtick/issues/1215)) ([#1220](https://github.com/arii/boomtick/issues/1220)) ([051c5db](https://github.com/arii/boomtick/commit/051c5db057363cc5221a262c5a79cb8b433f5840))
* python best-practices batch (td_cli guard, f-strings, dead code, availability probe) ([#1219](https://github.com/arii/boomtick/issues/1219)) ([c76b009](https://github.com/arii/boomtick/commit/c76b009fe31c4a966390854b2f84b09a868b81cc))
* RAG backend skew from transitive OTEL pins ([#1207](https://github.com/arii/boomtick/issues/1207)) ([f6691bd](https://github.com/arii/boomtick/commit/f6691bd72945bd8f9d9baf0a8f09ce09c94dad17))
* scope gate bypass window (closes [#1206](https://github.com/arii/boomtick/issues/1206)) ([#1209](https://github.com/arii/boomtick/issues/1209)) ([6f7e841](https://github.com/arii/boomtick/commit/6f7e8417d6317987f3fc48139f36541b0e9df1e4))
* scope probe single range, fail closed (no retry) ([#1214](https://github.com/arii/boomtick/issues/1214)) ([002eeeb](https://github.com/arii/boomtick/commit/002eeeb44e8b5413bad044ef91ebfa039cfa54e3))

## [0.20.1](https://github.com/arii/boomtick/compare/cli-v0.20.0...cli-v0.20.1) (2026-11-08)


### Bug Fixes

* **rag:** fail loud on unverified empty index in incremental path ([#1199](https://github.com/arii/boomtick/issues/1199)) ([7beb5e4](https://github.com/arii/boomtick/commit/7beb5e4154af872c89f4959b1fdf8ad40cb983cd))
* **tests:** gate RAG backend tests on real import, not find_spec ([#1193](https://github.com/arii/boomtick/issues/1193)) ([fc53afd](https://github.com/arii/boomtick/commit/fc53afd4fbfd0e42b6bca376322e6e799832e21e))

## [0.20.0](https://github.com/arii/boomtick/compare/cli-v0.19.3...cli-v0.20.0) (2026-11-06)


### Features

* mega rollup — close [#1142](https://github.com/arii/boomtick/issues/1142), [#1143](https://github.com/arii/boomtick/issues/1143), [#1139](https://github.com/arii/boomtick/issues/1139), [#1140](https://github.com/arii/boomtick/issues/1140) ([#1154](https://github.com/arii/boomtick/issues/1154)) ([f409dbc](https://github.com/arii/boomtick/commit/f409dbc91076be0ea4903ae6d45c0e8bdd8a2957))

## [0.19.3](https://github.com/arii/boomtick/compare/cli-v0.19.2...cli-v0.19.3) (2026-11-06)


### Bug Fixes

* **cli:** validate-issue passes mixed-case paths and existing dirs ([#1147](https://github.com/arii/boomtick/issues/1147)) ([c61e647](https://github.com/arii/boomtick/commit/c61e647cac7b61f7335ab0512877b6aecb3ece18))

## [0.19.2](https://github.com/arii/boomtick/compare/cli-v0.19.1...cli-v0.19.2) (2026-11-05)


### Bug Fixes

* **review:** ground Tailwind rule, cite hunks, drop AI naming ([#1114](https://github.com/arii/boomtick/issues/1114)) ([9c905f7](https://github.com/arii/boomtick/commit/9c905f7a92064078cb8af3e1a4a0477229c6a7ea))

## [0.19.1](https://github.com/arii/boomtick/compare/cli-v0.19.0...cli-v0.19.1) (2026-11-03)


### Bug Fixes

* **td:** valid GraphQL label resolution (drop bogus names: arg) ([#1109](https://github.com/arii/boomtick/issues/1109)) ([dd1a479](https://github.com/arii/boomtick/commit/dd1a4797fe9a8097067452053cf924b299fcc17b))

## [0.19.0](https://github.com/arii/boomtick/compare/cli-v0.18.0...cli-v0.19.0) (2026-11-03)


### Features

* **cli:** local session parity — td agent run, session, skill ([#1102](https://github.com/arii/boomtick/issues/1102)) ([aa2e473](https://github.com/arii/boomtick/commit/aa2e47345bde1da4aa3be8685a7d010e8d2a9a63))
* **mcp:** adopt pre-existing worktree schemas for lifecycle tools ([cbc0537](https://github.com/arii/boomtick/commit/cbc0537a2f1d8b9855154d883953b310356d1ca9))
* **mcp:** agent_merge_approved → agent_submit_pr (no agent merge authority) ([#1105](https://github.com/arii/boomtick/issues/1105)) ([71d8393](https://github.com/arii/boomtick/commit/71d8393fe0b90a00113af9cba908f830c7ae4398))
* **mcp:** skill_list/skill_read session tools ([#1101](https://github.com/arii/boomtick/issues/1101)) ([b9aeb67](https://github.com/arii/boomtick/commit/b9aeb671d0025b8452497045cb939d7969042036))
* **mcp:** worktree_create/list/remove session tools ([66e05c3](https://github.com/arii/boomtick/commit/66e05c350b47e118926720e183723a9563f2f473))


### Bug Fixes

* **cli:** pin token presence in dispatch precheck tests ([2876d0d](https://github.com/arii/boomtick/commit/2876d0df5bfa7590ec3c318ddf58cedc4e47891d))
* **cli:** skip commands-schema write outside boomtick checkout ([573b25f](https://github.com/arii/boomtick/commit/573b25f5898fd18a1370202315ef00a95fcb10f5))
* **cli:** skip commands-schema write outside boomtick checkout ([#1094](https://github.com/arii/boomtick/issues/1094)) ([7906717](https://github.com/arii/boomtick/commit/79067178ba6e5c992bf428a5095638e8dbee8987))
* **cli:** skip Jules branch precheck without GitHub token ([b986681](https://github.com/arii/boomtick/commit/b98668104392779d8d8343a0bd3436e0d3ff182a))
* **cli:** skip Jules branch precheck without GitHub token ([#1087](https://github.com/arii/boomtick/issues/1087)) ([316f8cb](https://github.com/arii/boomtick/commit/316f8cbda9e152ec9ce6bfd55e957e3ef4a29e38))

## [0.18.0](https://github.com/arii/boomtick/compare/cli-v0.17.1...cli-v0.18.0) (2026-11-02)


### Features

* **cli:** add td gh pr-view and run-jobs commands ([a6100d7](https://github.com/arii/boomtick/commit/a6100d7d19e849892cd4120aa5020474a8fe3d40)), closes [#1082](https://github.com/arii/boomtick/issues/1082) [#1083](https://github.com/arii/boomtick/issues/1083)
* **cli:** add td gh pr-view and run-jobs commands ([#1085](https://github.com/arii/boomtick/issues/1085)) ([64bc1c4](https://github.com/arii/boomtick/commit/64bc1c484503fec98bc840f5ae5d1d2b883c7062))
* **cli:** deep-agent track td-parity ([#1080](https://github.com/arii/boomtick/issues/1080)) ([361c178](https://github.com/arii/boomtick/commit/361c178b1b4cca4f040211562375895e3d8d9c65))

## [0.17.1](https://github.com/arii/boomtick/compare/cli-v0.17.0...cli-v0.17.1) (2026-11-02)


### Bug Fixes

* **schemas:** gitignore generated schemas, clean regen + tracked hooks ([#1076](https://github.com/arii/boomtick/issues/1076)) ([bd14054](https://github.com/arii/boomtick/commit/bd140545a30148731c697bc67e78a1062c24f150))

## [0.17.0](https://github.com/arii/boomtick/compare/cli-v0.16.0...cli-v0.17.0) (2026-11-02)


### Features

* **daemon:** autonomous multi-repo triage daemon ([#1059](https://github.com/arii/boomtick/issues/1059)) ([ddcc4c8](https://github.com/arii/boomtick/commit/ddcc4c85d8ecbbd88a073cc27c8ebba8119459d7))


### Bug Fixes

* **td:** stop build-repo-context clobbering cli-schema.json ([#1069](https://github.com/arii/boomtick/issues/1069)) ([ecf952e](https://github.com/arii/boomtick/commit/ecf952e0b853b2fe7e92386d8f51d67d7c599f43))
* **td:** tag detect-conflicts output as file overlap, not merge conflicts ([#1067](https://github.com/arii/boomtick/issues/1067)) ([4ed880d](https://github.com/arii/boomtick/commit/4ed880d8bbdf1d59e95e92607f59640a28c10a86))

## [0.16.0](https://github.com/arii/boomtick/compare/cli-v0.15.2...cli-v0.16.0) (2026-11-02)


### Features

* **contract:** machine-readable front-matter in AGENT_CONTRACT.md with shared dependency caching ([c5a4790](https://github.com/arii/boomtick/commit/c5a479065f9817279f4fdd21c1bfca8ef62da7b7))
* **contract:** machine-readable front-matter in AGENT_CONTRACT.md with shared dependency caching ([78317bf](https://github.com/arii/boomtick/commit/78317bf187ba32b0cf1dcd5152d3f5502dc3224d))
* **contract:** machine-readable front-matter in AGENT_CONTRACT.md with shared dependency caching ([#1047](https://github.com/arii/boomtick/issues/1047)) ([507464b](https://github.com/arii/boomtick/commit/507464bd8daa3cc81a504e8df65c3e2bdf0e465f))
* **mcp:** agent_discuss fixed-topic protocol ([#1044](https://github.com/arii/boomtick/issues/1044)) ([946897d](https://github.com/arii/boomtick/commit/946897d9d4f2c0fa2fce66d5847e63f690baecd3))
* **mcp:** agent_dispatch with worktree-scoped sessions (agent_status, agent_logs) ([ae10c37](https://github.com/arii/boomtick/commit/ae10c37ee04a116fef953f98c91e3d90a013d4e6))
* **mcp:** agent_dispatch with worktree-scoped sessions (agent_status, agent_logs) ([2817fe4](https://github.com/arii/boomtick/commit/2817fe45b5f9d631098c0a35539bd41ebd874483))
* **mcp:** agent_dispatch with worktree-scoped sessions (agent_status, agent_logs) ([f201ab0](https://github.com/arii/boomtick/commit/f201ab0a86c43f0967699ca10bce456d290b4904))
* **mcp:** agent_dispatch with worktree-scoped sessions (agent_status, agent_logs) ([82f6684](https://github.com/arii/boomtick/commit/82f668454c076b4806002f21100fd038a41f741a))
* **mcp:** agent_dispatch with worktree-scoped sessions (agent_status, agent_logs) ([#1046](https://github.com/arii/boomtick/issues/1046)) ([df5313e](https://github.com/arii/boomtick/commit/df5313e830d40a2fec7170fae50dc103816a1e07))
* **mcp:** worktree lifecycle tools ([d1d3fb4](https://github.com/arii/boomtick/commit/d1d3fb42a56a3530c793503e9b7972d8307057d9))
* **mcp:** worktree lifecycle tools (worktree_create, worktree_list, worktree_remove) ([#1042](https://github.com/arii/boomtick/issues/1042)) ([1ca2ae1](https://github.com/arii/boomtick/commit/1ca2ae15010f062f7e2bed9f4da0bac89991c00a))


### Bug Fixes

* **daemon:** support multi-repo Jules feedback and chunk batch PR searches [skip-scope-check] ([18719a2](https://github.com/arii/boomtick/commit/18719a2f942d7df8325ab70a9f9bdedee528212c))
* **daemon:** support multi-repo Jules feedback and chunk batch PR searches [skip-scope-check] ([#1053](https://github.com/arii/boomtick/issues/1053)) ([2aa9f65](https://github.com/arii/boomtick/commit/2aa9f658c5f72d81608ccec25614dde240d40609))
* **mcp:** clarify repo override param description and surface errors in repo_get_workflow_runs (fixes [#1025](https://github.com/arii/boomtick/issues/1025)) ([818342e](https://github.com/arii/boomtick/commit/818342ebf224d727e4581271b9263194d72e0e34))
* **mcp:** clarify repo override param description and surface errors in repo_get_workflow_runs [skip-scope-check] ([#1051](https://github.com/arii/boomtick/issues/1051)) ([6ab5003](https://github.com/arii/boomtick/commit/6ab5003735696faa3c3d26ba0a0d6454dd3baca3))
* **mcp:** restore worktree schema models and align session manager types ([2629dc6](https://github.com/arii/boomtick/commit/2629dc6aa11379238099f6dd42b143a98b385d3a))
* **repair-flow:** improve branch observability, conflict accuracy, repo overrides ([#1058](https://github.com/arii/boomtick/issues/1058)) ([8f96ef8](https://github.com/arii/boomtick/commit/8f96ef8c2071e1db0b7ed1056c9640f03b4e7f3c))

## [0.15.2](https://github.com/arii/boomtick/compare/cli-v0.15.1...cli-v0.15.2) (2026-11-01)


### Bug Fixes

* **cli:** add suggest fast-path and graceful list-sessions fallback ([#1021](https://github.com/arii/boomtick/issues/1021)) ([309ef2a](https://github.com/arii/boomtick/commit/309ef2aec26061815f3c4dd3bf2a7e67d4ff220e))
* **cli:** allow preflight in non-monorepo repositories by skipping missing scripts ([#1028](https://github.com/arii/boomtick/issues/1028)) ([c6dafdd](https://github.com/arii/boomtick/commit/c6dafdd5e48d23f5539b9dfe900084a8b52d546e))
* **mcp:** align resource URI schemes with MCP server discovery and add context status check tool ([#1016](https://github.com/arii/boomtick/issues/1016)) ([522cae1](https://github.com/arii/boomtick/commit/522cae149cf302a6c66c8c0f20e17309fa483173))


### Documentation

* **onboarding:** restrict AI review model guidance to Gemini API only ([#1030](https://github.com/arii/boomtick/issues/1030)) ([22ed9aa](https://github.com/arii/boomtick/commit/22ed9aa99f0b82ff0fd538b8666dce3fdfa21218))

## [0.15.1](https://github.com/arii/boomtick/compare/cli-v0.15.0...cli-v0.15.1) (2026-10-29)


### Bug Fixes

* **mcp:** resolve target workspace dynamically in repo.create_branch and worktree tools ([#990](https://github.com/arii/boomtick/issues/990)) ([cd2f34e](https://github.com/arii/boomtick/commit/cd2f34ea8607f037b855d41f899bf5152dc13c1f))

## [0.15.0](https://github.com/arii/boomtick/compare/cli-v0.14.3...cli-v0.15.0) (2026-10-29)


### Features

* **aggregate:** agent onboarding, multi-repo context, and sequential orchestration ([#1001](https://github.com/arii/boomtick/issues/1001)) ([7060777](https://github.com/arii/boomtick/commit/7060777195a84d391b5098226ce06a04ddefcd9a))
* **aggregate:** pure-node container, review runner hardening, mcp modernization, and offline dag engine ([#1002](https://github.com/arii/boomtick/issues/1002)) ([056503c](https://github.com/arii/boomtick/commit/056503c8c21b5bd99f3b9d874ee7fac25972362a))
* **cli:** solidify td as a deterministic offline workstation engine ([d5f1a06](https://github.com/arii/boomtick/commit/d5f1a0685114d947cf82a95a8d2ae9749f695c20))
* **cli:** solidify td as a deterministic offline workstation engine ([d059e67](https://github.com/arii/boomtick/commit/d059e675e77ccf570f45a4a668967b50ae22f480))
* **mcp:** modernize boomtick-mcp with typed outputSchema, resources interface, and streamable HTTP transport ([26401df](https://github.com/arii/boomtick/commit/26401df06774e9de7756a375e0080810cc35926e))


### Bug Fixes

* **container:** optimize container image footprint within 250MB size budget ([3e61d20](https://github.com/arii/boomtick/commit/3e61d205163a741890789047207452fec52df141))

## [0.14.3](https://github.com/arii/boomtick/compare/cli-v0.14.2...cli-v0.14.3) (2026-10-28)


### Bug Fixes

* **ci:** fix scope constraint validation for bot release PRs ([#977](https://github.com/arii/boomtick/issues/977)) ([a02baa0](https://github.com/arii/boomtick/commit/a02baa09d71fba38451c3967fc6ee38060a9ddbf))

## [0.14.2](https://github.com/arii/boomtick/compare/cli-v0.14.1...cli-v0.14.2) (2026-10-28)


### Bug Fixes

* **cli:** load project config lazily to avoid crash outside repo ([#975](https://github.com/arii/boomtick/issues/975)) ([ff88b1a](https://github.com/arii/boomtick/commit/ff88b1ad0c7663d737e465ff430e2d349d7fad84))

## [0.14.1](https://github.com/arii/boomtick/compare/cli-v0.14.0...cli-v0.14.1) (2026-10-28)


### Bug Fixes

* **ci:** fix release pipeline schema generation and issue quality check on automated alerts [skip-scope-check] ([#956](https://github.com/arii/boomtick/issues/956)) ([a0e6114](https://github.com/arii/boomtick/commit/a0e6114e33dac799313f36f363de6008477cebfe))
* **ci:** fix release-please scope constraint validation failure ([#947](https://github.com/arii/boomtick/issues/947)) ([2c0615d](https://github.com/arii/boomtick/commit/2c0615d8877591f2da203e766c917e022bde764e))
* **ci:** support modular refactoring and extracted sub-files in verify-scope.py ([#968](https://github.com/arii/boomtick/issues/968)) ([a73ac4f](https://github.com/arii/boomtick/commit/a73ac4f90c7c078c5a7d9a448f03cef04ab549f6))
* **cli:** Eliminate runtime sys.path mutations in schema_gen.py ([#967](https://github.com/arii/boomtick/issues/967)) ([e1654de](https://github.com/arii/boomtick/commit/e1654dec8cf4af0da08d0808ee815e39cb9ab634))
* **cli:** Standardize PR number CLI arguments to accept both '--pr' and '--pr-number' across all 'td gh' subcommands ([#966](https://github.com/arii/boomtick/issues/966)) ([5000b9b](https://github.com/arii/boomtick/commit/5000b9b254e178a88a99fce2627bf69a0bf3a149))
* **doctor:** Deduplicate safe.directory list and fix false-positive ownership check in td doctor ([#965](https://github.com/arii/boomtick/issues/965)) ([1901a98](https://github.com/arii/boomtick/commit/1901a98a9fafc403bce8110eb4c059c6a1078d8e))

## [0.14.0](https://github.com/arii/boomtick/compare/cli-v0.13.1...cli-v0.14.0) (2026-10-23)


### Features

* **cli:** provide unified td preflight command ([#932](https://github.com/arii/boomtick/issues/932)) ([08e3061](https://github.com/arii/boomtick/commit/08e30617efdb82acd321808dcc562385e748107c))
* equip td audit with tree-sitter AST linting for anti-pattern detection ([#928](https://github.com/arii/boomtick/issues/928)) ([d9c461b](https://github.com/arii/boomtick/commit/d9c461b76bda8900d524f84555aef2c1537f11e6))

## [0.13.1](https://github.com/arii/boomtick/compare/cli-v0.13.0...cli-v0.13.1) (2026-10-23)


### Bug Fixes

* **scripts:** resolve root directory paths and commands in workflow verification scripts [skip-scope-check] ([#913](https://github.com/arii/boomtick/issues/913)) ([5d00802](https://github.com/arii/boomtick/commit/5d0080293cca97060b3334b0441e9ec6d42e6626))

## [0.13.0](https://github.com/arii/boomtick/compare/cli-v0.12.1...cli-v0.13.0) (2026-10-22)


### Features

* aggregate PRs 908, 893, 895, 896, 897, 898 (canonical td migration, modern MCP, multi-target release, code intelligence, container suggestions) ([#910](https://github.com/arii/boomtick/issues/910)) ([3636191](https://github.com/arii/boomtick/commit/36361910cf0a2d9b8648a951e3338143520bb664))

## [0.12.1](https://github.com/arii/boomtick/compare/cli-v0.12.0...cli-v0.12.1) (2026-10-20)


### Bug Fixes

* **ci:** install build module before python3 -m build in release workflow ([#880](https://github.com/arii/boomtick/issues/880)) ([082ea63](https://github.com/arii/boomtick/commit/082ea637b6fd449950cd56b43995d7e34177d077))

## [0.12.0](https://github.com/arii/boomtick/compare/cli-v0.11.0...cli-v0.12.0) (2026-10-19)


### Features

* **tooling:** add PR reviews, PR commits, workflow runs inspection, and repo overrides ([#834](https://github.com/arii/boomtick/issues/834)) ([42a8638](https://github.com/arii/boomtick/commit/42a8638add4ce8278dedacd6d8d14acc9e0a3bb9))


### Bug Fixes

* **ci:** fix release-please scope constraint validation and checkout ref failures ([#819](https://github.com/arii/boomtick/issues/819)) ([76c4c62](https://github.com/arii/boomtick/commit/76c4c62d9ca1e17b3611d0d91c96103b7e46e906))

## [0.11.0](https://github.com/arii/boomtick/compare/cli-v0.10.1...cli-v0.11.0) (2026-10-12)


### Features

* **cli:** consolidate 'td agent plan-aggregation' into single unified plan artifact ([#803](https://github.com/arii/boomtick/issues/803)) ([05addc2](https://github.com/arii/boomtick/commit/05addc2be8e84bf4dedc9b794472eb8b2f2389dc))


### Bug Fixes

* **cli:** implement hunk-scoped AI conflict resolution and deterministic strategy fallback ([#810](https://github.com/arii/boomtick/issues/810)) ([9977c5d](https://github.com/arii/boomtick/commit/9977c5d449ce8de54bd4c7a1908a064d3d372b7c))
* **cli:** support session title in agent dispatch ([#801](https://github.com/arii/boomtick/issues/801)) ([e358cc5](https://github.com/arii/boomtick/commit/e358cc51e2c9cc9c3295a8265835d8d05ff26d4a))
* **mcp:** support dynamic repo context resolution and --repo forwarding across workspaces ([#811](https://github.com/arii/boomtick/issues/811)) ([f7e1665](https://github.com/arii/boomtick/commit/f7e166594f170843b7f2e267fab119c631bf3c83))

## [0.10.1](https://github.com/arii/boomtick/compare/cli-v0.10.0...cli-v0.10.1) (2026-09-22)


### Bug Fixes

* **cli,mcp:** improve workspace config resolution and github repo detection ([#787](https://github.com/arii/boomtick/issues/787)) ([0103e90](https://github.com/arii/boomtick/commit/0103e904d30213cc336a1ce9567ad59257494236))


### Documentation

* update boomtick-cli package description to showcase projects built with tool ([#791](https://github.com/arii/boomtick/issues/791)) ([a8875cd](https://github.com/arii/boomtick/commit/a8875cdf8d49080e31263aa63e22e3a827df4859))

## [0.10.0](https://github.com/arii/boomtick/compare/cli-v0.9.2...cli-v0.10.0) (2026-09-04)


### Features

* **impact:** add targeted route and viewport options for visual diff… ([#775](https://github.com/arii/boomtick/issues/775)) ([c767fd4](https://github.com/arii/boomtick/commit/c767fd47063ce6a1078a728c3af79bcf18e2c5c5))


### Performance Improvements

* **concurrency:** replace blocking time.sleep with configurable sleep callback ([#771](https://github.com/arii/boomtick/issues/771)) ([ec31958](https://github.com/arii/boomtick/commit/ec31958345affdc45e9810678b3233eec428acf2))

## [0.9.2](https://github.com/arii/boomtick/compare/cli-v0.9.1...cli-v0.9.2) (2026-09-01)


### Performance Improvements

* **pr-overlap:** parallelize PR file fetching to eliminate N+1 API calls ([#750](https://github.com/arii/boomtick/issues/750)) ([5281b0d](https://github.com/arii/boomtick/commit/5281b0d2eed6b9a26b471ea03a58c77c55cabc4e))

## [0.9.1](https://github.com/arii/boomtick/compare/cli-v0.9.0...cli-v0.9.1) (2026-08-13)


### Bug Fixes

* **ai:** add gemini fallback logic to AIClient ([b57ca81](https://github.com/arii/boomtick/commit/b57ca811881f22036c9bc025656a27fdd0642764))
* **ai:** add gemini fallback logic to AIClient ([5cc87cc](https://github.com/arii/boomtick/commit/5cc87cc79e65df79db98bc27e679d14ffdd2d18d))
* **ai:** add gemini fallback logic to AIClient ([3ba37ec](https://github.com/arii/boomtick/commit/3ba37ec50a7447a9517e9f0029ff05ee01adf4d8))
* **ai:** add gemini fallback logic to AIClient ([f814c7f](https://github.com/arii/boomtick/commit/f814c7f7cd3a356d1e32c74474c1d5b5a02a97b0))
* **ai:** Add Gemini fallback mechanism for AIClient operations ([#638](https://github.com/arii/boomtick/issues/638)) ([e86eb04](https://github.com/arii/boomtick/commit/e86eb04f583ede49d9408686c3e141ce151529f6))
* resolve Gemini schema errors and enable separate OpenAI code reviewer in Docker CI container ([#655](https://github.com/arii/boomtick/issues/655)) ([7326bc1](https://github.com/arii/boomtick/commit/7326bc1f781024afc77fb9d1dd8cbcefafd54829))

## [0.9.0](https://github.com/arii/boomtick/compare/cli-v0.8.0...cli-v0.9.0) (2026-08-10)


### Features

* centralized concurrency helper for Orchestrator ([#465](https://github.com/arii/boomtick/issues/465)) ([fd57148](https://github.com/arii/boomtick/commit/fd57148067f66a36719b32930427ba96fc265e65))


### Bug Fixes

* catch explicit UnknownObjectException in fix_ci method ([#487](https://github.com/arii/boomtick/issues/487)) ([5457c0e](https://github.com/arii/boomtick/commit/5457c0eb46b27c08e82456258751a5addfb24922))

## [0.8.0](https://github.com/arii/boomtick/compare/cli-v0.7.0...cli-v0.8.0) (2026-08-05)


### Features

* add --all flag to detect-conflicts command ([#419](https://github.com/arii/boomtick/issues/419)) ([7760ef2](https://github.com/arii/boomtick/commit/7760ef270e7c7f3fd54f283144ccbd385a005b5e))


### Bug Fixes

* td-cli gh issue-view --issue-number fails to parse argument ([#420](https://github.com/arii/boomtick/issues/420)) ([c916796](https://github.com/arii/boomtick/commit/c9167968bb0b1d9b19ed36961a9ba4834ff2ec9c))


### Documentation

* update agent workflows to reference search-issues command ([#422](https://github.com/arii/boomtick/issues/422)) ([3d94c11](https://github.com/arii/boomtick/commit/3d94c115a576297735202c613eb138c176d20390))

## [0.7.0](https://github.com/arii/boomtick/compare/cli-v0.6.1...cli-v0.7.0) (2026-08-05)


### Features

* implement td-cli gh search-issues command ([#411](https://github.com/arii/boomtick/issues/411)) ([d5537df](https://github.com/arii/boomtick/commit/d5537df8b8a3792b652fc0269ec51655b72d5fea))


### Documentation

* Audit all open GitHub issues ([#391](https://github.com/arii/boomtick/issues/391)) ([dfced8f](https://github.com/arii/boomtick/commit/dfced8f0ce616d5c9f1c8449525b8f9c28ad3f9d))

## [0.6.1](https://github.com/arii/boomtick/compare/cli-v0.6.0...cli-v0.6.1) (2026-07-21)


### Bug Fixes

* resolve python lint and type check errors ([#275](https://github.com/arii/boomtick/issues/275)) ([09abb29](https://github.com/arii/boomtick/commit/09abb29d156301396ffa06148800b5bb6c6ed510))

## [0.6.0](https://github.com/arii/boomtick/compare/cli-v0.5.1...cli-v0.6.0) (2026-07-20)


### Features

* support local agent orchestration in audit dispatch workflow ([#209](https://github.com/arii/boomtick/issues/209)) ([4df676a](https://github.com/arii/boomtick/commit/4df676ac265f2290a9003069c243627e85237962))

## [0.5.1](https://github.com/arii/boomtick/compare/cli-v0.5.0...cli-v0.5.1) (2026-07-18)


### Bug Fixes

* **ci:** optimize dependency graph traversal to prevent CI failure ([#203](https://github.com/arii/boomtick/issues/203)) ([991b70c](https://github.com/arii/boomtick/commit/991b70c77047a40e7dcc9948f60a3ea083d415a2))

## [0.5.0](https://github.com/arii/boomtick/compare/cli-v0.4.0...cli-v0.5.0) (2026-07-18)


### Features

* Consolidated Workflow Orchestrator ([#189](https://github.com/arii/boomtick/issues/189)) ([fefe3d8](https://github.com/arii/boomtick/commit/fefe3d84dda6ce863601e5d09943a5d45f085bbb))

## [0.4.0](https://github.com/arii/boomtick/compare/cli-v0.3.1...cli-v0.4.0) (2026-07-17)


### Features

* AI Code Review - Develop PR Context Aggregator ([#174](https://github.com/arii/boomtick/issues/174)) ([981137d](https://github.com/arii/boomtick/commit/981137d3d13ce449ab2db79880a0d7780365dc7a))

## [0.3.1](https://github.com/arii/boomtick/compare/cli-v0.3.0...cli-v0.3.1) (2026-07-17)


### Bug Fixes

* Address code review findings ([#159](https://github.com/arii/boomtick/issues/159)) ([34bcc36](https://github.com/arii/boomtick/commit/34bcc3634b49fe83d693fdbb5bec8b2993fe6ba7))

## [0.3.0](https://github.com/arii/boomtick/compare/cli-v0.2.1...cli-v0.3.0) (2026-07-15)


### Features

* Add Automated Agent Feedback Daemon ([#3246](https://github.com/arii/boomtick/issues/3246)) ([a800327](https://github.com/arii/boomtick/commit/a800327a048b2e9c078d39027fc9d11e660022a8))
* **ci:** consolidate AI code review rules from PR 3281 and PR 3282 ([#3395](https://github.com/arii/boomtick/issues/3395)) ([97c7f50](https://github.com/arii/boomtick/commit/97c7f5065f26747a08440e2430b80af7476f2a8d))
* **cli:** Add tool to fetch PR and review comments natively ([#3355](https://github.com/arii/boomtick/issues/3355)) ([7c98b80](https://github.com/arii/boomtick/commit/7c98b8097b51066abc2c97ab16582a451565b626))
* Enforce strict `project_config.json` parsing and remove hardcoded fallbacks ([#3624](https://github.com/arii/boomtick/issues/3624)) ([bf2227e](https://github.com/arii/boomtick/commit/bf2227eabb70b3bb5598738b436b6cf3c378aa7a))
* Map agent dispatch commands to jules_feedback_loop ([#3078](https://github.com/arii/boomtick/issues/3078)) ([a3d259a](https://github.com/arii/boomtick/commit/a3d259a98410c48b373fb420420eed94fa53c483))
* migrate release workflows to boomtick-pkg and setup symlinks wi… ([#3614](https://github.com/arii/boomtick/issues/3614)) ([0b31b7c](https://github.com/arii/boomtick/commit/0b31b7c7869beea22d47d5b0834eb3f99243a464))
* Unified Python Core Engine Consolidation ([#3166](https://github.com/arii/boomtick/issues/3166)) ([0dad8bb](https://github.com/arii/boomtick/commit/0dad8bbdf3e331e25a5b106c35d95ee38bf0c012))


### Bug Fixes

* add state parameter to github.issue_update MCP schema ([#3205](https://github.com/arii/boomtick/issues/3205)) ([5642e83](https://github.com/arii/boomtick/commit/5642e833dcf66cdd309a489a4935f247fe9a5f1e))
* **ci:** handle missing AI logs gracefully in verify-metrics ([#3580](https://github.com/arii/boomtick/issues/3580)) ([b126289](https://github.com/arii/boomtick/commit/b126289e565c403a1a84ba5160b40223ea8ccce7))
* **ci:** pass --ignore-scripts to impact build main ([#53](https://github.com/arii/boomtick/issues/53)) ([7160e49](https://github.com/arii/boomtick/commit/7160e494992764d9d95f0dadd0c5c5d23f199428))
* **ci:** pass --ignore-scripts to impact build main ([#55](https://github.com/arii/boomtick/issues/55)) ([4a5d1d9](https://github.com/arii/boomtick/commit/4a5d1d989f21fd62627e28027624b1bb4982127b))
* **cli:** implement lazy orchestrator to reduce startup time ([#3278](https://github.com/arii/boomtick/issues/3278)) ([4966ade](https://github.com/arii/boomtick/commit/4966ade6f067ea3a8269851d45c3635839957b97))
* **cli:** resolve td-cli UX, aliases, and crashes ([#3392](https://github.com/arii/boomtick/issues/3392)) ([d4e12d6](https://github.com/arii/boomtick/commit/d4e12d6b7aeb9bb955274629a4cc67343bc1a6e3))
* **cli:** retain review findings in PR comments ([#3450](https://github.com/arii/boomtick/issues/3450)) ([64aa1bd](https://github.com/arii/boomtick/commit/64aa1bdd1c62cb0c5afc01f5d27cededf04e964e))
* detect-antipatterns.mjs path resolution and impact-analysis-utils eslint errors ([#52](https://github.com/arii/boomtick/issues/52)) ([797475e](https://github.com/arii/boomtick/commit/797475ef8b93c5d74627d329e7bf842852a374c8))
* path resolution and linting issues in impact analysis ([#49](https://github.com/arii/boomtick/issues/49)) ([2b23a39](https://github.com/arii/boomtick/commit/2b23a39848e4c012d7c94b633c0627cad85619f6))
* resolve ModuleNotFoundError in Jules session creation and isolate python env ([#3442](https://github.com/arii/boomtick/issues/3442)) ([6870392](https://github.com/arii/boomtick/commit/6870392b6a1f5784110d9a75a1e6b972cf297775))
* Resolve tester findings and update progress documentation ([#3191](https://github.com/arii/boomtick/issues/3191)) ([1cfea38](https://github.com/arii/boomtick/commit/1cfea3813129f9289122a12f80c543103a541f6a))
* **security:** refactor dev_tools utils to use requests instead of ur… ([#3097](https://github.com/arii/boomtick/issues/3097)) ([ce3b04c](https://github.com/arii/boomtick/commit/ce3b04c546dd8e2104222674584cf4e17398cbb6))
