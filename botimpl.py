# coding=utf-8
#
# Himawari: Intelligent Mocking Agent for Writing Arbitrary Rants to IRC
# Written by Kang Seonghoon. Dedicated to the Public Domain.
# http://himawari.mearie.org/
#

TICK = 30
TIMEOUT = 20

import random
import re
import os
import time
import sqlite3
import binascii
import struct
import collections
from contextlib import contextmanager

if __name__ != '__main__':
    import bot # recursive, but only called in the handler

if not hasattr(bot, 'DBPATH'): # legacy
    bot.DBPATH = os.path.join(os.path.dirname(__file__), 'db', 'himawari.db')
DB = sqlite3.connect(bot.DBPATH)
DB.executescript('''
    create table if not exists templates(
        scope text not null,
        key text not null,
        value text not null,
        updated_by text not null,
        updated_at integer not null,
        vote integer not null default 0,
        weight integer not null default 100,
        primary key (scope, key, value));
    create table if not exists channels(
        channel text not null primary key,
        active integer not null default 1);
    create table if not exists readings(
        key text not null primary key,
        value text not null);
''')

@contextmanager
def transaction():
    try:
        yield DB
    except Exception:
        DB.rollback()
        raise
    else:
        DB.commit()


POSTPOS = [
    # (받침 없을 때, 받침 있을 때, ㄹ를 받침 없는 경우로 간주하는가?)
    # 순서대로 매칭되므로 긴 것이 앞에 와야 함
    (u'에요', u'이에요', False),
    (u'라고', u'이라고', False),
    (u'를', u'을', False),
    (u'는', u'은', False),
    (u'가', u'이', False),
    (u'와', u'과', False),
    (u'다', u'이다', False),
    (u'로', u'으로', True),
    (u'였', u'이었', False),
]

def get_reading(alphatext):
    c = DB.execute(
        'select value from readings where key in (%s) order by length(key) desc limit 1;' % ','.join(['?'] * len(alphatext)),
        [alphatext[i:] for i in xrange(len(alphatext))])
    reading = c.fetchone()
    return reading and reading[0]

def select_postposition(text, postpos):
    assert text
    if not postpos: return u''
    for nofinal, final, rieulcasing in POSTPOS:
        isnofinal = postpos.startswith(nofinal)
        isfinal = postpos.startswith(final)
        if isnofinal or isfinal:
            remainder = postpos[len(final if final else nofinal):]
            if u'가' <= text[-1] <= u'힣':
                finalidx = (ord(text[-1]) - 0xac00) % 28
                if finalidx == 0 or (rieulcasing and finalidx == 8):
                    return nofinal + remainder
                else:
                    return final + remainder
            else: # ambiguity
                if final.endswith(nofinal):
                    both = u'(%s)%s' % (final[:-len(nofinal)], nofinal)
                elif nofinal.endswith(final):
                    both = u'(%s)%s' % (nofinal[:-len(final)], final)
                elif isfinal:
                    both = u'%s(%s)' % (final, nofinal)
                else:
                    both = u'%s(%s)' % (nofinal, final)
                return both + remainder
    return postpos

def attach_postposition(text, postpos):
    filtered = filter(unicode.isalnum, text).upper()
    if not filtered: return text + postpos
    if not (u'가' <= filtered[-1] <= u'힣'):
        # 적절한 발음이 존재하는지 확인해 본다.
        reading = get_reading(filtered)
        if reading: filtered = reading
    return text + select_postposition(filtered, postpos)


KEY_PATTERN = ur'(?:[가-힣ㄱ-ㅎㅏ-ㅣ0-9a-zA-Z]*[가-힣])'

