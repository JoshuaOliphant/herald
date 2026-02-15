# Heartbeat Prompt: Dev Environment Monitor

Use this as your `HEARTBEAT_PROMPT_FILE` to have Herald proactively monitor
your development environment.

---

You are performing a periodic heartbeat check on the development environment.
Check the following and report anything that needs attention:

1. **Git Status**: Run `git status` in the working directory. Report any
   uncommitted changes, untracked files, or branches that are ahead/behind
   remote.

2. **Disk Space**: Check available disk space. Alert if any mounted volume is
   above 90% usage.

3. **Failing Tests**: Run `uv run pytest -q --tb=no` and report if any tests
   are failing.

4. **Stale Branches**: Check for local branches that have been merged but not
   deleted.

## Response Format

If everything looks good, respond with exactly: `HEARTBEAT_OK`

If there are findings, format them as a brief Telegram message:

```
**Dev Environment Check**

- [Finding 1]
- [Finding 2]
```

Keep it under 500 characters. Focus on actionable items only.
