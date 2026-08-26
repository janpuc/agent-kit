# agent-kit — implementation plan

Status: scaffold. Nothing is built yet. This document is the brief for the next
agent session.

## 1. Purpose

Three agent harnesses run against the same repositories: Claude Code, Codex and
OpenCode. Each one discovers skills from different directories, and each one has
its own plugin manifest format. Without a shared source of truth the same skill
gets copied three times, drifts in three directions, and nobody can say which
version any harness is running.

`agent-kit` is that source of truth. One batch, one version, one checksum,
three harnesses.

## 2. Requirements

These are fixed. Everything in this plan serves them.

1. **Works on Claude Code, Codex and OpenCode.** A skill is not shipped until it
   has been observed loading in all three.
2. **Versioned as one batch.** A single version and a single sha256 identify the
   whole set. Consumers pin one thing, not twenty-six.
3. **Skills and, where the format allows, plugins.** Skills are the primary
   payload; plugin manifests are the delivery convenience.

## 3. Verified ground truth

Everything in this section was verified against upstream source on 2026-08-26,
not inferred from documentation. Do not re-derive it; do challenge it if a
harness upgrade lands.

### 3.1 Skill discovery paths

| Path | Claude Code | Codex | OpenCode |
|---|:--:|:--:|:--:|
| `.claude/skills/<name>/SKILL.md` | yes | no | yes |
| `~/.claude/skills/` and `$CLAUDE_CONFIG_DIR/skills/` | yes | no | yes |
| `.agents/skills/<name>/SKILL.md` | no | yes | yes |
| `~/.agents/skills/` | no | yes | yes |
| `.opencode/skills/`, `~/.config/opencode/skills/` | no | no | yes |
| `$CODEX_HOME/skills`, `/etc/codex/skills` | no | yes | no |

Evidence:

- Codex: `const AGENTS_DIR_NAME: &str = ".agents"` in
  `codex-rs/ext/skills/src/host_roots.rs:24`. Codex reads `.agents` only and has
  no Claude-compatible path.
- OpenCode: `CLAUDE_EXTERNAL_DIR = ".claude"` and `AGENTS_EXTERNAL_DIR =
  ".agents"` in `packages/opencode/src/skill/index.ts:21-22`, gated by
  `disableExternalSkills` and `disableClaudeCodeSkills`.
- Claude Code: the shipped binary contains `.claude/skills` and **zero**
  occurrences of `.agents/skills`.

**The consequence that drives this whole repository:** no single directory
serves all three. A distribution must write to both `.agents/skills` and
`.claude/skills`. OpenCode reads both and keys skills by name
(`s.skills[name]`), so a skill present in both paths is deduplicated rather than
loaded twice.

### 3.2 SKILL.md is one format

The format is identical across all three harnesses. koment's own Claude and
Codex copies of its skill differ by exactly one line, the `description`.

OpenCode is the strictest validator, so author to its rules:

- `name`: required, `^[a-z0-9]+(-[a-z0-9]+)*$`, 1-64 characters, must equal the
  containing directory name.
- `description`: required, 1-1024 characters.
- `license`, `compatibility`, `metadata`: recognised by OpenCode, optional.
- Unknown frontmatter fields are ignored rather than rejected.

### 3.3 Subagents are not portable

Claude uses `agents/*.md` inside a skill; Codex uses `agents/openai.yaml`. These
are different formats for the same idea and neither harness reads the other's.

Fortunately `mattpocock/skills` already ships `agents/openai.yaml` in every
engineering skill, so those skills are already dual-harness. Any skill whose
value depends on a Claude-only `agents/*.md` will degrade on Codex and OpenCode;
say so in its entry in the lockfile rather than pretending it is portable.

### 3.4 Plugin systems

| | Claude Code | Codex | OpenCode |
|---|---|---|---|
| Manifest | `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` | `plugin.json` + JS entrypoint |
| Marketplace | `.claude-plugin/marketplace.json` | `.agents/plugins/marketplace.json` | none; npm package |
| Skills declared | auto-discovered from `skills/` | explicit `"skills": "./skills/"` | via config, not manifest |
| Install | `claude plugin marketplace add` | `codex plugin marketplace add` | `plugin[]` in `opencode.json` |

Evidence: Anthropic's own `skill-creator` plugin manifest declares no skills key
yet ships `skills/skill-creator/SKILL.md`, so Claude auto-discovers. koment's
Codex manifest declares `"skills": "./skills/"` explicitly. koment's OpenCode
integration is an npm package with a JS entrypoint and no skills at all.

OpenCode has a third route worth knowing about: its config accepts a `skills`
array of directory paths **or http(s) URLs**
(`packages/core/src/config/plugin/skill.ts`). That is the only remote-fetch
skill channel of the three.