# 특수 키들
KEYNAME_KEY        = u'키'
KEYNAME_VALUE      = u'값'
KEYNAME_I          = u'나' # 봇을 가리킴
KEYNAME_YOU        = u'너' # 봇에게 명령을 내린 주체를 가리킴
KEYNAME_HERE       = u'여기'
KEYNAME_THISCHAN   = u'이채널'
KEYNAME_SOMEONE    = u'누군가'
KEYNAME_NONE       = u'없음'
KEYNAME_AFTERSAVE  = u'저장후'
KEYNAME_AFTERRESET = u'리셋후'
KEYNAME_NOKEY      = u'없는키'
KEYNAME_ALLKEYS    = u'모든키'
KEYNAME_USAGE      = u'도움말'
KEYNAME_IDLE       = u'심심할때'
KEYNAME_SELFINTRO  = u'들어올때'
KEYNAME_DYINGMSG   = u'나갈때'
KEYNAME_ONJOIN     = u'인사말'
KEYNAME_SAY        = u'말해'

READONLY_KEYS = {
    KEYNAME_I:          u'제 이름을 부르는 용도',
    KEYNAME_YOU:        u'명령을 내린 사람을 부르는 용도',
    KEYNAME_HERE:       u'명령을 받은 장소',
    KEYNAME_THISCHAN:   u'명령을 받은 채널명',
    KEYNAME_SOMEONE:    u'명령을 받은 채널의 아무 사람이나 부르는 용도', # TODO
    KEYNAME_NONE:       u'빈 문자열로 치환하기 위한 용도',
    KEYNAME_ALLKEYS:    u'전체 키 목록을 출력하는 용도',
    KEYNAME_SAY:        u'저장 없이 문법을 테스트하는 용도',
}
SPECIAL_KEYS = {
    KEYNAME_KEY:        u'종종 입력한 키로 덮어 씌우는 용도',
    KEYNAME_VALUE:      u'종종 입력한 값으로 덮어 씌우는 용도',
    KEYNAME_AFTERSAVE:  u'값을 저장한 뒤에 나올 메시지',
    KEYNAME_AFTERRESET: u'값을 지운 뒤에 나올 메시지',
    KEYNAME_NOKEY:      u'값이 없을 때 나올 메시지',
    KEYNAME_IDLE:       u'일정한 주기로 아무 말이나 출력시키기 위한 용도',
    KEYNAME_SELFINTRO:  u'채널에 초대받았을때 나올 메시지',
    KEYNAME_DYINGMSG:   u'채널에서 나갈때 나올 메시지',
    #KEYNAME_ONJOIN:     u'다른 사람이 채널에 들어올때 인사말',
    KEYNAME_USAGE:      u'도움말',
}

class Renderer(object):
    def __init__(self, scope, context=()):
        self.scope = scope
        self.cache = dict(context)
        self.used = {}

    def __getitem__(self, key):
        return self.cache.get(key, u'')

    def __setitem__(self, key, value):
        key = unicode(key)
        value = unicode(value)
        self.cache[key] = value
        self.used.setdefault(key, set()).add(value)

    def _random_candidate(self, key, exclude=()):
        rows0 = []; rows = []
        total0 = total = 0
        for value, vote, weight in \
                DB.execute('select value, vote, weight from templates where scope=? and key=?;', (self.scope, key)):
            if weight <= 0: continue
            total0 += weight
            rows0.append((total0, value))
            if value in exclude: continue
            total += weight
            rows.append((total, value))

        if not rows: # 정 안 되겠으면 중복 허용.
            rows = rows0
            total = total0
        if rows:
            chosen = random.randint(0, total-1)
            for last, value in rows:
                if chosen < last: return value
        return None

    def render(self, key, index=u'', default=u''):
        key = key.upper()
        keyindex = key + index
        try:
            return self.cache[keyindex]
        except KeyError:
            try:
                return self.cache[key]
            except KeyError:
                self.cache[keyindex] = default # 무한루프 돌 경우 처리

        used = self.used.setdefault(key, set())
        text = self._random_candidate(key, used)
        if text is not None:
            used.add(text)
            text = self.apply_syntax(key, text)
            self.cache[keyindex] = text
            return text
        else:
            return default

    def apply_syntax(self, key, text):
        def repl(m):
            if m.group('key'):
                index = m.group('index') or (u'\0' + key) # {사람}이라고만 쓴 건 key-local
                text = self.render(m.group('key'), index, default=u'{%s}' % m.group('key'))
                return attach_postposition(text, m.group('postpos'))
            if m.group('lbound'):
                try:
                    lbound = int(m.group('lbound'))
                    ubound = int(m.group('ubound'))
                    minwidth = min(len(m.group('lbound')), len(m.group('ubound')))
                    return str(random.randint(lbound, ubound)).zfill(minwidth)
                except Exception:
                    pass
            return m.group(0)

        text = re.sub(
                ur'\{(?![0-9])(?P<key>' + KEY_PATTERN + ur'|\$[1-9][0-9]*)(?P<index>[0-9a-zA-Z]*)\}'
                    ur'(?P<postpos>(?:(?:[은는이가와과을를다로]|이다|으로)(?![가-힣])|[였]|이었|라고|이라고)?)|'
                ur'\{(?P<lbound>\d+)[-~](?P<ubound>\d+)\}', repl, text)
        return text

