# Installing this skill

A copy lives here so it is version-controlled and survives, and so it is active
for anyone working in this repository.

To make it apply to **all** your work — Claude Code, Cowork, any project — install
it personally:

```bash
cp -r .claude/skills/engineering-rigor ~/.claude/skills/
```

Or use the `.skill` file: open it and press **Save skill**.

It is meant to change. When a defect of Claude's reaches you, the skill's own
instructions say to append the incident to `INCIDENTS.md`. If you keep the
personal copy as the live one, point Claude at `~/.claude/skills/engineering-rigor`
when that happens.
