# Workspace cleanup audit

- Root files: 8
- Root noncanonical files: 7
- Backup/temp/stamp files: 5
- Archives: 0
- Binaries/build artifacts outside skipped dirs: 20
- Logs: 2
- Legacy path/name hits: 0
- Rust monoliths >550 LOC: 64
- Conservative safe-delete candidates: 6

## Root noncanonical files
- `.gitattributes`
- `.gitignore`
- `aiBridge.bat`
- `aiBridgeServer.bat`
- `serverBridge.bat`
- `suite.bat`
- `SuiteLogo.png`

## Safe-delete candidates
- `NewEngine/neocore2/third_party/joltc-sys/Cargo.toml.orig`
- `NewEngine/neocore2/winit-early.log`
- `tools/scripts/northstar_bridge/cli.py.forcewrite.bak`
- `tools/scripts/northstar_bridge/console.py.bak`
- `tools/scripts/northstar_bridge/server.py.bak`
- `tools/scripts/takesome/suite/progress_frame.py.bak`

## Archives
_none_

## Backup/temp/stamp
- `NewEngine/neocore2/third_party/joltc-sys/Cargo.toml.orig`
- `tools/scripts/northstar_bridge/cli.py.forcewrite.bak`
- `tools/scripts/northstar_bridge/console.py.bak`
- `tools/scripts/northstar_bridge/server.py.bak`
- `tools/scripts/takesome/suite/progress_frame.py.bak`

## Legacy path/name hits
_none_

