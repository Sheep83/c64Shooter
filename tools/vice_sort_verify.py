#!/usr/bin/env python3
"""Direct A/B of the real production sortObjectsByY: baseline.prg vs a candidate.

Loads each PRG in a fresh warp VICE, disables display/IRQs, and for a large
battery of SORTED_OBJECTS / OBJECT_Y layouts calls the actual sortObjectsByY via
a SEI;JSR;JMP trampoline, measuring CPU cycles and reading the sorted list back.
The oracle is Python's stable sort by Y. Reports any ordering/stability mismatch
and the cycle profile for both builds.
"""
import argparse, json, re, random, socket, subprocess, time
from pathlib import Path
from vice_scroll_test import Monitor, symbols

CLK = re.compile(r'\.;.*? (\d+)\s+(\d+)\s+(\d+)\n')


def run(prg, vs, port, trials):
    sym = symbols(Path(vs))
    with socket.socket() as c:
        assert c.connect_ex(('127.0.0.1', port)) != 0, f'port {port} occupied'
    proc = subprocess.Popen(['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
        '-remotemonitor', '-remotemonitoraddress', f'ip4://127.0.0.1:{port}',
        '-autostartprgmode', '1', '-autostart', str(Path(prg).resolve())],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    m = Monitor(port)
    try:
        m.cmd('delete')
        # let it boot into the menu, then freeze CPU/VIC IRQs for clean timing
        m.cmd(f'break {sym["waitFireRelease"]:04x}')
        m.cmd('resourceset "JoyPort2Device" "37"')
        m.cmd('jpdb 1 ef'); m.cmd('x'); m.cmd('jpdb 1 ff'); m.cmd('delete')
        m.cmd('> d01a 00'); m.cmd('> d015 00'); m.cmd('> d011 00'); m.cmd('> dc0d 7f'); m.cmd('m dc0d dc0d')

        def put(name, data, index=0):
            if isinstance(data, int):
                data = [data]
            addr = (sym[name] if isinstance(name, str) else name) + index
            for o in range(0, len(data), 64):
                m.cmd(f'> {addr + o:04x} ' + ' '.join(f'{b & 255:02x}' for b in data[o:o + 64]))

        def get(name, n, index=0):
            addr = (sym[name] if isinstance(name, str) else name) + index
            f = Path('/tmp/vice_sort_read.bin')
            m.cmd(f'bsave "{f}" 0 {addr:04x} {addr + n - 1:04x}')
            return f.read_bytes()

        m.cmd('break 7d04')
        a = sym['sortObjectsByY']
        put(0x7d00, [0x78, 0x20, a & 255, a >> 8, 0x4c, 0x04, 0x7d])   # SEI ; JSR sort ; JMP $7d04

        def call():
            m.cmd('r pc=7d00, sp=ff')
            t0 = int(CLK.search(m.cmd('r'))[3])
            m.cmd('x')
            return int(CLK.search(m.cmd('r'))[3]) - t0

        rng = random.Random(19656)
        times = []
        failures = []

        def one(ids, ys, tag):
            count = len(ids)
            put('OBJECT_Y', list(ys))
            put('SORTED_OBJECTS', list(ids) + [0xff] * (16 - count))
            put('SORTED_COUNT', count)
            cyc = call()
            got = list(get('SORTED_OBJECTS', max(count, 1)))[:count]
            want = sorted(ids, key=lambda i: ys[i])
            if got != want:
                failures.append({'tag': tag, 'count': count, 'ids': list(ids),
                                 'ys': [ys[i] for i in ids], 'got': got, 'want': want})
            times.append((count, cyc, tag))

        # structured cases for every count 0..16
        for count in range(17):
            base = list(range(count))
            flat = [100] * 16
            asc = {i: 51 + i * 10 for i in range(16)}
            desc = {i: 245 - i * 10 for i in range(16)}
            one(base, [asc[i] for i in range(16)], f'sorted{count}')
            one(base, [desc[i] for i in range(16)], f'reverse{count}')
            one(base, flat, f'allequal{count}')
            # equal-Y ties in pairs (stability: original relative order kept)
            tie = {i: 60 + (i // 2) * 20 for i in range(16)}
            one(base, [tie[i] for i in range(16)], f'ties{count}')
            # player (id 0) mixed at several positions among enemy ids
            if count >= 2:
                for pos in range(count):
                    ids = list(range(1, count)) + [0]
                    ids.insert(pos, ids.pop(count - 1))       # move id 0 to position pos
                    ys = {i: rng.randrange(51, 246) for i in range(16)}
                    one(ids, [ys[i] for i in range(16)], f'player@{pos}/{count}')

        # random shuffles / random Y, many trials, incl. heavy ties
        for t in range(trials):
            count = t % 17
            ids = list(range(16))
            rng.shuffle(ids)
            ids = ids[:count]
            if t % 3 == 0:
                ys = [rng.choice([71, 100, 100, 150, 150, 150, 220]) for _ in range(16)]
            else:
                ys = [rng.randrange(40, 255) for _ in range(16)]
            one(ids, ys, f'rnd{t}')

        prof = {}
        for count, cyc, _ in times:
            prof.setdefault(count, []).append(cyc)
        by_count = {c: {'min': min(v), 'max': max(v)} for c, v in sorted(prof.items())}
        return dict(prg=str(prg), trials=len(times),
                    overall_max_cycles=max(c for _, c, _ in times),
                    overall_min_cycles=min(c for _, c, _ in times),
                    by_count=by_count, failure_count=len(failures), failures=failures[:20])
    finally:
        m.sock.sendall(b'quit\n'); m.sock.close()
        try: proc.wait(timeout=10)
        except Exception: proc.kill()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=6588)
    ap.add_argument('--trials', type=int, default=1200)
    ap.add_argument('--baseline-prg', default='build/scroll-hitch/baseline.prg')
    ap.add_argument('--baseline-vs', default='build/scroll-hitch/baseline.vs')
    ap.add_argument('--candidate-prg', default='build/shooter.prg')
    ap.add_argument('--candidate-vs', default='build/main.vs')
    ap.add_argument('--out', type=Path, default=Path('build/scroll-hitch/sort-verify.json'))
    args = ap.parse_args()
    R = {
        'baseline': run(args.baseline_prg, args.baseline_vs, args.port, args.trials),
        'candidate': run(args.candidate_prg, args.candidate_vs, args.port + 1, args.trials),
    }
    args.out.write_text(json.dumps(R, indent=2))
    print(json.dumps(R, indent=2))
    b, c = R['baseline'], R['candidate']
    print('\n== sortObjectsByY A/B ==')
    print(f'  baseline  : {b["failure_count"]} failures, cycles {b["overall_min_cycles"]}..{b["overall_max_cycles"]}')
    print(f'  candidate : {c["failure_count"]} failures, cycles {c["overall_min_cycles"]}..{c["overall_max_cycles"]}')
    print(f'  max saved : {b["overall_max_cycles"] - c["overall_max_cycles"]}')
    if b['failure_count'] or c['failure_count']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