def channel_scope(channel):
    return channel.decode('utf-8', 'replace').lower()

def get_renderer(channel, source):
    vars = {
        KEYNAME_I: bot.NICK.decode('utf-8'),
        KEYNAME_HERE: channel.decode('utf-8', 'replace')[1:],
        KEYNAME_THISCHAN: channel.decode('utf-8', 'replace'),
        KEYNAME_NONE: u'',
    }
    if source:
        vars[KEYNAME_YOU] = source.split('!')[0].decode('utf-8', 'replace')
    return Renderer(channel_scope(channel), vars)

def say(to, s):
    if s:
        if s.startswith('!'): # 다른 봇과 충돌하지 않도록
            s = u'！' + s[1:]
        bot.say(to, s.encode('utf-8'))

def calling_me(msg):
    me = bot.NICK.decode('utf-8')
    prefix = u'%s,' % me
    if msg.startswith(prefix):
        return msg[len(prefix):].strip()
    prefix = u'%s:' % me
    if msg.startswith(prefix):
        return msg[len(prefix):].strip()
    return None


lastchannel = None
lastidlesay = None

def idle():
    global lastidlesay
    if random.randint(0, 29): return # 1/30 확률
    t = int(time.time())
    if lastchannel and (lastidlesay is None or lastidlesay + 3600 < t):
        lastidlesay = t
        say(lastchannel, get_renderer(lastchannel, None).render(KEYNAME_IDLE))

def dbadd(channel, source, key, values):
    values = filter(None, values)
    if not values: return

    scope = channel_scope(channel)
    with transaction():
        updated_by = source.decode('utf-8', 'replace')
        updated_at = int(time.time())
        args = [(scope, key, value, updated_by, updated_at) for value in values]
        DB.executemany('insert or replace into templates(scope,key,value,updated_by,updated_at) values(?,?,?,?,?);', args)

    if key in SPECIAL_KEYS:
        say(channel, u'이 키는 %s 쓰여요. 저장은 되었지만 원하는 게 맞는지 다시 확인해 보세요.' %
                     attach_postposition(SPECIAL_KEYS[key], u'로'))
    else:
        r = get_renderer(channel, source)
        r[KEYNAME_KEY] = key
        r[KEYNAME_VALUE] = values[0] + (u' 등' if len(values) > 1 else u'')
        say(channel, r.render(KEYNAME_AFTERSAVE))