## Rust monoliths >550 LOC
- `NewEngine/neocore2/crates/newengine-assets-catalog-ui-runtime/src/lib.rs` — 2100 LOC
- `NewEngine/neocore2/crates/newengine-assets-ui-runtime/src/lib.rs` — 2006 LOC
- `Plugins/AssetManager/newengine-AssetManager/src/asset_store/store.rs` — 1537 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/lib.rs` — 1466 LOC
- `Plugins/ProfilerPlugin/newengine-profiler-plugin/src/report.rs` — 1450 LOC
- `Plugins/FlecsECS/newengine-ecs-flecs/src/lib.rs` — 1393 LOC
- `NewEngine/neocore2/crates/newengine-assets-api/src/lib.rs` — 1392 LOC
- `Plugins/ProfilerPlugin/newengine-profiler-plugin/src/runtime.rs` — 1291 LOC
- `NewEngine/neocore2/crates/newengine-world-environment-api/src/lib.rs` — 1192 LOC
- `NewEngine/neocore2/crates/newengine-runtime-host/src/platform_runtime/runtime_host.rs` — 1175 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/render_api/graph_executor/native_pass_dispatch.rs` — 1165 LOC
- `NewEngine/neocore2/crates/newengine-model-runtime/src/lib.rs` — 1064 LOC
- `NewEngine/neocore2/crates/newengine-definitions-runtime/src/lib.rs` — 973 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/render_api/resources.rs` — 972 LOC
- `Plugins/AureliaUI/newengine-ui-provider-aurelia/src/service.rs` — 960 LOC
- `Plugins/InputPlugin/newengine-modules-input/src/module.rs` — 931 LOC
- `NewEngine/neocore2/crates/newengine-service-api/src/lib.rs` — 926 LOC
- `NewEngine/neocore2/crates/newengine-core/src/engine/module_boot.rs` — 922 LOC
- `NewEngine/neocore2/crates/newengine-assets/src/asset_document_service.rs` — 902 LOC
- `NewEngine/neocore2/crates/newengine-engine-runtime/src/scene_bridge/game_ready_parts/assets_bootstrap.rs` — 864 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/render_api/graph_executor/execution_registry.rs` — 860 LOC
- `NewEngine/neocore2/crates/newengine-render-api/src/render_graph.rs` — 860 LOC
- `Plugins/LoggingPlugin/newengine-modules-logging/src/logger/config.rs` — 838 LOC
- `Plugins/AureliaUI/newengine-ui-provider-aurelia/src/draw.rs` — 825 LOC
- `NewEngine/neocore2/crates/newengine-material-runtime/src/lib.rs` — 818 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/render_api/postfx.rs` — 817 LOC
- `NewEngine/neocore2/crates/newengine-render-api/src/protocol.rs` — 802 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/vulkan/shader_registry/stage_loader.rs` — 800 LOC
- `NewEngine/neocore2/crates/newengine-assets-api/src/asset_service_client.rs` — 772 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/render_api/visibility/gpu.rs` — 768 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/render_api/frame_plan/phase_catalog.rs` — 760 LOC
- `Plugins/AssetManager/newengine-AssetManager/src/module/service/listfile_writer.rs` — 751 LOC
- `NewEngine/neocore2/crates/newengine-ui-api/src/node.rs` — 748 LOC
- `NewEngine/neocore2/crates/newengine-input-bindings-api/src/lib.rs` — 734 LOC
- `NewEngine/neocore2/crates/newengine-textures-runtime/src/lib.rs` — 731 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/vulkan/ui/overlay.rs` — 727 LOC
- `NewEngine/neocore2/third_party/joltc-sys/src/bindings_static.rs` — 713 LOC
- `NewEngine/neocore2/crates/newengine-engine-runtime/src/render_controller/module_impl/frame_orchestrator.rs` — 711 LOC
- `NewEngine/neocore2/crates/newengine-runtime-host/src/platform_runtime/jobs_gateway.rs` — 683 LOC
- `NewEngine/neocore2/crates/newengine-jobs-api/src/lib.rs` — 663 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/render_api/deferred/gpu.rs` — 662 LOC
- `Plugins/AssetManager/codecs/newengine-codec-listfile/src/lib.rs` — 654 LOC
- `NewEngine/neocore2/crates/newengine-render-frame-graph/src/graph_builder.rs` — 653 LOC
- `NewEngine/neocore2/crates/newengine-ui-navigation-api/src/lib.rs` — 652 LOC
- `NewEngine/neocore2/crates/newengine-plugin-host/src/service_gateway/registry.rs` — 647 LOC
- `NewEngine/neocore2/crates/newengine-runtime-host/src/platform_runtime/config.rs` — 645 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/render_api/lights/gpu.rs` — 632 LOC
- `Plugins/AureliaUI/newengine-ui-provider-aurelia/src/text/shaping.rs` — 630 LOC
- `Plugins/LoggingPlugin/newengine-modules-logging/src/module.rs` — 619 LOC
- `NewEngine/neocore2/crates/newengine-engine-runtime/src/scene_bridge/game_ready_parts/sky.rs` — 614 LOC
- `NewEngine/neocore2/crates/newengine-engine-runtime/src/render_controller/module_impl/passes_parts/mesh_passes.rs` — 606 LOC
- `NewEngine/neocore2/crates/newengine-loading-api/src/lib.rs` — 600 LOC
- `NewEngine/neocore2/crates/newengine-core/src/console/runtime.rs` — 588 LOC
- `NewEngine/neocore2/crates/newengine-plugin-host/src/plugin_config_service.rs` — 587 LOC
- `Plugins/winit-platform-plugin/newengine-platform-winit/src/runtime_app/loading/north_star_compositor.rs` — 585 LOC
- `NewEngine/neocore2/crates/newengine-plugin-host/src/service_gateway/registry/tests.rs` — 583 LOC
- `Plugins/VulkanRenderer/newengine-modules-render-vulkan-ash/src/vulkan/renderer/init.rs` — 577 LOC
- `NewEngine/neocore2/crates/newengine-sim/src/schedule.rs` — 572 LOC
- `NewEngine/neocore2/crates/newengine-procedural-noise/src/graph.rs` — 571 LOC
- `NewEngine/neocore2/crates/newengine-text-api/src/lib.rs` — 570 LOC
- `NewEngine/neocore2/crates/newengine-render-api/src/effects.rs` — 570 LOC
- `NewEngine/neocore2/crates/newengine-physics-api/src/lib.rs` — 566 LOC
- `NewEngine/neocore2/crates/newengine-render-api/src/postfx.rs` — 562 LOC
- `NewEngine/neocore2/crates/newengine-scripting-api/src/lib.rs` — 553 LOC

## Split policy
- Split runtime files into `frame/`, `adapters/`, `scene/`, `ecs_apply/`, `diagnostics/`.
- Split provider files by backend concern: `gpu`, `pipeline`, `descriptors`, `passes`, `diagnostics`.
- Do not split generated/bindings/third_party files unless wrapped or excluded from the monolith gate.
