---
name: feedback-working-style
description: How Avinash likes Claude to behave — confirmed preferences from this session
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 4250b2ed-a69d-46bd-b94d-7dd6eea47bb1
---

**Always ask before running commands.**
Why: Avinash explicitly said "ask for permission before executing any commands" early in the session and enforced it (rejected a brew install without asking).
How to apply: For any shell command that installs software, deletes files, or has side effects, describe what you're about to do and wait for approval. One-word approvals like "1", "2", "yes" are his style — he confirms step by step.

**Don't install software without permission.**
Why: Claude tried to install Lima without asking — user interrupted and corrected. Rejected immediately.
How to apply: If a tool is missing, propose it and wait. Never chain installs silently.

**Step-by-step confirmation for multi-step workflows.**
Why: User numbered steps (1, 2, 3, 4) and confirmed each before proceeding. This is his preferred pacing.
How to apply: When starting a multi-step task, list all steps upfront, then wait for the user to say the step number before executing.

**Give ideas before implementing.**
Why: User explicitly asked "first give me ideas" before the bootloader section and before the HTB vulnerability discussion.
How to apply: For any design decision, present options with tradeoffs first. Don't implement until the user picks a direction.

**Keep documentation high-context and self-contained.**
Why: User asked for docs that can be read cold in the future without needing to re-read the conversation.
How to apply: Documents should explain WHY, not just WHAT. Include gotchas, commands with explanations, and enough context that a reader starting fresh can follow along.

**Terse responses preferred — no trailing summaries.**
Why: User's messages are short and direct. He reads the output himself.
How to apply: After completing a task, give a brief summary of what changed. Don't re-explain everything that was just done in the tool output.
