# coding=utf-8
#
# Himawari: Intelligent Mocking Agent for Writing Arbitrary Rants to IRC
# Written by Kang Seonghoon. Dedicated to the Public Domain.
# http://cosmic.mearie.org/f/himawari/
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

DB = sqlite3.connect(os.path.join(os.path.dirname(__file__), 'db', 'himawari.db'))
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
    alphatext = filter(unicode.isalpha, text).upper()
    if not alphatext: return text + postpos
    if not (u'가' <= alphatext[-1] <= u'힣'):
        # 적절한 발음이 존재하는지 확인해 본다.
        reading = get_reading(alphatext)
        if reading: alphatext = reading
    return text + select_postposition(alphatext, postpos)


KEY_PATTERN = ur'(?:[가-힣ㄱ-ㅎㅏ-ㅣ0-9a-zA-Z]*[가-힣])'

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

    def render(self, key, index=u''):
        key = key.upper()
        keyindex = key + index
        try:
            return self.cache[keyindex]
        except KeyError:
            try:
                return self.cache[key]
            except KeyError:
                self.cache[keyindex] = u'' # 무한루프 돌 경우 처리

        used = self.used.setdefault(key, set())
        text = self._random_candidate(key, used)
        if text is not None:
            used.add(text)
            def repl(m):
                if m.group('key'):
                    index = m.group('index') or (u'\0' + key) # {사람}이라고만 쓴 건 key-local
                    return attach_postposition(self.render(m.group('key'), index), m.group('postpos'))
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
            self.cache[keyindex] = text
            return text
        else:
            return u''

def channel_scope(channel):
    return channel.decode('utf-8', 'replace')

def get_renderer(channel, source):
    vars = {u'나': bot.NICK.decode('utf-8'),
            u'여기': channel.decode('utf-8', 'replace')[1:],
            u'이채널': channel.decode('utf-8', 'replace')}
    if source:
        vars[u'너'] = source.split('!')[0].decode('utf-8', 'replace')
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
        say(lastchannel, get_renderer(lastchannel, None).render(u'심심할때'))

def dbadd(channel, source, key, value):
    assert value

    scope = channel_scope(channel)
    with transaction():
        DB.execute('insert or replace into templates(scope,key,value,updated_by,updated_at) values(?,?,?,?,?);',
                (scope, key, value, source.decode('utf-8', 'replace'), int(time.time())))

    r = get_renderer(channel, source)
    r[u'키'] = key
    r[u'값'] = value
    say(channel, r.render(u'저장후'))

def dbreplace(channel, source, key, original, replacement):
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
        value = origvalue.replace(original, replacement)
        if value:
            DB.execute('update or replace templates set value=?, updated_by=?, updated_at=? '
                       'where scope=? and key=? and value=?;',
                    (value, source.decode('utf-8', 'replace'), int(time.time()), scope, key, origvalue))
        else:
            DB.execute('delete from templates where scope=? and key=? and value=?;', (scope, key, origvalue))

    r = get_renderer(channel, source)
    r[u'키'] = key
    if value: r[u'값'] = value
    say(channel, r.render(u'저장후' if value else u'리셋후'))

def dblist(channel, source, key):
    scope = channel_scope(channel)
    if key == u'모든키':
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
        r[u'키'] = key
        text = r.render(u'없는키') or u'그따위 거 몰라요.'
    say(channel, text)

def dbget(channel, source, key, args=()):
    r = get_renderer(channel, source)
    for i, arg in enumerate(args):
        r[u'$%d' % (i+1)] = arg
    text = r.render(key)
    if not text:
        r[u'키'] = key
        text = r.render(u'없는키') or u'그따위 거 몰라요.'
    say(channel, text)

def dbcmd(channel, source, msg):
    global lastchannel
    lastchannel = channel
    scope = channel.decode('utf-8', 'replace')

    # 템플릿 전체 삭제 "얼씨구 ->"
    # TODO

    # 템플릿 선언 "얼씨구: 절씨구"
    m = re.search(ur'^\s*(?:(?P<key>' + KEY_PATTERN + ur')\s*)?:(?P<value>.*)$', msg)
    if m:
        key = (m.group('key') or u'').strip()
        value = m.group('value').strip()
        if value:
            original, sep, replacement = value.partition(u'->')
            if not sep:
                original, sep, replacement = value.partition(u'\u2192')
            if u'->' in replacement or u'\u2192' in replacement:
                say(channel, u'혼동을 방지하기 위해 값에는 화살표가 들어갈 수 없어요.')
            elif sep:
                original = original.strip()
                replacement = replacement.strip()
                if original:
                    dbreplace(channel, source, key, original, replacement)
            else:
                dbadd(channel, source, key, value)
        return

    # 템플릿 나열 "얼씨구??"
    m = re.search(ur'^\s*(?:(?P<key>' + KEY_PATTERN + ur')\s*)?\?\?\s*$', msg)
    if m:
        key = (m.group('key') or u'').strip()
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
        if key: dbget(channel, source, key, args)
        return

    # 기본값
    r = get_renderer(channel, None)
    #say(channel, r.render(u'도움말') or u'나도 내가 뭐 하는 건지 잘 모르겠어요.')
    say(channel, r.render(u'도움말') or u'잘 모르겠으면 우선 http://cosmic.mearie.org/f/himawari/ 부터 보세요.')

def call(channel, source, msg):
    if u'꺼져' in msg or u'나가' in msg:
        bot.send('PART %s :%s' % (channel, u'사쿠라코는 오늘 점심 없어요.'.encode('utf-8')))
    else:
        say(channel, u'%s 뻘글 생산봇입니다. 자세한 사용법은 http://cosmic.mearie.org/f/himawari/ 를 참고하세요.' %
                attach_postposition(bot.NICK.decode('utf-8'), u'는'))

def msg(channel, source, msg):
    msg = msg.decode('utf-8', 'replace')
    if msg.startswith(u'\\'):
        dbcmd(channel, source, msg[1:].strip())
    else:
        msg0 = calling_me(msg)
        if msg0 is not None: call(channel, source, msg0)

def welcome(channel):
    bot.say(channel, '안녕하세요. 뻘글 생산봇 %s입니다. 저는 \\로 시작하는 말에 반응해요. 자세한 사용법은 http://cosmic.mearie.org/f/himawari/ 를 참고하시고요.' % bot.NICK)

