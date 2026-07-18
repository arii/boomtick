# Changelog

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
