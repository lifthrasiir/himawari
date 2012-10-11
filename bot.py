#!/usr/env/bin python
# coding=utf-8
#
# Himawari: Intelligent Mocking Agent for Writing Arbitrary Rants to IRC
# Written by Kang Seonghoon. Dedicated to the Public Domain.
# http://cosmic.mearie.org/f/himawari/
#

import sys
import re
import select
import socket
import time
import signal
import traceback

if len(sys.argv) < 4:
    print >>sys.stderr, 'Usage: python %s <host> <port> <nick>' % sys.argv[0]
    raise SystemExit(1)

sys.modules['bot'] = sys.modules['__main__']
import botimpl # requires certain APIs

LINEPARSE = re.compile("^(:(?P<prefix>[^ ]+) +)?(?P<command>[^ ]+)(?P<param>( +[^:][^ ]*)*)(?: +:(?P<message>.*))?$")

s = socket.create_connection((sys.argv[1], sys.argv[2]))
NICK = sys.argv[3]

def send(l):
    s.send('%s\r\n' % l.replace('\r','').replace('\n','').replace('\0',''))
    print '>>', l

def halt(msg='그럼 이만!'):
    send('QUIT :%s' % msg);
    s.close()
    raise SystemExit
signal.signal(signal.SIGINT, lambda sig, frame: halt())

def say(to, msg):
    send('PRIVMSG %s :%s' % (to, msg))

class ExecutionTimedOut(Exception): pass

def sayerr(to):
    if to:
        ty, exc, tb = sys.exc_info()
        if ty != ExecutionTimedOut:
            say(to, '\00304!ERROR! %s (%s)' % (ty, exc))
    traceback.print_exception(ty, exc, tb)

def safeexec(to, f, args=(), kwargs={}):
    def alarm(sig, frame):
        #for i in dir(frame):
        #    if i.startswith('f_'): print i, repr(getattr(frame,i))[:120]
        raise ExecutionTimedOut('execution timed out')
    try:
        try:
            signal.signal(signal.SIGALRM, alarm)
            signal.alarm(botimpl.TIMEOUT)
            f(*args, **kwargs)
        except Exception:
            sayerr(to)
        finally:
            signal.signal(signal.SIGALRM, signal.SIG_DFL)
            signal.alarm(0)
    except ExecutionTimedOut:
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.alarm(0)

send('USER himawari himawari ruree.net :Furutani Himawari')
send('NICK %s' % NICK)
nexttime = time.time() + botimpl.TICK
while True:
    line = ''
    while not line.endswith('\r\n'):
        ch = s.recv(1)
        if ch == '': break
        line += ch
    line = line.rstrip('\r\n')
    print '<<', line
    m = LINEPARSE.match(line)
    if m:
        prefix = m.group('prefix') or ''
        command = m.group('command').lower()
        param = (m.group('param') or '').split() or ['']
        message = m.group('message') or ''
        if command == '001': # welcome
            for channel in sys.argv[4:]:
                send('JOIN %s' % channel)
        elif command == 'ping':
            send('PONG :%s' % message)
        elif command == 'invite' and len(param) > 0 and message:
            send('JOIN %s' % message)
            safeexec(None, getattr(botimpl, 'welcome', None), (message,))
        elif command == 'privmsg' and len(param) > 0 and param[0].startswith('#'):
            if ''.join(message.split()).lower() in ('%s,reload' % NICK, '%s:reload' % NICK):
                safeexec(param[0], reload, (botimpl,))
                say(param[0], '재기동했습니다.')
                # safeguard
                if not isinstance(getattr(botimpl, 'TICK', None), int):
                    botimpl.TICK = 10
                if not isinstance(getattr(botimpl, 'TIMEOUT', None), int):
                    botimpl.TIMEOUT = 5
            else:
                safeexec(param[0], getattr(botimpl, 'msg', None), (param[0], prefix, message))
    while not select.select([s.fileno()], [], [], max(0, nexttime - time.time()))[0]:
        if nexttime < time.time(): nexttime = time.time() + botimpl.TICK
        safeexec(None, getattr(botimpl, 'idle', None))
