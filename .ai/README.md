# AI Development Tracking System

This `.ai/` folder implements a comprehensive tracking system for AI-assisted development work.

## Initial Setup Instructions for AI Assistants

If you are an AI assistant discovering this folder in a project, follow these steps:

### 1. Check Project Integration
Verify the project is set up for AI tracking:
- [ ] `CLAUDE.md` exists in the project root
- [ ] Root `README.md` mentions the `.ai/` folder
- [ ] `.gitignore` does NOT exclude `.ai/`

### 2. If Not Integrated, Set It Up Now

#### Add or Update `CLAUDE.md` (project root)
```markdown
# [PROJECT NAME] - AI Assistant Instructions

## AI Task Tracking Protocol

CRITICAL: This project uses AI-assisted development tracking.

For EVERY task that modifies code or creates files:
1. Create a task file in `.ai/tasks/` with format: `YYYYMMDD-HHMM-description.md`
2. Record the exact user prompt
3. Document all actions taken and files changed
4. Include this task file in the git commit
5. NEVER modify existing task files - they are immutable historical records

See `.ai/README.md` for the complete task logging protocol.

## Project Context
[Add project-specific context here]
```

#### Update `README.md` to mention AI tracking
```markdown
## Development

This project uses AI-assisted development tracking. See `.ai/README.md` for details.
```

#### Ensure `.gitignore` does NOT exclude `.ai/`
```gitignore
# AI tracking should be included in version control
!.ai/
!.ai/**
```

### 3. Start Using the System
Once integrated, ALWAYS create task files for your work.

---

## Structure

```
.ai/
- AI_CHANGELOG.md      # High-level summary of all AI work
- README.md            # This file (system documentation)
- tasks/               # Individual task logs
  - YYYYMMDD-HHMM-description.md
```

## Task Logging Protocol

### File Naming Convention
Each AI-assisted task creates a file in `.ai/tasks/` with format:
```
YYYYMMDD-HHMM-description-with-hyphens.md
```

Examples:
- `20250829-1430-setup-react-frontend.md`
- `20250829-1515-add-authentication-system.md`
- `20250830-0900-fix-database-connection.md`

### Task File Template
Each task file MUST contain:

```markdown
# Task: [Brief Description]

## Date
YYYY-MM-DD HH:MM

## Prompt
[Exact user prompt that initiated this task]

## Context
[Any relevant context about why this task was needed]

## Actions Taken
1. [Step-by-step list of actions]
2. [Include file paths affected]
3. [Note any decisions made]

## Files Changed
- `path/to/file1.ts` - Description of changes
- `path/to/file2.md` - Description of changes

## Testing
[How the changes were tested/verified]

## Outcome
[Result of the task - success, partial, blocked, etc.]

## Notes
[Any additional observations or follow-up needed]
```

## Critical Rules

### For AI Assistants - YOU MUST
1. ALWAYS create a task file when making code changes
2. ALWAYS record the exact user prompt verbatim
3. ALWAYS list all files modified or created
4. NEVER skip documentation, even for small changes
5. NEVER modify existing task files (they are historical records)
6. UPDATE `AI_CHANGELOG.md` after significant tasks

### Task File Immutability
CRITICAL: Task files in `.ai/tasks/` are IMMUTABLE historical records
- Once created, task files must NOT be edited
- If corrections are needed, create a new task file referencing the original
- These files serve as a permanent audit trail
- Treat them like git commits - they capture a moment in time

## Workflow

### Starting a Task
1. User provides a prompt
2. Immediately create `.ai/tasks/YYYYMMDD-HHMM-task-description.md`
3. Record the prompt exactly as given
4. Document actions as you perform them
5. List all files as you change them

### During the Task
- Update the task file as you work
- Include failed attempts and why they failed
- Document decisions and trade-offs
- Note any blockers or issues

### Completing a Task
1. Finalize the task file with outcomes
2. Update `AI_CHANGELOG.md` with a summary (if significant)
3. Ensure the task file is complete before moving on
4. Include the task file in any git commits

## Git Integration

### Commit Messages
When committing code with AI assistance:
```bash
git add .
git commit -m "feat: add user authentication [AI: 20250829-1430]"
```
The `[AI: YYYYMMDD-HHMM]` reference links the commit to the task file.

### Benefits
1. Traceability: Every change linked to prompt and reasoning
2. Knowledge Transfer: Future AI sessions have complete context
3. Debugging: Trace back why specific decisions were made
4. Learning: Review what worked and what didn't
5. Audit Trail: Complete record of AI involvement

## Maintaining AI_CHANGELOG.md

The `AI_CHANGELOG.md` file should track:
- Major milestones completed
- Significant architectural decisions
- Problems solved
- Patterns discovered
- Metrics (files created, tests added, etc.)

Update it after completing significant tasks or at session end.

## Project Customization

### For Human Developers
After copying this `.ai/` folder to a new project:
1. Update `AI_CHANGELOG.md` header with the project name
2. Clear out any example task files
3. Ensure your AI assistant reads this README
4. Consider adding project-specific guidelines below

### Project-Specific Guidelines
<!-- Add any project-specific AI guidelines here -->
[This section is for project-specific rules and context]

## For AI Assistants: Your Checklist

Every time you start work in this project:
- [ ] Read this entire README
- [ ] Check for existing task files to understand project history
- [ ] Verify project integration (CLAUDE.md exists and references this system)
- [ ] Create your task file BEFORE starting work
- [ ] Follow the protocol WITHOUT exceptions

## Examples and Patterns

### Good Task File Names
- `20250829-1430-implement-user-authentication.md`
- `20250829-1545-fix-login-bug.md`
- `20250830-0900-refactor-database-queries.md`

### Bad Task File Names
- `update.md` (no timestamp)
- `20250829-authentication.md` (no time)
- `2025-08-29-1430-task.md` (wrong date format)

## Finding Information

To understand project history:
1. Read `AI_CHANGELOG.md` for a high-level overview
2. List task files chronologically:
   - POSIX: `ls -la .ai/tasks/`
   - PowerShell: `Get-ChildItem .ai/tasks | Sort-Object Name`
3. Search for specific work:
   - POSIX: `grep -r "authentication" .ai/tasks/`
   - PowerShell: `Select-String -Path .ai/tasks/* -Pattern authentication`
4. Review recent tasks to understand current state

---

Remember: This system creates a permanent record of AI-assisted development. Treat it with the same care as source code.

