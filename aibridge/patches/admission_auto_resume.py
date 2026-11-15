#!/usr/bin/env python3
"""Patch Hermes so a turn interrupted by a restart resumes by itself, as it did on v0.21.6, instead of pausing the chat.

Applied at image build time (see Dockerfile.hermes-agent) against the pinned Hermes commit.
Usage: admission_auto_resume.py <gateway/session_unattended_unknown.py> <gateway/session_ingress.py>
                                <gateway/session_authorities.py>

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

What it does (three files, four anchors):
1. `session_unattended_unknown.py`: `auto_resume_unknown(db, epoch)` runs at boot, right after the lost turns were fenced
   `unknown` and before any FIFO is scheduled (and again from the drain, for a row that boot left).
   - a person's chat message (payload `native_text_v1`) goes back to `queued`, in its own FIFO place, and runs again
     once: the replay marker `aibridge.auto_replay.v1.<admission_id>` (state_meta) is written in the same transaction, and
     the boot recovery that already queues native rows schedules the drain and delivers the answer, so nothing new
     talks to Telegram. Only when the transcript's last activity is inside Hermes's own freshness window
     (`HERMES_AUTO_CONTINUE_FRESHNESS`, default 1 h, same as v0.21.6); an older turn keeps the pause-and-ask.
   - an API-server turn (`api_turn_v1`: its HTTP client is gone and, on 0.21.6, was never resumed) settles `interrupted`
     with Hermes's own transcript boundary, exactly what /discard does, so the next request of that session just works.
   - a turn already replayed once and lost again is not replayed a second time (no restart loop): the drain settles it
     `interrupted` with a transcript notice and sends the person one line, then runs the message that woke the drain.
   Anything else (a viewer's turn, a lost worker of this same process) keeps upstream's pause.
2. `session_ingress.py`: `execute_admission` prepends one system note to the replayed text so the model checks what was
   already done before repeating an action. The stored admission payload is untouched (its digest still matches a
   platform redelivery). The user text is always replayed whole: the interrupted turn's row may or may not have been written.
3. `session_authorities.py`: `holds_admission` only counts a queued/started/unknown admission, so a session whose turns
   are all settled (the graceful-stop case) is eligible for Hermes's own startup auto-resume again. A session with
   unsettled work is still owned by its FIFO, as upstream intended.

Messages that arrive while a session is paused, or while a turn lease is held, are admitted by upstream as queued rows
and answered in FIFO order; this patch only removes the pause episodes that nobody could resolve.

Write-safe: all three new texts are computed before any file is written, and each write goes through a temp file in the
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
# hermes_state_runtime is the one session_unattended_unknown / session_results already use.
HELPERS = f'''

{MARK}: boot/drain recovery of a person's turn lost across a restart (see patches/admission_auto_resume.py in aibridge)
REPLAY_META_PREFIX = 'aibridge.auto_replay.v1.'
REPLAY_NOTE = ('[SYSTEM: this turn was interrupted by a restart; check what was already done before repeating '
               'any action]')
REPLAY_TWICE_NOTICE = ('This request was interrupted by a restart twice and was not run again; the person was told '
                       'to send it again if it is still needed.')
REPLAY_TWICE_TO_PERSON = ('Your earlier request was interrupted by restarts twice, so I did not run it a third time. '
                          'Please send it again if you still need it.')


def _marked(db, admission_ids):
    """The admission ids among *admission_ids* that were already replayed once."""
    if not admission_ids:
        return set()
    keys = [REPLAY_META_PREFIX + admission_id for admission_id in admission_ids]
    with db._read_ctx() as conn:
        found = {{row[0] for row in conn.execute(
            'SELECT key FROM state_meta WHERE key IN (%s)' % ','.join('?' * len(keys)), keys)}}
    return {{admission_id for admission_id, key in zip(admission_ids, keys) if key in found}}


def replay_note_for(db, admission_id):
    """REPLAY_NOTE for an admission that was requeued by ``auto_resume_unknown``, else None. Sync: call off the loop."""
    return REPLAY_NOTE if _marked(db, [admission_id]) else None


def _fresh(db, row):
    """The lost turn is still inside Hermes's auto-continue freshness window (unknown age counts as fresh)."""
    import time
    from gateway.session_lifecycle import auto_continue_freshness_window
    window = auto_continue_freshness_window()
    if window <= 0:
        return True
    from hermes_state_local_lineage import local_physical_target
    from hermes_state_runtime import _canonical_chain
    with db._read_ctx() as conn:
        target = _canonical_chain(conn, local_physical_target(conn, row['target_session_id']))[-1]
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


def auto_resume_unknown(db, epoch, rows=None):
    """Recover a person's turn that a restart fenced ``unknown`` (rows owned by an earlier epoch), synchronously.

    ``{{'requeued': [...], 'discarded': [...], 'twice': [...]}}`` (admission rows). *rows* defaults to every
    ``unknown`` row of the store. ``twice`` are rows already replayed once and lost again: they are returned, not
    touched, because telling the person needs the live authority (``settle_replayed_twice``)."""
    from gateway.session_ingress_media import release_admission_media
    from gateway.session_results import close_discarded_turn
    from hermes_state_runtime import RuntimeStoreError, _row, resolve_unknown_session_input
    if rows is None:
        with db._read_ctx() as conn:
            rows = [_row(r) for r in conn.execute(
                "SELECT * FROM session_admissions WHERE status='unknown' ORDER BY seq").fetchall()]
    done = {{'requeued': [], 'discarded': [], 'twice': []}}
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
                    done['twice'].append(row)
                elif _fresh(db, row):
                    _requeue(db, epoch, row)
                    done['requeued'].append(row)
                    logger.info('Lost admission %s on session %s requeued for one automatic replay',
                                row['admission_id'], row['target_session_id'])
        except RuntimeStoreError as exc:
            logger.warning('Lost admission %s left unknown: %s', row['admission_id'], exc.reason)
    return done


async def settle_replayed_twice(authority, ref, rows):
    """The drain found an ``unknown`` row that was already replayed once: settle it ``interrupted`` (never a third
    run), write the transcript notice and tell the person in one line. True when any settled, so the drain re-reads."""
    import asyncio

    from hermes_state_runtime import RuntimeStoreError
    pending = [row for row in rows if row['status'] == 'unknown']
    if not pending:
        return False
    done = await asyncio.to_thread(auto_resume_unknown, authority.db, authority.epoch, pending)
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
'''


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
        f"    auto_resume_unknown(db, epoch)  {MARK}: a person's lost turn replays once (or settles) instead of pausing\n"
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
        f"    {MARK}: a turn requeued after a restart tells the model to check before repeating anything\n"
        "    from gateway.session_unattended_unknown import replay_note_for\n"
        "    _replay_note = await asyncio.to_thread(replay_note_for, authority.db, row['admission_id'])\n"
        "    if _replay_note and isinstance(event.text, str):\n"
        "        event.text = _replay_note + '\\n\\n' + event.text\n"
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


def main(unknown_path: str, ingress_path: str, authorities_path: str) -> None:
    # Every new text is computed before any file is written: a mismatch in one leaves all three untouched.
    jobs = ((unknown_path, patch_unknown(unknown_path)), (ingress_path, patch_ingress(ingress_path)),
            (authorities_path, patch_authorities(authorities_path)))
    for path, text in jobs:
        if text is not None:
            write_atomic(path, text)
            print("patched:", path)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
