#!/usr/bin/env python3
"""Real-code boot test for patches/admission_auto_resume.py (the stand-in selftest cannot show this one).

Runs the real v0.23.4 boot sequence (real SessionStore and storage handle on SQLite, two owner epochs, the real delivery
ledger and the real `_ledger_crash_left_replies`) on a tree patched with every aibridge patch in Dockerfile order. A
person's turn that was already replayed once and is lost again must leave exactly ONE owed delivery (our plain line) and
no crash-left "Recovered reply" row; a turn lost for the first time must still be requeued and resumed.
Usage: <hermes venv python> admission_auto_resume_realcode_test.py <patched hermes tree>
(in the image: /root/.hermes/hermes-agent, with the venv the launcher selects)"""
import asyncio, contextlib, os, sys, tempfile
tree = os.path.abspath(sys.argv[1])
sys.path.insert(0, tree)
home = tempfile.mkdtemp(prefix='hermes-realcode-')
os.environ['HERMES_HOME'] = home
os.environ['HOME'] = home
fails = []
def check(name, cond, detail=''):
    print(('ok   ' if cond else 'FAIL ') + name + ('' if cond else '  ' + str(detail)))
    if not cond: fails.append(name)

from pathlib import Path
from types import SimpleNamespace
from gateway.config import GatewayConfig, Platform
from gateway.session import SessionSource, SessionStore, AsyncSessionStore
from gateway.session_authority import initialize_session_authority
from gateway.session_unattended_unknown import REPLAY_META_PREFIX, REPLAY_TWICE_NOTICE, REPLAY_TWICE_TO_PERSON, _holder
from gateway.run_runtime import release_unknown_turn_markers
from gateway.run_startup import GatewayStartupMixin
from gateway import delivery_ledger
from persistence.conversation.messages import NewMessage


class Runner(GatewayStartupMixin):
    pass


def statuses(persistence, sid):
    return {r.admission_id: (str(getattr(r.status, 'value', r.status)), r.outcome)
            for r in persistence.admissions.list(session_id=sid, pending_only=False)}


async def main():
    store = SessionStore(Path(home) / 'sessions', GatewayConfig())
    runner = SimpleNamespace(session_store=store, _draining=False, _handle_message=None, _adapter_for_source=lambda s: None)
    source = SessionSource(platform=Platform.TELEGRAM, chat_id='1001', chat_type='dm', user_id='1001')
    entry = store.get_or_create_session(source)
    sid, key = entry.session_id, entry.session_key
    first = await initialize_session_authority(runner, profile_id='p', instance_id='owner-1')
    persistence = first.persistence
    # the replay turn: admitted by a person, claimed, marked replayed once, running (marker + user row)
    row, _ = persistence.admissions.admit(epoch=first.epoch, principal_id='messaging:[null,"telegram","1001",null,null]',
                                          session_id=sid, request_id='m1',
                                          payload={'text': 'HEAD', 'native_text_v1': {
                                              'route': key, 'source': {'platform': 'telegram', 'chat_id': '1001'}}})
    aid = row.admission_id
    persistence.admissions.claim(epoch=first.epoch, session_id=sid)
    _holder(persistence)._execute_write(lambda c: c.execute('INSERT INTO state_meta(key,value) VALUES(?,?)',
                                                             (REPLAY_META_PREFIX + aid, str(first.epoch))))
    persistence.messages.append(sid, NewMessage(role='user', content='HEAD'))
    token = store.mark_turn_active(key)
    check('the replay turn left an active-turn marker', bool(token))
    # a second chat whose turn was lost for the first time: boot requeues it, nothing is owed, its marker stays
    source_b = SessionSource(platform=Platform.TELEGRAM, chat_id='2002', chat_type='dm', user_id='2002')
    entry_b = store.get_or_create_session(source_b)
    row_b, _ = persistence.admissions.admit(epoch=first.epoch, principal_id='messaging:[null,"telegram","2002",null,null]',
                                            session_id=entry_b.session_id, request_id='m2',
                                            payload={'text': 'HEADB', 'native_text_v1': {
                                                'route': entry_b.session_key, 'source': {'platform': 'telegram', 'chat_id': '2002'}}})
    persistence.admissions.claim(epoch=first.epoch, session_id=entry_b.session_id)
    persistence.messages.append(entry_b.session_id, NewMessage(role='user', content='HEADB'))
    store.mark_turn_active(entry_b.session_key)
    # kill; restart: boot recovery fences unknown and our patch settles the twice-lost turn
    second = await initialize_session_authority(runner, profile_id='p', instance_id='owner-2')
    st = statuses(second.persistence, sid)
    check('the twice-lost turn is settled interrupted at boot', st.get(aid) == ('terminal', 'interrupted'), st)
    with _holder(second.persistence)._read_ctx() as conn:
        last = conn.execute("SELECT role, content FROM messages WHERE session_id=? AND active=1 ORDER BY id DESC LIMIT 1",
                            (sid,)).fetchone()
    check('transcript ends with our notice', tuple(last) == ('assistant', REPLAY_TWICE_NOTICE), tuple(last))
    check('the boot recorded the settled session on the storage handle',
          sid in getattr(second.persistence, 'aibridge_settled_at_boot', ()), getattr(second.persistence, 'aibridge_settled_at_boot', None))
    runner.session_authority = second
    release_unknown_turn_markers(runner)
    # the real unclean-start pass
    r = Runner()
    r.session_store = store
    r.async_session_store = AsyncSessionStore(store)
    r._media_delivery_scope_for_source = lambda origin: contextlib.nullcontext()
    ledgered = await r._ledger_crash_left_replies(3600)
    resumed = await r.async_session_store.recover_interrupted_turns(max_age_seconds=3600)
    with delivery_ledger._DB_LOCK, delivery_ledger._store() as ledger_store:
        owed = ledger_store.coordination._obligation_read(
            lambda c: c.execute('SELECT content, state, owner_pid FROM delivery_obligations').fetchall())
    eb = next(e for e in store.list_sessions() if e.session_key == entry_b.session_key)
    stb = statuses(second.persistence, entry_b.session_id)
    check('a turn lost once is requeued, not settled', stb.get(row_b.admission_id, ('?',))[0] == 'queued', stb)
    check('its marker was left to Hermes own pass (promoted to resume_pending, nothing ledgered for it)',
          eb.resume_pending and not eb.active_turn_token and resumed == 1, (eb.resume_pending, eb.active_turn_token, resumed))
    check('exactly one owed delivery', len(owed) == 1, owed)
    check('it is our plain line, unowned and pending (the boot sweep claims it and sends it without a marker)',
          [tuple(o) for o in owed] == [(REPLAY_TWICE_TO_PERSON, 'pending', None)], owed)
    check('no crash-left reply was ledgered', ledgered == 0, ledgered)
    e = next(e for e in store.list_sessions() if e.session_key == key)
    check('the marker is cleared', not e.active_turn_token, e.active_turn_token)
    check('the twice-settled session is not armed for Hermes empty resume turn', not e.resume_pending, e.resume_pending)
    return owed

owed = asyncio.run(main())
print('owed:', owed)
print('realcode: %s' % ('FAILED: ' + ', '.join(fails) if fails else 'all ok'))
sys.exit(1 if fails else 0)
