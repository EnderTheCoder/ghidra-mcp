# Changelog

## 20260722.6

- Moved detailed user documentation to the GitHub Wiki and made the remaining repository documentation English-first.
- Removed the clean-room charter and obsolete development-stage specification, source, and verification documents.
- Added a task-oriented Wiki with getting-started, tool catalog, and operations pages.

## 20260722.5

- Added a GHCR publication workflow pinned to exact action commits. Pushes to `main` build `linux/amd64` without cache, publish version and `latest` tags, and verify health metadata against the remote digest.
- Made the English README the primary entry point and added an independent Chinese README.
- Added Python package metadata for the README, project links, issue tracker, and container image.

## 20260722.4

- Licensed original project code under Apache License 2.0 and included the standard license and `xjoker` attribution in source archives, wheels, and container images.
- Added public contribution and security-reporting policies and MCP client configuration examples.
- Removed hard-coded release versions from documentation.

## 20260722.3

- Added standard MCP `ToolAnnotations` to tool contracts and included them in the schema digest.
- Marked `program_close` as a non-idempotent mutation that removes the active session while preserving save-first behavior and keeping the session open when saving fails.
- Upgraded the development test dependency to pytest 9.1.1 to resolve a medium-severity temporary-directory advisory.

## 20260722.2

- Made `instructions_list` report requested and effective start addresses and skipped byte counts, with optional strict start validation.
- Made `function_get` distinguish function-body membership from unassigned addresses and added `function_body_add` for confirmed detached continuation ranges.
- Added bounded pseudo-disassembly to `references_list` for direct references into undefined control-flow-flattening code islands, including coverage, source, and confidence metadata.
- Made `control_flow_graph` distinguish static default flow from analyzer-inferred computed flow.
- Added tool contract versions to the schema digest so clients can detect incompatible response changes.

## 20260722.1

- Implemented a single-process PyGhidra MCP server from an empty Git history.
- Added 34 program, navigation, analysis, inspection, and transactional mutation tools.
- Added local stdio and Bearer-authenticated Streamable HTTP transports.
- Added layered configuration, persistent projects, health metadata, and a non-root `linux/amd64` image.
- Added original symbolic, stripped, and control-flow-heavy ELF fixtures with real Ghidra tests.
- Set Ghidra 12.1.2 as the security baseline and reject unknown or older installations before JVM startup.
- Added native Ghidra undo on save failure, bounded decompilation output, cancellable analysis deadlines, and strict HTTP input/public-URL boundaries.