## 4. The skill set

Decided. Seven skills, deliberately not twenty-six: every skill's `name` and
`description` is loaded into context by all three harnesses on every session, so
the set is a recurring cost paid three times over.

| Skill | Source | License | Why |
|---|---|---|---|
| `writing-for-agents` | `mattpocock/skills` | MIT | Four repositories here carry a hand-maintained `AGENTS.md`. Its default move is deleting no-op prose. |
| `diagnosing-bugs` | `mattpocock/skills` | MIT | Gates on a repro command that goes red before any theory is allowed. |
| `research` | `mattpocock/skills` | MIT | Primary sources only, writes a cited file. Suits Talos, Flux and kubebuilder API digging. |
| `tdd` | `mattpocock/skills` | MIT | Go work across dispatch, miroir and koment. |
| `codebase-design` | `mattpocock/skills` | MIT | Fixes design vocabulary; other skills borrow from it. |
| `triage` | `mattpocock/skills` | MIT | For incoming issues on public repositories. |
| `karpathy-guidelines` | `multica-ai/andrej-karpathy-skills` | MIT | Single-file behavioural overlay; cheap. |

Deliberately excluded, with reasons, so nobody re-litigates them silently:

- `code-review` — Claude Code ships a built-in `/code-review`.
- `implement`, `prototype` — overlap heavily with the above.
- `to-spec`, `to-tickets`, `wayfinder` — tracker-driven; revisit if issue-first
  workflows start.
- `wizard`, `ask-matt`, the productivity set — no current use.
- `skill-creator` — Codex already bundles its own at
  `$CODEX_HOME/skills/.system/skill-creator`, alongside `plugin-creator` and
  `skill-installer`. Adding a second one is confusing, not helpful.

## 5. Repository layout

```
agent-kit/
├── AGENTS.md                     the contract; CLAUDE.md points at it
├── PLAN.md                       this file
├── README.md                     what it is and how to consume it
├── VERSION                       one semver for the whole batch
├── agent-kit.lock.json           provenance and checksums for every skill
├── mise.toml                     toolchain pins
├── .justfile                     build, verify, release recipes
├── .koment/policy.yaml           comment policy
├── skills/<name>/SKILL.md        canonical, harness-neutral. Source of truth.
├── vendor/<name>/<sha>/          verbatim upstream. Never edited.
├── plugins/
│   ├── claude/.claude-plugin/plugin.json
│   ├── codex/.codex-plugin/plugin.json
│   └── opencode/{package.json,plugin.json,index.js}
├── .claude-plugin/marketplace.json    repo root as a Claude marketplace
├── .agents/plugins/marketplace.json   repo root as a Codex marketplace
├── scripts/                      build and verification
├── dist/                         generated, gitignored
└── .github/workflows/            validate and release
```

The rule that keeps this honest: `skills/` is authored, `vendor/` is evidence,
`dist/` is generated. Nothing is edited in two places.

## 6. Versioning

The requirement is one batch version and one sha. That resolves to:

- **`VERSION`** — a single semver for the entire batch. There are no per-skill
  versions. Adding, removing or changing any skill bumps this one number.
- **`agent-kit.lock.json`** — for each skill: upstream repository, upstream
  commit sha, license, the vendored path, and a per-file sha256 of the canonical
  tree. This is what makes "which version of `tdd` am I running" answerable.
- **Release artifacts** — `agent-kit_v<version>.tar.gz` plus
  `agent-kit_<version>_checksums.txt`.

The artifact naming deliberately mirrors koment's
(`koment-plugin-codex_v<tag>.tar.gz`, `koment-plugins_<version>_checksums.txt`)
because the consumer that will fetch this already knows how to parse that shape:
`gh release download` by pattern, then `sha256sum --check`. Do not invent a new
naming scheme for aesthetic reasons.

A consumer therefore pins exactly two strings: a version and a sha256. That is
the requirement, satisfied.

## 7. Phases

Each phase has an acceptance criterion. A phase is not done until its criterion
is demonstrated, not argued.

### Phase 0 — Resolve the open questions

Do this first and do it empirically. All three CLIs are available in the
session. Section 9 lists the questions. Write the answers back into this file
and record the reasoning with `koment add`.

*Accepts when:* every question in section 9 is answered with an observed
command output rather than a reading of the docs.

### Phase 1 — Vendor and canonicalise

Fetch each upstream skill tree at a pinned commit into
`vendor/<name>/<sha>/`, unmodified. Then create `skills/<name>/SKILL.md` as the
canonical copy. Where the canonical copy differs from upstream, the difference
must be justified in a koment annotation.

