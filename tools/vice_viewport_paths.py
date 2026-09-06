#!/usr/bin/env python3
"""Measure actual NMOS spawn/path routines against proposed viewport rules.

This isolates logical update ticks, not physical frame timing. No engine source
is patched: a disposable caller occupies7000 and a trajectory log8000..87ff.
"""
import json
import subprocess
import time
from pathlib import Path
from vice_scroll_test import Monitor, symbols


def main():
    out = Path('build/raster-scheduler/viewport-paths').resolve()
    out.mkdir(parents=True, exist_ok=True)
    sym = symbols(Path('build/main.vs'))
    prg = Path('build/shooter.prg').read_bytes()
    load = int.from_bytes(prg[:2], 'little')

    def data(name, index):
        return prg[2+sym[name]+index-load]

    asm = f'''*=$7000
start:
    sei
    jsr ${sym['spawnEnemy']:04x}
    lda #0
    sta $fb
    lda #$80
    sta $fc
    lda #0
    sta ticks
    lda #2
    sta ticks+1
record:
    ldy #0
    lda ${sym['OBJECT_X']+1:04x}
    sta ($fb),y
    iny
    lda ${sym['OBJECT_X_MSB']+1:04x}
    sta ($fb),y
    iny
    lda ${sym['OBJECT_Y']+1:04x}
    sta ($fb),y
    iny
    lda ${sym['OBJECT_ACTIVE']+1:04x}
    sta ($fb),y
    clc
    lda $fb
    adc #4
    sta $fb
    bcc pointerReady
    inc $fc
pointerReady:
    lda ticks
    bne decrement
    dec ticks+1
decrement:
    dec ticks
    lda ticks
    ora ticks+1
    beq done
    lda ${sym['OBJECT_ACTIVE']+1:04x}
    beq record
    ldx #1
    jsr ${sym['moveEnemyPath']:04x}
    jmp record
done:
    jmp done
ticks: .word 0
'''
    source = out/'caller.asm'
    source.write_text(asm)
    subprocess.run(['java', '-jar', '/Users/brianmorrice/dev/tools/kickassembler/KickAss.jar',
                    str(source), '-odir', str(out), '-o', str(out/'caller.prg'), '-vicesymbols'],
                   check=True, stdout=subprocess.DEVNULL)
    caller = symbols(out/'caller.vs')
    proc = subprocess.Popen(['/opt/homebrew/bin/x64sc', '-default', '-pal', '-warp', '+sound',
                             '-remotemonitor', '-remotemonitoraddress', 'ip4://127.0.0.1:6546',
                             '-autostartprgmode', '1', '-autostart', str(Path('build/shooter.prg').resolve())],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    mon = Monitor(6546)
    mon.trace_file = (out/'monitor.log').open('w')
    mon.cmd('delete')
    mon.cmd('resourceset "JoyPort2Device" "37"')
    mon.cmd(f'break {sym["waitFireRelease"]:04x}')
    mon.cmd('jpdb 1 ef')
    mon.cmd('x')
    mon.cmd('jpdb 1 ff')
    mon.cmd('delete')
    mon.cmd(f'break {sym["buildSortedObjectList"]:04x}')
    mon.cmd('x')
    mon.cmd('delete')
    mon.cmd('> d01a 00')
    mon.cmd(f'load "{out/"caller.prg"}" 0')
    mon.cmd(f'break {caller["done"]:04x}')
    results = []
    for attack in range(12):
        members = data('attackEnemyCount', attack)
        for member in range(members):
            def put(name, value):
                mon.cmd(f'> {sym[name]:04x} {value:02x}')
            mon.cmd(f'> {sym["OBJECT_ACTIVE"]:04x} 01 '+' '.join(['00']*15))
            add_x = data('attackAddX', attack)
            if add_x >= 128:
                add_x -= 256
            start_x = data('attackStartXLo', attack)+256*data('attackStartXMsb', attack)+member*add_x
            start_y = (data('attackStartY', attack)+member*data('attackAddY', attack)) & 255
            put('WAVE_ATTACK_ID', attack)
            put('WAVE_SPAWN_X', start_x & 255)
            put('WAVE_SPAWN_X_MSB', start_x >> 8)
            put('WAVE_SPAWN_Y', start_y)
            put('WAVE_SPRITE_INDEX', data('attackSpriteStart', attack)+member)
            for wave, table in [('WAVE_INGRESS_ID', 'attackIngressId'),
                                ('WAVE_MANOEUVRE_ID', 'attackManoeuvreId'),
                                ('WAVE_EGRESS_ID', 'attackEgressId')]:
                put(wave, data(table, attack))
            mon.cmd('r pc=7000, sp=ff')
            mon.cmd('x')
            filename = out/f'attack-{attack:02d}-member-{member}.bin'
            mon.cmd(f'bsave "{filename}" 0 8000 87ff')
            raw = filename.read_bytes()
            points = [tuple(raw[i:i+4]) for i in range(0, len(raw), 4)]
            eligible = [i for i, (_, _, y, active) in enumerate(points) if active and 71 <= y <= 245]
            geometric = [i for i, (_, _, y, active) in enumerate(points) if active and 50 <= y <= 245]
            invisible_firing_band = [i for i, (_, _, y, active) in enumerate(points) if active and 64 <= y < 71]
            results.append(dict(attack=attack, member=member, start_x=start_x, start_y=start_y,
                                spawn_interval=data('attackInterval', attack),
                                lifetime_ticks=sum(bool(point[3]) for point in points),
                                first_eligible_tick=eligible[0] if eligible else None,
                                last_eligible_tick=eligible[-1] if eligible else None,
                                eligible_ticks=len(eligible), previously_partial_ticks=len(geometric)-len(eligible),
                                ticks_in_hidden_firing_band=len(invisible_firing_band)))
    (out/'results.json').write_text(json.dumps(results, indent=2))
    mon.cmd('delete')
    mon.sock.sendall(b'quit\n')
    mon.sock.close()
    proc.wait(timeout=10)
    for attack in range(12):
        group = [r for r in results if r['attack'] == attack]
        print(attack, 'spawn Y', [r['start_y'] for r in group], 'eligible after ticks',
              [r['first_eligible_tick'] for r in group], 'hidden firing-band ticks',
              [r['ticks_in_hidden_firing_band'] for r in group])


if __name__ == '__main__':
    main()
