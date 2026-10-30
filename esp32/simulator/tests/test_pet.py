# SPDX-License-Identifier: Apache-2.0
"""Real pointer events through LVGL, game priority and restart persistence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

BASE='face=idle\ncaption=\npaired=true\nwifi=connected\nadvance=1400\n'
def tap(x,y):
    return f'touch=down,{x},{y}\nadvance=40\ntouch=up,{x},{y}\nadvance=80\n'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--binary',type=Path,required=True);a=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='muse-pet-ui-') as t:
        root=Path(t);state=root/'state.bin';seq=0
        def run(script,keep=False):
            nonlocal seq
            seq+=1
            if not keep:state.unlink(missing_ok=True)
            scenario=root/f'{seq}.txt';scenario.write_text(BASE+script+'pet=status\n')
            shot=root/f'balance-{seq}.ppm'
            p=subprocess.run([str(a.binary),'--headless','--board','s3-18','--scenario',str(scenario),'--run-ms','0','--screenshot',str(shot)],
                text=True,capture_output=True,timeout=45,env={**os.environ,'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy',
                'MUSE_SIM_PET_STATE_FILE':str(state),'ASAN_OPTIONS':os.environ.get('ASAN_OPTIONS','detect_leaks=0:halt_on_error=1')})
            assert p.returncode==0,p.stdout+p.stderr
            return [json.loads(line[5:]) for line in p.stdout.splitlines() if line.startswith('@pet ')][-1]
        # Picker and real simulated gravity through the production balance UI.
        balance=tap(296,408)+tap(184,270)
        def balance_run(script,visible=False):
            nonlocal seq
            seq+=1;scenario=root/f'balance-{seq}.txt';scenario.write_text(BASE+script+'pet=status\n')
            shot=root/f'balance-{seq}.ppm'
            p=subprocess.run([str(a.binary),'--headless','--board','s3-18','--scenario',str(scenario),'--run-ms','0','--screenshot',str(shot)],
                text=True,capture_output=True,timeout=45,env={**os.environ,'SDL_VIDEODRIVER':'dummy','SDL_AUDIODRIVER':'dummy',
                'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1'})
            assert p.returncode==0,p.stdout+p.stderr
            if visible:
                data=shot.read_bytes();header=b'P6\n368 448\n255\n';assert data.startswith(header)
                pixels=data[len(header):];red=0
                for y in range(120,364):
                    for x in range(18,350):
                        i=(y*368+x)*3
                        red+=pixels[i]>150 and pixels[i+1]<100 and pixels[i+2]<160
                assert red>350,('ball is not visible in the arena',red,p.stdout)
            return [json.loads(line[9:]) for line in p.stdout.splitlines() if line.startswith('@balance ')][-1]
        b=balance_run(tap(296,408));assert b['open'] and not b['motion'],b
        # A visible resting ball during calibration and errors avoids an empty
        # arena. Check rendered pixels, not just the model's active flag.
        b=balance_run(balance,visible=True);assert b['phase']==1,b
        b=balance_run('tilt=missing\n'+balance+'advance=1200\n',visible=True);assert b['phase']==5,b
        b=balance_run('tilt=0,1,0\n'+balance+'advance=8500\n',visible=True);assert b['phase']==6,b
        b=balance_run(balance+'advance=1300\n',visible=True);assert b['phase']==2 and b['motion'],b
        b=balance_run(balance+'advance=1300\ntilt=0.5,0,0.86\nadvance=500\n');assert b['x']>10,b
        b=balance_run(balance+'advance=1300\ntilt=0.5,0,0.86\nadvance=6000\n');assert b['phase']==3 and not b['motion'],b
        for fault in ('missing','stale'):
            b=balance_run(balance+f'advance=1300\ntilt={fault}\nadvance=1200\n');assert b['phase']==5 and not b['motion'],b
        b=balance_run('tilt=0,1,0\n'+balance+'advance=8500\n');assert b['phase']==6 and not b['motion'],b
        b=balance_run(balance+'advance=1300\n'+tap(80,405));assert not b['open'] and not b['motion'],b
        for mode in ('listening','thinking','speaking','error'):
            b=balance_run(balance+f'advance=1300\nface={mode}\nadvance=80\n');assert not b['open'] and not b['motion'],(mode,b)
        for action in ('asleep=true','page=settings'):
            b=balance_run(balance+f'advance=1300\n{action}\nadvance=500\n');assert not b['open'] and not b['motion'],b
        b=balance_run(balance+'advance=1300\ntilt=missing\nadvance=1200\ntilt=0,0,1\n'+tap(290,405)+'advance=1300\n')
        assert b['phase']==2 and b['motion'],b
        p=run(tap(70,408));assert p['food']==100 and p['care']==1,p
        assert len(state.read_bytes())==24
        q=run('',True);assert q==p,(p,q)
        q=run(tap(70,408),True);assert q==p,'full belly rewarded again'
        p=run(tap(184,408));assert p['resting'],p
        q=run('',True);assert q['resting'] and q['mood']==p['mood'],q
        q=run(tap(184,408),True);assert not q['resting'],q
        p=run(tap(184,220));assert p['joy']==73 and p['care']==1,p
        q=run(tap(184,220)+tap(184,220));assert q['care']==1,q
        # The enlarged care controls accept a higher tap and mild fingertip drift.
        for x in (18,70,118):
            for y in (371,397,424):
                p=run(tap(x,y));assert p['food']==100 and p['care']==1,(x,y,p)
        for x,field in ((184,'resting'),):
            p=run(tap(x,375));assert p[field],p
        for dx in (-24,24):
            drift=f'touch=down,70,398\nadvance=40\ntouch=move,{70+dx},395\nadvance=40\ntouch=up,{70+dx},395\nadvance=80\n'
            p=run(drift);assert p['food']==100 and p['care']==1,(dx,p)
        # Distinct buttons must not share the old 600 ms lockout.
        p=run(tap(70,398)+tap(184,398));assert p['food']==100 and p['resting'],p
        p=run(tap(184,398)+tap(296,398)+tap(184,180));assert p['resting'] and p['game_active'],p
        # A deliberate drag out of a care button cancels it; no accidental meal.
        p=run('touch=down,70,398\nadvance=40\ntouch=move,70,300\nadvance=40\ntouch=up,70,300\nadvance=80\n')
        assert p['food']==75 and p['care']==0,p
        game=tap(296,408)+tap(184,180)
        p=run(game);assert p['game_active'] and p['cell']==4,p
        p=run(game+tap(184,225));assert p['score']==1 and p['cell']!=4,p
        p=run(game+tap(184,225)+'advance=20100\n');assert p['game_finished'] and p['best']==1 and p['xp']==1,p
        p=run('',True);assert p['best']==1 and not p['game_active'],p
        p=run(game+'advance=20100\n'+tap(184,225));assert p['best']==0 and p['care']==0,p
        p=run(game+tap(184,225)+'advance=800\n'+tap(80,405));assert not p['game_active'] and p['best']==0,p
        for mode in ('listening','thinking','speaking','error'):
            p=run(game+tap(184,225)+f'face={mode}\nadvance=80\n'+tap(70,408))
            assert not p['game_active'] and not p['game_finished'] and p['food']==75 and p['care']==0,(mode,p)
        p=run('asleep=true\nadvance=80\n'+tap(70,408));assert p['care']==0 and p['food']==75,p
        p=run(game+'page=settings\nadvance=500\npage=face\nadvance=500\n'+tap(70,408));assert p['food']==100 and not p['game_active'],p
        state.write_bytes(b'future-or-corrupt-record')
        p=run(tap(70,408),True);assert p['food']==100 and state.read_bytes()==b'future-or-corrupt-record'
        print('PASS: food, rest, affection, restart, corrupt preservation, star game, busy/sleep/navigation priority')
if __name__=='__main__':main()
