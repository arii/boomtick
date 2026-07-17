# Changelog

## [0.3.2](https://github.com/arii/boomtick/compare/mcp-v0.3.1...mcp-v0.3.2) (2026-07-17)


### Bug Fixes

* pass jules_api_key env to impact analysis steps ([#151](https://github.com/arii/boomtick/issues/151)) ([a4744ee](https://github.com/arii/boomtick/commit/a4744eeed2d665eb87053f828551a1136259b0fc))

## [0.3.1](https://github.com/arii/boomtick/compare/mcp-v0.3.0...mcp-v0.3.1) (2026-07-17)


### Bug Fixes

* resolve workflow audit failures and consolidate automation ([#110](https://github.com/arii/boomtick/issues/110)) ([aa3682b](https://github.com/arii/boomtick/commit/aa3682b966cc3de6639f0a895bfafffb89106fcb))

## [0.3.0](https://github.com/arii/boomtick/compare/mcp-v0.2.1...mcp-v0.3.0) (2026-07-15)


### Features

* **cli:** Add tool to fetch PR and review comments natively ([#3355](https://github.com/arii/boomtick/issues/3355)) ([7c98b80](https://github.com/arii/boomtick/commit/7c98b8097b51066abc2c97ab16582a451565b626))
* Consolidate CI setup logic into composite action ([#3073](https://github.com/arii/boomtick/issues/3073)) ([ac9012f](https://github.com/arii/boomtick/commit/ac9012f4ec377c29fada9f71d1091854394d96c0))
* consolidated package extraction for boomtick-pkg ([#3491](https://github.com/arii/boomtick/issues/3491)) ([8e33e34](https://github.com/arii/boomtick/commit/8e33e34e4ca2711d1468944c0f8294386bf26445))
* Handle missing node_modules gracefully in verify:schemas script ([#3438](https://github.com/arii/boomtick/issues/3438)) ([b9645a8](https://github.com/arii/boomtick/commit/b9645a8d9846dbafab2ca5a1c6951005ad862af1))
* **mcp:** add dedicated github.get_pr tool ([#3277](https://github.com/arii/boomtick/issues/3277)) ([a74dc79](https://github.com/arii/boomtick/commit/a74dc79e1d7d1a4ade89852c28a16ec5b834ea30))
* migrate release workflows to boomtick-pkg and setup symlinks wi… ([#3614](https://github.com/arii/boomtick/issues/3614)) ([0b31b7c](https://github.com/arii/boomtick/commit/0b31b7c7869beea22d47d5b0834eb3f99243a464))
* Unified Python Core Engine Consolidation ([#3166](https://github.com/arii/boomtick/issues/3166)) ([0dad8bb](https://github.com/arii/boomtick/commit/0dad8bbdf3e331e25a5b106c35d95ee38bf0c012))


### Bug Fixes

* add state parameter to github.issue_update MCP schema ([#3205](https://github.com/arii/boomtick/issues/3205)) ([5642e83](https://github.com/arii/boomtick/commit/5642e833dcf66cdd309a489a4935f247fe9a5f1e))
* **ci:** handle missing AI logs gracefully in verify-metrics ([#3554](https://github.com/arii/boomtick/issues/3554)) ([5e0c346](https://github.com/arii/boomtick/commit/5e0c34659d6344ff7a79a86dc88d06bee8b96998))
* **ci:** handle missing AI logs gracefully in verify-metrics ([#3580](https://github.com/arii/boomtick/issues/3580)) ([b126289](https://github.com/arii/boomtick/commit/b126289e565c403a1a84ba5160b40223ea8ccce7))
* **ci:** pass --ignore-scripts to impact build main ([#53](https://github.com/arii/boomtick/issues/53)) ([7160e49](https://github.com/arii/boomtick/commit/7160e494992764d9d95f0dadd0c5c5d23f199428))
* **ci:** pass --ignore-scripts to impact build main ([#55](https://github.com/arii/boomtick/issues/55)) ([4a5d1d9](https://github.com/arii/boomtick/commit/4a5d1d989f21fd62627e28027624b1bb4982127b))
* detect-antipatterns.mjs path resolution and impact-analysis-utils eslint errors ([#52](https://github.com/arii/boomtick/issues/52)) ([797475e](https://github.com/arii/boomtick/commit/797475ef8b93c5d74627d329e7bf842852a374c8))
* **mcp:** use sessionId for jules tools to avoid PR ID confusion ([#3286](https://github.com/arii/boomtick/issues/3286)) ([0c4147b](https://github.com/arii/boomtick/commit/0c4147b8cdd98160f0422dcf73ec8b35164176bf))
* **mcp:** use z.input instead of z.infer for CreateBranchInputSchema ([#3094](https://github.com/arii/boomtick/issues/3094)) ([baeaf41](https://github.com/arii/boomtick/commit/baeaf41a0333b73dc597a72c876e87c4dd4a1ae3))
* path resolution and linting issues in impact analysis ([#49](https://github.com/arii/boomtick/issues/49)) ([2b23a39](https://github.com/arii/boomtick/commit/2b23a39848e4c012d7c94b633c0627cad85619f6))
* resolve ModuleNotFoundError in Jules session creation and isolate python env ([#3442](https://github.com/arii/boomtick/issues/3442)) ([6870392](https://github.com/arii/boomtick/commit/6870392b6a1f5784110d9a75a1e6b972cf297775))
* Resolve tester findings and update progress documentation ([#3191](https://github.com/arii/boomtick/issues/3191)) ([1cfea38](https://github.com/arii/boomtick/commit/1cfea3813129f9289122a12f80c543103a541f6a))
