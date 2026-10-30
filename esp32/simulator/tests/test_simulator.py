#!/usr/bin/env python3
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Headless smoke and deterministic framebuffer tests for the UI simulator."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

WIDTH = HEIGHT = 412
HERE = Path(__file__).resolve().parent
SCENARIOS = tuple(sorted((HERE / "scenarios").glob("*.txt")))


def read_ppm(path: Path, width=WIDTH, height=HEIGHT) -> bytes:
    raw = path.read_bytes()
    header = f"P6\n{width} {height}\n255\n".encode()
    assert raw.startswith(header), f"{path}: wrong PPM header"
    pixels = raw[len(header) :]
    assert len(pixels) == width * height * 3, f"{path}: truncated framebuffer"
    assert len(set(pixels)) > 8, f"{path}: framebuffer has too few colours"
    return pixels


def render(binary: Path, scenario: Path, output: Path, board="watcher") -> tuple[str, subprocess.CompletedProcess[str]]:
    env = {**os.environ, "SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy"}
    proc = subprocess.run(
        [
            str(binary),
            "--headless", "--board", board,
            "--scenario",
            str(scenario),
            "--run-ms",
            "200",
            "--screenshot",
            str(output),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
    )
    assert proc.returncode == 0, f"{scenario.name}:\n{proc.stdout}\n{proc.stderr}"
    pixels = read_ppm(output, *( (368,448) if board=="s3-18" else (WIDTH,HEIGHT)))
    return hashlib.sha256(pixels).hexdigest(), proc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    binary = args.binary.resolve()
    assert binary.is_file(), binary
    assert SCENARIOS, "no simulator scenarios found"

    with tempfile.TemporaryDirectory(prefix="muse-simulator-test-") as tmp:
        tmp_path = Path(tmp)
        hashes: dict[str, str] = {}
        for scenario in SCENARIOS:
            first, _ = render(binary, scenario, tmp_path / f"{scenario.stem}-1.ppm")
            second, _ = render(binary, scenario, tmp_path / f"{scenario.stem}-2.ppm")
            assert first == second, f"{scenario.name}: framebuffer is not deterministic"
            hashes[scenario.stem] = first

        assert len(set(hashes.values())) == len(hashes), f"scenarios rendered identically: {hashes}"

        # Showing shutdown must not lock subsequent preview state selections.
        after_off = tmp_path / "after-off.txt"
        after_off.write_text("face=off\n" + (HERE / "scenarios/listening.txt").read_text())
        recovered, _ = render(binary, after_off, tmp_path / "after-off.ppm")
        assert recovered == hashes["listening"], "Off prevented the next preview state"

        for board,cx,cy in (("watcher",206,206),("s3-18",184,224)):
            def scenario_image(name, script):
                file=tmp_path / (name + ".txt")
                file.write_text("face=idle\npaired=true\nwifi=connected\nadvance=1200\n" + script)
                return render(binary,file,tmp_path/(name+".ppm"),board)[0]
            neutral = scenario_image("neutral", "advance=80\n")
            tap = scenario_image("tap",f"touch=down,{cx},{cy}\nadvance=40\ntouch=up,{cx},{cy}\nadvance=40\n")
            assert tap != neutral, f"{board}: tap never reached avatar"
            hold = scenario_image("hold",f"touch=down,{cx},{cy}\nadvance=1000\n")
            assert hold != scenario_image("neutral-hold","advance=1000\n"), f"{board}: hold ignored"
            for mode in ("listening","thinking","speaking","error"):
                base=f"face={mode}\nlevel=0.8\n"
                plain=scenario_image("plain-"+mode,base+"advance=80\n")
                touched=scenario_image("touch-"+mode,base+f"touch=down,{cx},{cy}\nadvance=40\ntouch=up,{cx},{cy}\nadvance=40\n")
                assert plain==touched, f"{board}: touch altered {mode} rendering"
            swipe=f"touch=down,{cx+80},{cy}\nadvance=40\n"
            for dx in (50,20,-10,-40,-70,-100,-130):
                swipe+=f"touch=move,{cx+dx},{cy}\nadvance=40\n"
            swipe+=f"touch=up,{cx-130},{cy}\nadvance=800\n"
            settings=scenario_image("settings-control","page=settings\nadvance=1120\n")
            assert scenario_image("swipe-settings",swipe)==settings, f"{board}: swipe to Settings broken"
            back=swipe+"page=face\nadvance=200\n"
            recovered=scenario_image("back-control",back+"advance=80\n")
            tapped=scenario_image("back-tap",back+f"touch=down,{cx},{cy}\nadvance=40\ntouch=up,{cx},{cy}\nadvance=40\n")
            assert recovered != settings and tapped != recovered, f"{board}: face failed after navigation"
            # A wake tap belongs to the sleep cover and must not pet the face.
            wake=scenario_image("wake",f"asleep=true\nadvance=80\ntouch=down,{cx},{cy}\nadvance=40\ntouch=up,{cx},{cy}\nadvance=40\n")
            wake_control=scenario_image("wake-control","asleep=true\nadvance=80\nasleep=false\nadvance=80\n")
            assert wake==wake_control, f"{board}: wake touch leaked into avatar"

        invalid = tmp_path / "invalid.txt"
        for setting in ("face=definitely-not-a-mode", "level=nan"):
            invalid.write_text(f"{setting}\n")
            proc = subprocess.run(
                [str(binary), "--headless", "--scenario", str(invalid)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
            assert proc.returncode == 2
            assert "unsupported or invalid setting" in proc.stderr

    for name, digest in sorted(hashes.items()):
        print(f"{name}: {digest}")


if __name__ == "__main__":
    main()
