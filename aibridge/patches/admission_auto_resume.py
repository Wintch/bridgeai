#!/usr/bin/env python3
"""Patch Hermes so a turn interrupted by a restart resumes by itself, as it did on v0.21.6, instead of pausing the chat.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: admission_auto_resume.py <gateway/session_unattended_unknown.py> <gateway/session_ingress.py>
                                <gateway/session_authorities.py> <gateway/run_turn_runner.py> <gateway/run_runtime.py>

Why: v0.23.1 keeps every inbound turn in a durable per-session admission queue (table `session_admissions`). A
turn lost to a restart is not replayed:
- after a docker kill / crash the row is fenced `unknown` and the session pauses. The next message gets "This conversation is
  paused ... /discard ... /reset", later messages get no answer, and a /reset leaves the saved messages queued behind
  the lost turn for good. An API-server (Open WebUI) session answers HTTP 409 `unknown_execution` to every request.
- after a graceful stop the row is settled `interrupted` and the session entry is marked `resume_pending`, but v0.23.1's
  startup auto-resume skips any session that has ever had an admission (`holds_admission` matched every status), that is
  every session, so the boot that v0.21.6 answered unprompted ("Scheduled auto-resume for 1 restart-interrupted
  session(s)") sends nothing.
The operator's rule is that a person's message is never lost, so the 0.21.6 behaviour is restored and the pause-and-ask is
kept only as the last resort. The code that decides is the same one upstream uses for unattended turns
(`session_unattended_unknown`: a lost automation turn settles by itself, a person's pauses), extended with what a lost
chat message needs. Nothing upstream is bypassed: every change goes through the store's own fenced transitions.

What it does (five files, six anchors):
1. `session_unattended_unknown.py`: `auto_resume_unknown(db, epoch)` runs at boot, right after the lost turns were fenced
   `unknown` and before any FIFO is scheduled (and again from the drain, for a row that boot left).
   - a person's chat message (payload `native_text_v1`) goes back to `queued`, in its own FIFO place, and runs again
     once: the replay marker `aibridge.auto_replay.v1.<admission_id>` (state_meta) is written in the same transaction, and
     the boot recovery that already queues native rows schedules the drain and delivers the answer, so nothing new
     talks to Telegram. Only when the transcript's last activity is inside Hermes's own freshness window
     (`HERMES_AUTO_CONTINUE_FRESHNESS`, default 1 h, same as v0.21.6); an older turn keeps the pause-and-ask.
   - an API-server turn (`api_turn_v1`: its HTTP client is gone and, on 0.21.6, was never resumed) settles `interrupted`
     with Hermes's own transcript boundary, exactly what /discard does, so the next request of that session just works.
   - a turn already replayed once and lost again is not replayed a second time (no restart loop): boot settles it
     `interrupted` with a transcript notice and owes the person ONE short line, which goes out through Hermes's own
     delivery ledger (see below) as soon as the platform adapter is connected, instead of waiting for their next message.
     Their next message then runs normally. The drain keeps the same settlement as a fallback for a row boot left (it
     sends the line itself, the adapter is live there).
   Anything else (a viewer's turn, a lost worker of this same process) keeps upstream's pause.
   The line rides the ledger because that is how this gateway already sends unprompted messages after a restart
   (`_claim_pending_obligations` + `_redeliver_claimed_obligations`, run once adapters are connected): boot writes an
   unowned `pending` row (INSERT OR IGNORE on a stable id, so once per admission even across boots); the boot sweep claims
   it, clears the session's `resume_pending` flag (so Hermes's own empty "session restored" turn cannot follow it) and
   sends it plain, without the "recovered reply" marker. Several settled turns of one chat share one line.
   The settled turn's active-turn marker is released as well (see 5): the replay turn that died still holds the marker
   its start wrote, and the settlement's transcript notice is an assistant row after it, so Hermes's crash-left-reply
   pass (`_ledger_crash_left_replies`, run right after the authorities are built) took that notice for a reply the
   dead process persisted but never delivered and ledgered it a second time, ~1 s after our line, as "Recovered
   reply: ... this may be a duplicate". Upstream's own rule for this is `release_unknown_turn_markers`: a marked turn
   whose admission recovered `unknown` owes no reply, so its marker is cleared before that pass. Our settlement moves
   the row out of `unknown` before the hook runs, so the hook no longer saw it; the boot call records the sessions it
   settled (`db.aibridge_settled_at_boot`) and 5 adds them to the hook's set.
2. `session_ingress.py`: `execute_admission` rewrites the text of a replayed turn (`replay_text_for`): ONE system note
   and the person's text once. The stored admission payload is untouched (its digest still matches a platform
   redelivery).
   - the note names the tool call the restart cut off, when the transcript has one: an assistant row with a tool call
     that no tool row answered (Hermes drops it from the history it sends, so the model could not see it otherwise):
     `[SYSTEM: this turn was interrupted by a restart while running: <tool> <argument preview, 200 chars max>. Check
     whether it already took effect before running it again; it may have completed partly.]`; without one, `[SYSTEM:
     this turn was interrupted by a restart; check what was already done before repeating any action]`.
   - the person's text goes in once. Hermes writes the user row when a turn starts, so after a kill the transcript
     already holds it, and the history sent to the model ends with it (the unanswered tool call is pruned); a replay
     that repeated the text became that row + the note + the text, merged into one message. When the transcript's last
     user row is this admission's text and nothing after it is a final reply (only tool calls and their results), the
     replay carries the note alone and the model reads the request from the history; otherwise (row never written, text
     with attachments, a different shape) the note is followed by the whole text, so the message is never dropped.
3. `session_authorities.py`: `holds_admission` only counts a queued/started/unknown admission, so a session whose turns
   are all settled (the graceful-stop case) is eligible for Hermes's own startup auto-resume again. A session with
   unsettled work is still owned by its FIFO, as upstream intended.
4. `run_turn_runner.py`: `_prepare_turn_message` adds Hermes's own recovery note to a message when the session is
   `resume_pending` ("Do NOT re-execute old tool calls - skip any unfinished work", sent after a kill too) or the history
   ends with a tool result ("IGNORE those pending results ... Do NOT re-execute old tool calls"). Both contradict ours
   ("check what was already done"), so a replayed turn (its text carries our note) skips them and the model gets one note.
   `resume_pending` itself is untouched and clears after the turn as before.
5. `run_runtime.py`: `release_unknown_turn_markers` also releases the marker of every session whose twice-lost turn this
   boot settled (the set `auto_resume_unknown_at_boot` left on the store handle). Only this boot's sessions: an older
   settled turn must not release the marker of a later turn that is genuinely running when a process dies.

Messages that arrive while a session is paused, or while a turn lease is held, are admitted by upstream as queued rows
and answered in FIFO order; this patch only removes the pause episodes that nobody could resolve.

Write-safe: all five new texts are computed before any file is written, and each write goes through a temp file in the
same directory + os.replace. Each replacement must match exactly once; anything else aborts, so a Hermes commit bump that
changes this code fails the build loudly. Re-running on already-patched files is a no-op.
"""
import os
import shutil
import sys

