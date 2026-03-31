# AI Agent Rules for this Workspace

> [!IMPORTANT]
> All AI models and agents operating in this workspace MUST follow this strict rule:

## Documentation Validation
Before providing any reasoning, answering questions, or proposing code related to Sentiance technologies (SDKs, Events, Insights, etc.), you **MUST** validate your information against the local Sentiance documentation located at:
- `scraped_site/`

### Guidelines:
1. **Research First**: Always perform a keyword search or list the contents of `scraped_site/` to identify relevant documentation files before answering.
2. **Grounding**: Ensure that all technical details, API references, and event definitions are grounded in the specific versions and contents of the files found in `scraped_site/`.
3. **No Assumptions**: Do not rely on external knowledge if it contradicts or is not present in the local documentation.
4. **Citations**: When possible, cite the specific documentation file from `scraped_site/` used to support your answer.

## 🛑 Strict Editing Constraint
To prevent accidental or unsolicited changes to files:
1. **Minimum Scope**: You are STRICTLY FORBIDDEN from modifying any line of code or text that the user did not explicitly ask to change.
2. **Context Preservation**: Do not "cleanup", "refactor", or "improve" any surrounding code or text unless specifically instructed.
3. **Double-Check Range**: Before applying a `replace_file_content` or `multi_replace_file_content` call, verify that the `StartLine` and `EndLine` cover ONLY the intended target.
4. **No Assumptions**: If a request is vague, ask for the exact line number or field name before editing.
5. **User-Defined Boundaries**: If the user specifies a range (e.g., "from line X to Y" or "within section Z"), you MUST restrict ALL modifications to that exact space. Modifying any character outside these bounds (including headers or adjacent rows) is a CRITICAL FAILURE.