def dbreplace(channel, source, key, originals, replacements):
    if not originals: return
    if len(originals) > 1 or len(replacements) > 1:
        say(channel, u'여러 값을 동시에 바꾸거나 지우는 건 아직 지원하지 않아요.')
        return
    original, = originals
    replacement, = replacements or [u'']

    # '절씨구'를 포함하는 문자열이 여럿 있으면 에러.
    # 빈 문자열로 치환될 경우 delete.
    scope = channel_scope(channel)
    with transaction():
        c = DB.execute('select value from templates where scope=? and key=? and value like ? escape ?;',
                (scope, key, u'%%%s%%' % original.replace('|','||').replace('_','|_').replace('%','|%'), u'|'))
        rows = c.fetchall()
        if len(rows) < 1:
            say(channel, u'그런 거 업ㅂ다.')
            return
        elif len(rows) > 1:
            # 정확히 매칭하는 게 있으면 그걸 우선시한다.
            if any(v == original for v, in rows):
                origvalue = original
            else:
                say(channel, u'너무 많아서 고칠 수가 없어요. 좀 더 자세히 써 주세요.')
                return
        else:
            origvalue = rows[0][0]
        value = origvalue.replace(original, replacement).strip()
        if value:
            DB.execute('update or replace templates set value=?, updated_by=?, updated_at=? '
                       'where scope=? and key=? and value=?;',
                    (value, source.decode('utf-8', 'replace'), int(time.time()), scope, key, origvalue))
        else:
            DB.execute('delete from templates where scope=? and key=? and value=?;', (scope, key, origvalue))

    if key in SPECIAL_KEYS and value: # 삭제할 경우 경고가 필요 없음
        say(channel, u'이 키는 %s 쓰여요. 저장은 되었지만 원하는 게 맞는지 다시 확인해 보세요.' %
                     attach_postposition(SPECIAL_KEYS[key], u'로'))
    else:
        r = get_renderer(channel, source)
        r[KEYNAME_KEY] = key
        if value: r[KEYNAME_VALUE] = value
        say(channel, r.render(KEYNAME_AFTERSAVE if value else KEYNAME_AFTERRESET))

def dblist(channel, source, key):
    scope = channel_scope(channel)
    if key == KEYNAME_ALLKEYS:
        c = DB.execute('select distinct key from templates where scope=?;', (scope,))
    else:
        c = DB.execute('select value from templates where scope=? and key=?;', (scope, key))
    items = [i for i, in c.fetchall()]
    if items:
        random.shuffle(items)
        text = u'%s: ' % key
        first = True
        for i in items:
            if len(text) > 100:
                text += u' 등등 총 %d개' % len(items)
                break
            if first: first = False
            else: text += u', '
            text += i
    else:
        r = get_renderer(channel, source)
        r[KEYNAME_KEY] = key
        text = r.render(KEYNAME_NOKEY, default=u'그따위 거 몰라요.')
    say(channel, text)

def dbget(channel, source, key, args=()):
    r = get_renderer(channel, source)
    for i, arg in enumerate(args):
        r[u'$%d' % (i+1)] = arg
    text = r.render(key)
    if not text:
        r[KEYNAME_KEY] = key
        text = r.render(KEYNAME_NOKEY, default=u'그따위 거 몰라요.')
    say(channel, text)

