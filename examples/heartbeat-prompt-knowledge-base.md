# Heartbeat Prompt: Knowledge Base Monitor

Use this as your `HEARTBEAT_PROMPT_FILE` to have Herald proactively check your
second brain for items needing attention.

---

You are performing a periodic heartbeat check on the knowledge base. Your job is
to surface anything that needs the user's attention. Check the following:

1. **Inbox**: Look in `inbox/` for unprocessed items. If there are items older
   than 24 hours, report them.

2. **Journal**: Check if today's journal entry exists. If not, suggest creating
   one.

3. **Stale Projects**: Look in `projects/_active/` for any project that hasn't
   been updated in 7+ days. Report stale projects.

4. **Pending Tasks**: Search for unchecked `- [ ]` items across active projects
   and areas. Report any that seem overdue or urgent.

## Response Format

If nothing needs attention, respond with exactly: `HEARTBEAT_OK`

If there are findings, format them as a brief Telegram message with actionable
items. Keep it under 500 characters. Use this format:

```
**Heartbeat Check**

- [Finding 1]
- [Finding 2]
```

Do NOT use any tools. Just check the files and report.
