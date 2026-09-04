# Changelog

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