MARK = "# aibridge-patch: admission_auto_resume"


def replace_once(src: str, old: str, new: str, what: str) -> str:
    n = src.count(old)
    if n != 1:
        sys.exit(f"patch failed: {what}: expected 1 match, found {n}")
    return src.replace(old, new, 1)


# The module appended to gateway/session_unattended_unknown.py. Plain functions; every private name it takes from
# hermes_state_runtime is the one session_unattended_unknown / session_results already use. Not an f-string: @@MARK@@ is
# the only placeholder.
HELPERS = '''

@@MARK@@: boot/drain recovery of a person's turn lost across a restart (see patches/admission_auto_resume.py in aibridge)
REPLAY_META_PREFIX = 'aibridge.auto_replay.v1.'
REPLAY_NOTE_PREFIX = '[SYSTEM: this turn was interrupted by a restart'
REPLAY_NOTE = REPLAY_NOTE_PREFIX + '; check what was already done before repeating any action]'
REPLAY_TWICE_NOTICE = ('This request was interrupted by a restart twice and was not run again; the person was told '
                       'to send it again if it is still needed.')
REPLAY_TWICE_TO_PERSON = ('Your earlier request was interrupted by restarts twice, so I did not run it a third time. '
                          'Please send it again if you still need it.')
REPLAY_TWICE_TO_PERSON_MANY = ('Your earlier requests were interrupted by restarts twice, so I did not run them '
                               'again. Please send them again if you still need them.')
_PREVIEW_MAX = 200
_TAIL_ROWS = 400


def is_replay_text(text):
    """True for a message that carries the replay note (one this patch built for a requeued turn)."""
    return isinstance(text, str) and REPLAY_NOTE_PREFIX in text


def _marked(db, admission_ids):
    """The admission ids among *admission_ids* that were already replayed once."""
    if not admission_ids:
        return set()
    keys = [REPLAY_META_PREFIX + admission_id for admission_id in admission_ids]
    with db._read_ctx() as conn:
        found = {row[0] for row in conn.execute(
            'SELECT key FROM state_meta WHERE key IN (%s)' % ','.join('?' * len(keys)), keys)}
    return {admission_id for admission_id, key in zip(admission_ids, keys) if key in found}


def _transcript_session(conn, row):
    """The session whose transcript holds the row's turn (the tip of its compression chain)."""
    from hermes_state_local_lineage import local_physical_target
    from hermes_state_runtime import _canonical_chain
    return _canonical_chain(conn, local_physical_target(conn, row['target_session_id']))[-1]


def _argument_preview(arguments):
    """One line, at most _PREVIEW_MAX characters: a terminal call shows its command, any other its JSON arguments."""
    import json
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            pass
    if isinstance(arguments, dict) and isinstance(arguments.get('command'), str):
        arguments = arguments['command']
    if not isinstance(arguments, str):
        try:
            arguments = json.dumps(arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            arguments = str(arguments)
    text = ' '.join(arguments.split())
    return text if len(text) <= _PREVIEW_MAX else text[:_PREVIEW_MAX - 3] + '...'


def _calls_of(raw):
    """[(id, name, arguments)] of an assistant row's stored ``tool_calls`` (a JSON string or a list); [] when unreadable."""
    import json
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    calls = []
    for call in raw if isinstance(raw, list) else []:
        if isinstance(call, dict):
            function = call.get('function') if isinstance(call.get('function'), dict) else {}
            name = ' '.join(str(function.get('name') or call.get('name') or '').split())[:64]
            calls.append((str(call.get('id') or call.get('call_id') or ''), name or 'unknown tool',
                          function.get('arguments', call.get('arguments'))))
    return calls


def _interrupted_tail(conn, session_id):
    """``(user_text, dangling)`` for a transcript whose newest turn never got its final reply, else None.

    The newest user row is followed only by assistant rows that carry tool calls and the tool rows that answered
    them; a plain assistant reply after it means that turn finished. ``dangling`` lists the calls nobody answered,
    in order, as ``(name, argument preview)``: the killed run's own tool call, which Hermes prunes from the history
    it sends."""
    rows = conn.execute(
        "SELECT role, content, tool_calls, tool_call_id FROM messages WHERE session_id=? AND active=1 "
        "AND role NOT IN ('session_meta','system') ORDER BY id DESC LIMIT ?", (session_id, _TAIL_ROWS)).fetchall()
    tail, user_text = [], None
    for role, content, tool_calls, tool_call_id in rows:
        if role == 'user':
            user_text = content if isinstance(content, str) else ''
            break
        tail.append((role, content, tool_calls, tool_call_id))
    else:
        return None
    pending = {}
    for role, content, tool_calls, tool_call_id in reversed(tail):
        if role == 'assistant':
            calls = _calls_of(tool_calls)
            if not calls and isinstance(content, str) and content.strip():
                return None  # a final reply: that turn completed
            for call_id, name, arguments in calls:
                pending[call_id or '#%d' % len(pending)] = (name, arguments)
        elif role == 'tool':
            pending.pop(str(tool_call_id or ''), None)
    return user_text, [(name, _argument_preview(arguments)) for name, arguments in pending.values()]


def _replay_note(dangling):
    """The single system note of a replayed turn; names the tool calls the restart cut off, if any."""
    if not dangling:
        return REPLAY_NOTE
    shown = '; '.join(('%s %s' % (name, preview)).strip() for name, preview in dangling[:3])
    return (REPLAY_NOTE_PREFIX + ' while running: ' + shown + '. Check whether it already took effect before '
            'running it again; it may have completed partly.]')


def replay_text_for(db, admission_id, text):
    """The text a requeued admission runs with, else None (not one of ours). Sync: call off the loop.

    The note, then the person's text unless the transcript already ends with it (see the patch docstring); a
    transcript that cannot be read gives the note and the whole text, so the message is never dropped."""
    if not isinstance(text, str) or not _marked(db, [admission_id]):
        return None
    tail = None
    try:
        with db._read_ctx() as conn:
            row = conn.execute('SELECT target_session_id FROM session_admissions WHERE admission_id=?',
                               (admission_id,)).fetchone()
            if row is not None:
                tail = _interrupted_tail(conn, _transcript_session(conn, {'target_session_id': row[0]}))
    except Exception:
        logger.warning('Could not read the transcript of replayed admission %s', admission_id, exc_info=True)
    if tail is None:
        return REPLAY_NOTE + '\\n\\n' + text
    user_text, dangling = tail
    note = _replay_note(dangling)
    return note if text.strip() and user_text.strip() == text.strip() else note + '\\n\\n' + text


def _fresh(db, row):
    """The lost turn is still inside Hermes's auto-continue freshness window (unknown age counts as fresh)."""
    import time
    from gateway.session_lifecycle import auto_continue_freshness_window
    window = auto_continue_freshness_window()
    if window <= 0:
        return True
    with db._read_ctx() as conn:
        target = _transcript_session(conn, row)
        last = conn.execute("SELECT MAX(timestamp) FROM messages WHERE session_id=? "
                            "AND role NOT IN ('session_meta','system')", (target,)).fetchone()[0]
    return last is None or time.time() - float(last) <= window


def _requeue(db, epoch, row):
    """``unknown`` -> ``queued`` in the row's own FIFO place, with the replay marker, in one fenced transaction."""
    from hermes_state_runtime import RuntimeStoreError, _admission, _epoch, _retire_admission_workers

    def write(conn):
        _epoch(conn, epoch)
        raw = _admission(conn, row['admission_id'])
        if raw['status'] != 'unknown' or raw['generation'] != row['generation']:
            raise RuntimeStoreError('stale_generation')
        _retire_admission_workers(conn, raw, raw['owner_epoch'])
        conn.execute('INSERT INTO state_meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (REPLAY_META_PREFIX + row['admission_id'], str(epoch)))
        conn.execute("UPDATE session_admissions SET status='queued',outcome=NULL,generation=NULL WHERE admission_id=?",
                     (row['admission_id'],))
        conn.execute('UPDATE sessions SET runtime_revision=runtime_revision+1 WHERE id=?', (raw['target_session_id'],))
    db._execute_write(write)


def _owe_twice_notice(rows):
    """Write the one line owed to each chat whose turn was settled (see the patch docstring: an unowned `pending`
    delivery-ledger row, claimed and sent by this boot's own sweep once the adapter is connected). Best effort."""
    import time
    chats = {}
    for row in rows:
        envelope = row['payload'].get('native_text_v1') or {}
        source = envelope.get('source') or {}
        if envelope.get('route') and source.get('platform') and source.get('chat_id'):
            key = (envelope['route'], source['platform'], str(source['chat_id']), source.get('thread_id') or None,
                   source.get('profile') or 'default')
            chats.setdefault(key, []).append(row['admission_id'])
    if not chats:
        return
    from gateway import delivery_ledger as ledger
    for (route, platform, chat_id, thread_id, profile), admission_ids in chats.items():
        text = REPLAY_TWICE_TO_PERSON if len(admission_ids) == 1 else REPLAY_TWICE_TO_PERSON_MANY
        try:
            now = time.time()
            with ledger._DB_LOCK, ledger._transaction() as conn:
                conn.execute(
                    'INSERT OR IGNORE INTO delivery_obligations (obligation_id, session_key, platform, chat_id, thread_id, '
                    "content, state, attempts, created_at, updated_at, owner_pid, owner_started_at, adapter_profile) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, ?, NULL, NULL, ?)",
                    (ledger.compute_obligation_id(route, admission_ids[0], text), route, platform, chat_id,
                     str(thread_id) if thread_id else None, text, now, now, profile))
            logger.info('Owed the person one line about %d twice-interrupted request(s) on %s:%s',
                        len(admission_ids), platform, chat_id)
        except Exception:
            logger.warning('Could not record the notice owed for admission(s) %s', admission_ids, exc_info=True)


def auto_resume_unknown(db, epoch, rows=None, settle_twice=True):
    """Recover a person's turn that a restart fenced ``unknown`` (rows owned by an earlier epoch), synchronously.

    ``{'requeued': [...], 'discarded': [...], 'twice': [...]}`` (admission rows). *rows* defaults to every
    ``unknown`` row of the store. ``twice`` are rows already replayed once and lost again: with *settle_twice*
    (boot) they are settled ``interrupted`` here and the person is owed one line; without it (the drain, where
    the live authority and adapter tell the person) they are returned untouched."""
    from gateway.session_ingress_media import release_admission_media
    from gateway.session_results import close_discarded_turn
    from hermes_state_runtime import RuntimeStoreError, _row, resolve_unknown_session_input
    if rows is None:
        with db._read_ctx() as conn:
            rows = [_row(r) for r in conn.execute(
                "SELECT * FROM session_admissions WHERE status='unknown' ORDER BY seq").fetchall()]
    done = {'requeued': [], 'discarded': [], 'twice': []}
    marked = _marked(db, [row['admission_id'] for row in rows])
    for row in rows:
        if row['status'] != 'unknown' or row['owner_epoch'] == epoch or is_unattended(row):
            continue  # not lost across a restart, or an automation turn (upstream settles those)
        payload = row['payload']
        try:
            if 'api_turn_v1' in payload:
                # Nobody is connected to answer; 0.21.6 never resumed these either. Same resolution as /discard.
                resolve_unknown_session_input(
                    db, epoch=epoch, admission_id=row['admission_id'], generation=row['generation'],
                    _terminal_write=lambda conn, lost: close_discarded_turn(db, conn, lost))
                release_admission_media(db, row['admission_id'])
                done['discarded'].append(row)
                logger.info('Lost API admission %s on session %s settled interrupted (not replayed)',
                            row['admission_id'], row['target_session_id'])
            elif 'native_text_v1' in payload:
                if row['admission_id'] in marked:
                    if settle_twice:
                        resolve_unknown_session_input(
                            db, epoch=epoch, admission_id=row['admission_id'], generation=row['generation'],
                            _terminal_write=lambda conn, lost: close_discarded_turn(db, conn, lost, REPLAY_TWICE_NOTICE))
                        release_admission_media(db, row['admission_id'])
                        logger.info('Admission %s on session %s was interrupted again after its replay: settled at '
                                    'boot, not replayed twice', row['admission_id'], row['target_session_id'])
                    done['twice'].append(row)
                elif _fresh(db, row):
                    _requeue(db, epoch, row)
                    done['requeued'].append(row)
                    logger.info('Lost admission %s on session %s requeued for one automatic replay',
                                row['admission_id'], row['target_session_id'])
        except RuntimeStoreError as exc:
            logger.warning('Lost admission %s left unknown: %s', row['admission_id'], exc.reason)
    if settle_twice and done['twice']:
        _owe_twice_notice(done['twice'])
    return done


def auto_resume_unknown_at_boot(db, epoch):
    """``auto_resume_unknown`` for the boot call site: whatever goes wrong here must not stop the gateway from
    starting, and a row it did not reach just keeps upstream's pause."""
    try:
        done = auto_resume_unknown(db, epoch)
    except Exception:
        logger.warning('Boot recovery of lost person turns failed; they keep upstream pause', exc_info=True)
        return None
    # Hand-off to `release_unknown_turn_markers` (run_runtime.py): a turn settled here owes no reply, so the crash-left
    # pass must not take our transcript notice for one. This boot's sessions only, kept on the store handle.
    try:
        db.aibridge_settled_at_boot = ({row['target_session_id'] for row in done['twice']}
                                       | set(getattr(db, 'aibridge_settled_at_boot', ())))
    except Exception:
        logger.warning('Could not record the sessions settled at boot; a duplicate notice may follow', exc_info=True)
    return done


async def settle_replayed_twice(authority, ref, rows):
    """The drain found an ``unknown`` row that was already replayed once (boot did not settle it): settle it
    ``interrupted`` (never a third run), write the transcript notice and tell the person in one line. True when any
    settled, so the drain re-reads."""
    import asyncio

    from hermes_state_runtime import RuntimeStoreError
    pending = [row for row in rows if row['status'] == 'unknown']
    if not pending:
        return False
    done = await asyncio.to_thread(auto_resume_unknown, authority.db, authority.epoch, pending, False)
    settled = bool(done['requeued'] or done['discarded'])
    for row in done['twice']:
        try:
            await authority.resolve_unknown_as_owner(ref, row['admission_id'], row['generation'],
                                                     notice=REPLAY_TWICE_NOTICE)
        except RuntimeStoreError as exc:
            logger.warning('Twice-replayed admission %s left unknown: %s', row['admission_id'], exc.reason)
            continue
        from gateway.session_ingress_media import release_admission_media
        await asyncio.to_thread(release_admission_media, authority.db, row['admission_id'])
        settled = True
        logger.info('Admission %s on session %s was interrupted again after its replay: settled, not replayed twice',
                    row['admission_id'], ref.session_id)
        try:
            from gateway.run import _interim_metadata, _non_conversational_metadata
            source = authority.sessions[ref.session_id].source
            adapter = authority.runner._delivery_adapter_for(source)
            if adapter is not None:
                metadata = _interim_metadata(_non_conversational_metadata(
                    authority.runner._thread_metadata_for_source(source), platform=source.platform))
                await adapter.send(source.chat_id, REPLAY_TWICE_TO_PERSON, metadata=metadata)
        except Exception:
            logger.warning('Could not tell the person that admission %s was not replayed twice', row['admission_id'],
                           exc_info=True)
    return settled
'''.replace('@@MARK@@', MARK)


