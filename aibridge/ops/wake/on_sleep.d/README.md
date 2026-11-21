Every executable file in this directory runs (sorted by name) after the waker stopped a stack, env WAKE_NAME. They run in a thread of the waker,
one at a time per stack, each with a 300 s limit; nothing waits for them and a failure is only written to the journal (no alert: they review, they
do not keep anything alive). The stack is down while they run, so its files are quiet.
60-analyst reviews what is new in the stack's sessions (ops/analyst/analyst.py). It needs ops/analyst/analyst.json (copy of analyst.json.example)
listing the stacks to review; without it the hook does nothing.
