# ADR-001: Web UI Stack Selection (React + Vite + TypeScript vs Static SPA)

## Status
Accepted

## Context
ShadowX Factory requires a real-time web interface to visualize:
1. The multi-agent pipeline state machine (`ANALYSIS` -> `DESIGN` -> `CODING` -> `TESTING` -> `DEBUGGING` -> `REVIEW` -> `DOCS`).
2. An interactive DAG/graph with state transitions and cycle counters for the Tester-Debugger loop.
3. Syntax-highlighted code viewer and unified diff inspector (Monaco Editor).
4. Live event stream timeline over Server-Sent Events (SSE).
5. Offline replay mode for quota-free demonstration of runs.

The host operating system is Windows with Device Guard active. In earlier stages of this project, Device Guard blocked pip-generated `.exe` launchers (`shadow.exe`). There was a risk that Windows AppLocker / Device Guard policies would similarly block Node.js tools, npm scripts, or native compilers (such as ESBuild).

## Spike Findings
On Day 1, we executed an isolated toolchain spike:
- Node.js runtime: `v24.18.0`
- Package manager: `npm 11.16.0`
- Test commands executed: `npx create-vite@latest ui-spike --template react-ts`, `npm install`, `npm run build`.
- **Result**: The Vite development server and production build bundle completed cleanly in 3.98s with zero Device Guard blocks, security alerts, or binary execution restrictions.

## Decision
We select **React 19 + Vite + TypeScript + Tailwind CSS** as the primary frontend stack:
- **Graph Visualization**: `@xyflow/react` (React Flow) for rendering the pipeline state machine and active node animations.
- **Code & Diff Viewing**: `@monaco-editor/react` for high-fidelity code rendering and side-by-side git diffs.
- **Charts & Metrics**: `recharts` for token usage and stage duration analytics.

### Contingency Fallback
If downstream npm packages with unsigned C++ binaries ever encounter Device Guard restrictions on a specific deployment host, the backend is built to serve a static single-page app (vanilla JS + Alpine.js + Tailwind CDN + Mermaid.js) from FastAPI (`/static`) using the identical SSE endpoint contract.

## Consequences
- Clean separation between backend API and reactive frontend.
- Standard developer experience with fast HMR (Hot Module Replacement).
- Easy production packaging: `npm run build` outputs static assets directly into FastAPI's static mount directory.