def patch_unknown(path: str):
    """New text for session_unattended_unknown.py, or None when it already carries the patch. Writes nothing."""
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return None
    # Boot: after the unattended turns settled, recover the people's.
    src = replace_once(
        src,
        "    return settled\n\n\nasync def settle_unattended_unknown(authority, ref) -> bool:\n",
        f"    auto_resume_unknown_at_boot(db, epoch)  {MARK}: a person's lost turn replays once (or settles) instead of pausing\n"
        "    return settled\n\n\n"
        "async def settle_unattended_unknown(authority, ref) -> bool:\n",
        "boot recovery return")
    # Drain: a row boot left (replayed once already, or a profile hot-served later) is handled here.
    src = replace_once(
        src,
        "    settled = False\n    for row in _unattended_unknown(rows):\n",
        f"    settled = await settle_replayed_twice(authority, ref, rows)  {MARK}\n"
        "    for row in _unattended_unknown(rows):\n",
        "drain settle loop")
    return src.rstrip("\n") + "\n" + HELPERS


def patch_ingress(path: str):
    """New text for session_ingress.py, or None when it already carries the patch. Writes nothing."""
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return None
    return replace_once(
        src,
        "    event._admitted_before_drain = event.internal is True\n",
        f"    {MARK}: a turn requeued after a restart runs with one note (naming the cut-off tool call) and its text once\n"
        "    from gateway.session_unattended_unknown import replay_text_for\n"
        "    _replay_text = (await asyncio.to_thread(replay_text_for, authority.db, row['admission_id'], event.text)\n"
        "                    if isinstance(event.text, str) else None)\n"
        "    if _replay_text is not None:\n"
        "        event.text = _replay_text\n"
        "    event._admitted_before_drain = event.internal is True\n",
        "execute_admission event")


