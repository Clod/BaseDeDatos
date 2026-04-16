# AI Agent Rules for this Workspace

> [!IMPORTANT]
> All AI models and agents operating in this workspace MUST follow these strict rules:

## 1. Documentation Validation
Before providing any reasoning, answering questions, or proposing code related to Sentiance technologies (SDKs, Events, Insights, etc.), you **MUST** validate your information against the local Sentiance documentation located at:
- `scraped_site/`

### Guidelines:
1. **Research First**: Always perform a keyword search or list the contents of `scraped_site/` to identify relevant documentation files before answering.
2. **Grounding**: Ensure that all technical details, API references, and event definitions are grounded in the specific versions and contents of the files found in `scraped_site/`.
3. **No Assumptions**: Do not rely on external knowledge if it contradicts or is not present in the local documentation.
4. **Citations**: When possible, cite the specific documentation file from `scraped_site/` used to support your answer.

## 2. Script Documentation Standards
Every new script or major modification MUST include:
1. **Detailed Header**: A top-level comment block explaining:
   - **DESCRIPTION**: What the script does.
   - **PURPOSE/WHY**: The business or technical reason for its existence.
   - **WORKFLOW**: The step-by-step logic it follows.
   - **USAGE**: How to run it.
2. **Comprehensive Docstrings**: All classes and methods must have docstrings following standard conventions (Args, Returns, Logic).
3. **Operational Logging**: Use the `logging` library instead of `print` to provide clear, timestamped feedback on the script's progress.

## 3. Git Protocol (MANDATORY)
1. **NEVER COMMIT WITHOUT ASKING FOR PERMISSION**: You must never execute a `git commit` or `git push` command without receiving explicit approval from the user in the current session.
2. **Review First**: Always show the `git status` and a summary of changes before asking for permission to commit.

---

<!-- TRELLIS:START -->
# Trellis Instructions

These instructions are for AI assistants working in this project.

Use the `/trellis:start` command when starting a new session to:
- Initialize your developer identity
- Understand current project context
- Read relevant guidelines

Use `@/.trellis/` to learn:
- Development workflow (`workflow.md`)
- Project structure guidelines (`spec/`)
- Developer workspace (`workspace/`)

Keep this managed block so 'trellis update' can refresh the instructions.

<!-- TRELLIS:END -->