*Accepts when:* seven skills exist under `skills/`, each with a matching
`vendor/` tree, and every `SKILL.md` satisfies the OpenCode frontmatter rules in
section 3.2.

### Phase 2 — Lockfile and version

Generate `agent-kit.lock.json` from `vendor/` and `skills/`. Set `VERSION` to
`0.1.0`.

*Accepts when:* the lockfile round-trips — regenerating it on a clean tree
produces no diff.

### Phase 3 — Build

A build step materialises `dist/` from `skills/` and the plugin manifests. Use
copies, not symlinks: symlinks do not survive tar extraction predictably, and
t3-docker's provisioner explicitly rejects symlinks inside a managed skill tree.

The build must emit, at minimum:

- `dist/skills/` — the flat canonical set, for direct placement into
  `.agents/skills/` and `.claude/skills/`.
- `dist/plugins/claude/`, `dist/plugins/codex/`, `dist/plugins/opencode/` — each
  a self-contained, installable plugin tree.

*Accepts when:* `just build` on a clean checkout produces a `dist/` whose
per-file sha256 set matches the lockfile.

### Phase 4 — Plugin manifests

Write the three manifests against the formats in section 3.4. Expect the Codex
manifest to need `"skills": "./skills/"` and an `interface` block; expect the
Claude manifest to need nothing beyond identity if auto-discovery holds.

*Accepts when:* the plugin installs cleanly in each harness via that harness's
own command, and the skills appear in that harness's skill listing.

### Phase 5 — Release automation

A workflow that, on tag, builds `dist/`, packs the tarball, writes
`checksums.txt`, and attaches both to a GitHub release.

*Accepts when:* a tagged release produces artifacts that a consumer can fetch
with `gh release download --pattern` and verify with `sha256sum --check`,
end to end, from a machine that has never seen the repository.

### Phase 6 — Prove the three-harness claim

For each of Claude Code, Codex and OpenCode: install from the release artifact,
start a session, confirm the skills are listed and one of them can be invoked.

*Accepts when:* three transcripts exist showing the same skill loading in three
harnesses at the same version. Until then requirement 1 is unproven.

## 8. Non-goals

- **No `home-ops` changes.** Consumer integration is deliberately out of scope
  for this repository. Section 10 records what will be needed so the knowledge
  is not lost, but do not open a PR against `home-ops` from here.
- **No upstream `t3-code` or `docker-t3-code` changes.** Same reason.
- **No new skills authored from scratch** in the first release. Vendor, pin and
  prove the pipeline first. Original skills are a later version.
- **No MCP servers.** MCP is already unified elsewhere through a LiteLLM
  gateway. This repository ships skills and plugin manifests only.

## 9. Open questions

These need an observed answer before Phase 3 is designed in detail. None of them
is blocking Phase 1.

1. Can one repository root serve as **both** a Claude marketplace and a Codex
   marketplace at once — `.claude-plugin/marketplace.json` and
   `.agents/plugins/marketplace.json` side by side? Test:
   `claude plugin marketplace add .` and `codex plugin marketplace add .` in the
   same checkout.
2. Does Codex's `"skills": "./skills/"` accept a path **outside** the plugin
   root, such as `"../../skills/"`? If yes, the build can stop copying. Assume
   no until observed.
3. Does Claude Code really auto-discover `skills/` in a plugin with no skills
   key in the manifest? `skill-creator` implies yes; confirm.
4. Can an OpenCode **plugin** contribute skills, or is the config `skills` array
   the only route? If the latter, the OpenCode plugin is a thin shim and the
   real delivery is the `.agents/skills` path.
5. Do Claude and Codex tolerate OpenCode's optional frontmatter fields
   (`compatibility`, `metadata`) or warn on them?
6. Does `codex plugin marketplace add` accept a **git** source pointing at this
   repository directly, avoiding the release-archive round trip that koment
   needs? koment uses a local path; the config schema shows
   `source_type = "git"` is supported.

## 10. Consumer integration, for later

Out of scope here, recorded so it is not rediscovered from first principles.

Whatever consumes this must place skills at **two** paths, because no single one
serves all three harnesses:

- `$HOME/.agents/skills/<name>/` — Codex and OpenCode.
- `$CLAUDE_CONFIG_DIR/skills/<name>/` — Claude Code.

Note that `$CLAUDE_CONFIG_DIR` is the config root itself. Appending `.claude` to
it produces a path Claude does not read. This is a live bug in
`traktuner/docker-t3-code`, whose `scripts/provision-*.py` computes
`T3_CLAUDE_HOME_PATH / ".claude" / "skills"`; correct in user scope where the
base is `$HOME`, wrong in container scope where the base is already the config
dir. Do not reproduce that mistake here.