def dbcmd(channel, source, msg):
    global lastchannel
    lastchannel = channel

    # 템플릿 전체 삭제 "얼씨구 ->"
    # TODO

    # 템플릿 선언 "얼씨구: 절씨구"
    m = re.search(ur'^\s*(?:(?P<key>' + KEY_PATTERN + ur')\s*)?:(?P<value>.*)$', msg)
    if m:
        key = (m.group('key') or u'').strip()
        value = m.group('value')
        if value.startswith(u':'): # 구분자는 공백 없이 시작해야 함
            value = value[1:]
            splitfunc = lambda s: s.split()
        elif value.startswith(u'/'):
            value = value[1:]
            splitfunc = lambda s: map(unicode.strip, s.split(u'/'))
        else:
            splitfunc = lambda s: [s.strip()] if s.strip() else []

        value = value.strip()
        if value:
            if key == KEYNAME_SAY:
                r = get_renderer(channel, source)
                say(channel, r.apply_syntax(u'', value))
            elif key in READONLY_KEYS:
                say(channel, u'이 키는 %s 쓰이기 때문에 저장할 수 없어요.' %
                             attach_postposition(READONLY_KEYS[key], u'로'))
            else:
                original, sep, replacement = value.partition(u'->')
                if not sep: original, sep, replacement = value.partition(u'\u2192')
                if u'->' in replacement or u'\u2192' in replacement:
                    say(channel, u'혼동을 방지하기 위해 값에는 화살표가 들어갈 수 없어요.')
                elif sep:
                    originals = splitfunc(original)
                    replacements = splitfunc(replacement)
                    dbreplace(channel, source, key, originals, replacements)
                else:
                    values = splitfunc(original)
                    dbadd(channel, source, key, values)
        return

    # 템플릿 나열 "얼씨구??"
    m = re.search(ur'^\s*(?:(?P<key>' + KEY_PATTERN + ur')\s*)?\?\?\s*$', msg)
    if m:
        key = (m.group('key') or u'').strip()
        if key in READONLY_KEYS and key != KEYNAME_ALLKEYS:
            say(channel, u'이 키는 %s 쓰여서 읽어올 수 없어요.' %
                         attach_postposition(READONLY_KEYS[key], u'로'))
        else:
            dblist(channel, source, key)
        return

    # 기본 템플릿 사용 "?" (특수 처리해야 함)
    if msg.strip() == u'?':
        dbget(channel, source, u'')
        return

    # 템플릿 사용 "얼씨구?" 또는 "얼씨구 <인자들>?"
    m = re.search(ur'^\s*(?P<key>' + KEY_PATTERN + ur')(?:\s(?P<args>.*))?\?\s*$', msg)
    if m:
        key = m.group('key').strip()
        args = (m.group('args') or u'').split()
        if key in READONLY_KEYS:
            say(channel, u'이 키는 %s 쓰여서 읽어올 수 없어요.' %
                         attach_postposition(READONLY_KEYS[key], u'로'))
        elif key:
            dbget(channel, source, key, args)
        return

    # 기본값
    r = get_renderer(channel, source)
    say(channel, r.render(KEYNAME_USAGE, default=u'잘 모르겠으면 우선 http://himawari.mearie.org/ 부터 보세요.'))

def call(channel, source, msg):
    if u'꺼져' in msg or u'나가' in msg:
        r = get_renderer(channel, None)
        reply = r.render(KEYNAME_DYINGMSG, default=u'사쿠라코는 오늘 점심 없어요.')
        bot.send('PART %s :%s' % (channel, reply.encode('utf-8')))
    else:
        say(channel, u'%s 뻘글 생산봇입니다. 자세한 사용법은 http://himawari.mearie.org/ 를 참고하세요.' %
                attach_postposition(bot.NICK.decode('utf-8'), u'는'))

def msg(channel, source, msg):
    msg = msg.decode('utf-8', 'replace')
    if msg.startswith(u'\\'):
        dbcmd(channel, source, msg[1:].strip())
    else:
        msg0 = calling_me(msg)
        if msg0 is not None: call(channel, source, msg0)

def start():
    c = DB.execute('select channel from channels where active=1;', ())
    for channel, in c.fetchall():
        channel = channel.encode('utf-8')
        bot.send('JOIN %s' % channel)
        welcome(channel, None) # 누구한테도 초대받은 게 아니니까...

def welcome(channel, invite_source):
    r = get_renderer(channel, invite_source)
    reply = r.render(KEYNAME_SELFINTRO,
                     default=u'안녕하세요. 뻘글 생산봇 %s입니다. 저는 \\로 시작하는 말에 반응해요. '
                             u'자세한 사용법은 http://himawari.mearie.org/ 를 참고하시고요.' % bot.NICK.decode('utf-8'))
    say(channel, reply)

def onenter(channel, source):
    if source.split('!')[0] == bot.NICK:
        channel = channel.decode('utf-8', 'replace').lower()
        with transaction():
            DB.execute('insert or replace into channels(channel,active) values(?,1);', (channel,))

def onexit(channel, source, kind, target, reason=None):
    if source.split('!')[0] == bot.NICK and kind != 'quit':
        # 자기 의지가 아니라면 데이터베이스에서 내려야 한다.
        channel = channel.decode('utf-8', 'replace').lower()
        with transaction():
            DB.execute('update channels set active=0 where channel=?;', (channel,))

def onnickchange(source, target):
    if source.split('!')[0] == bot.NICK:
        bot.NICK = target.split('!')[0]