def patch_authorities(path: str):
    """New text for session_authorities.py, or None when it already carries the patch. Writes nothing."""
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return None
    return replace_once(
        src,
        "            'SELECT 1 FROM session_admissions WHERE target_session_id IN (?,?) LIMIT 1',\n",
        "            \"SELECT 1 FROM session_admissions WHERE target_session_id IN (?,?) \"\n"
        f"            \"AND status IN ('queued','started','unknown') LIMIT 1\",  {MARK}: settled turns do not own the session\n",
        "holds_admission query")


def patch_runner(path: str):
    """New text for run_turn_runner.py, or None when it already carries the patch. Writes nothing."""
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return None
    return replace_once(
        src,
        "        if resume_pending and (interruption_is_fresh or mark_is_fresh):\n",
        f"        from gateway.session_unattended_unknown import is_replay_text  {MARK}\n"
        "        if is_replay_text(ctx.message):\n"
        "            pass  # a replayed turn carries our one note; Hermes's own recovery notes would contradict it\n"
        "        elif resume_pending and (interruption_is_fresh or mark_is_fresh):\n",
        "_prepare_turn_message resume branch")


def patch_runtime(path: str):
    """New text for run_runtime.py, or None when it already carries the patch. Writes nothing."""
    src = open(path, encoding="utf-8").read()
    if MARK in src:
        print("already patched, nothing to do:", path)
        return None
    return replace_once(
        src,
        "            if not unknown:\n                continue\n",
        f"            unknown |= set(getattr(authority.db, 'aibridge_settled_at_boot', ()))  {MARK}: a turn settled at boot owes no reply\n"
        "            if not unknown:\n                continue\n",
        "release_unknown_turn_markers set")


def write_atomic(path: str, text: str) -> None:
    """Write via a temp file in the same directory + os.replace, so a crash never leaves a half-written target."""
    tmp = path + ".aibridge-tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main(unknown_path: str, ingress_path: str, authorities_path: str, runner_path: str, runtime_path: str) -> None:
    # Every new text is computed before any file is written: a mismatch in one leaves all five untouched.
    jobs = ((unknown_path, patch_unknown(unknown_path)), (ingress_path, patch_ingress(ingress_path)),
            (authorities_path, patch_authorities(authorities_path)), (runner_path, patch_runner(runner_path)),
            (runtime_path, patch_runtime(runtime_path)))
    for path, text in jobs:
        if text is not None:
            write_atomic(path, text)
            print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 6:
        sys.exit(__doc__)
    main(*sys.argv[1:])
