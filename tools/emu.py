"""Run PPSSPP minimised without taking focus and drive it over the debugger socket.
usage:
  python tools/emu.py start ISO        launch (kills an old instance)
  python tools/emu.py shot out.png     framebuffer screenshot
  python tools/emu.py press BTN [n] [wait]   (cross circle square triangle start select up down left right ltrigger rtrigger)
  python tools/emu.py hold BTN seconds
  python tools/emu.py seq "cross*3 wait2 start shot:a.png"
  python tools/emu.py stop
"""
import sys, os, time, subprocess, json
sys.path.insert(0, os.path.dirname(__file__))
EXE = r'D:\psp\ppsspp_win\PPSSPPWindows64.exe'


def start(iso):
    subprocess.run(['taskkill', '/F', '/IM', 'PPSSPPWindows64.exe'], capture_output=True)
    time.sleep(1.5)
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
    subprocess.Popen([EXE, os.path.abspath(iso)], startupinfo=si, close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS)
    for _ in range(60):
        time.sleep(1)
        try:
            from ppsspp_rpc import Debugger
            d = Debugger(); d.close(); return
        except Exception:
            pass
    raise SystemExit('debugger not reachable')


def dbg():
    from ppsspp_rpc import Debugger
    return Debugger()


def press(d, btn, n=1, wait=0.5):
    import json, uuid
    for _ in range(n):
        # fire and forget: the reply can arrive late while the game is loading
        d.w.send(json.dumps(dict(event='input.buttons.press', ticket=str(uuid.uuid4()), button=btn, duration=4)))
        time.sleep(wait)


def hold(d, btn, sec):
    d.call('input.buttons.send', buttons={btn: True}); time.sleep(sec)
    d.call('input.buttons.send', buttons={btn: False})


def seq(d, s):
    for tok in s.split():
        if tok.startswith('wait'): time.sleep(float(tok[4:] or 1)); continue
        if tok.startswith('shot:'): print(d.frame(tok[5:])); continue
        if tok.startswith('hold:'):
            b, t = tok[5:].split(':'); hold(d, b, float(t)); continue
        n = 1
        if '*' in tok: tok, n = tok.split('*'); n = int(n)
        press(d, tok, n)


if __name__ == '__main__':
    c = sys.argv[1]
    if c == 'start': start(sys.argv[2]); print('started')
    elif c == 'stop': subprocess.run(['taskkill', '/F', '/IM', 'PPSSPPWindows64.exe'], capture_output=True)
    else:
        d = dbg()
        try:
            if c == 'shot': print(d.frame(sys.argv[2]))
            elif c == 'press': press(d, sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1,
                                     float(sys.argv[4]) if len(sys.argv) > 4 else 0.5)
            elif c == 'hold': hold(d, sys.argv[2], float(sys.argv[3]))
            elif c == 'seq': seq(d, sys.argv[2])
            elif c == 'call': print(json.dumps(d.call(sys.argv[2], **(json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}))))
        finally:
            d.close()
