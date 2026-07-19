# docs/ — project documentation index

Start with the root **`PROJECT_GUIDE.md`** (master usage guide) and root **`README.md`** (workspace map). This tree holds everything else:

| Folder | Contents |
|---|---|
| `usage/` | How to operate the system: `runbook.md` (relaunch the stack on a Chameleon node + gotchas), `testing-guide.md` (exercise the running system, read results). |
| `architecture/` | How it's designed: `architecture-and-integration.md` (chatbot ↔ advisor seam, plain language), `harness-plan.md` (benchmark harness + scorer contract), `router-refactor-plan.md` (RouterTree design + A7 ablation). |
| `reference/` | Config templates for the node: `node.env.reference` (the node's `.env`), `rag-app.service.reference` (systemd unit). |
| `archive/` | Historical, superseded by the above — kept for the record: `goal.md` (original mission plan), `progress-log.md` (execution log), `seam-map.md` (initial integration recon), `chi-edge-advisor_prototype-state.md` (advisor prototype snapshot, 2026-07-01; pre-integration paths/counts are stale). |
