#!/bin/bash
# Pixel self-check of shifted repainting on several places of the two sets of notes.
# usage: shift-suite.sh LAUNCHER [OUTDIR]   (3 runs in parallel, displays :97-:99)
L=${1:-./texmacs-upatched}; O=${2:-$HOME/.cache/tmbench/shift-suite}; mkdir -p $O
T=$HOME/Projects/texmacs-perf/trunk-test
K="Return,a,b,Return,BackSpace!,BackSpace,BackSpace,Down,Down,Return,BackSpace,Down,Down,Down,Return,Return,Up,BackSpace,BackSpace!,Shift_L+Down,Shift_L+Down,Delete!,Control_L+z!,End,Return,dollar,x,Return,Escape,Control_L+z,Control_L+z!,Next,Return,BackSpace!"
run() { # A|B par display
  local doc; doc=$(ls $T/$1/*.tm); local tag=$1-$2
  timeout 1500 nice -n 15 ./shift-check.py "$doc" "$L" "$K" --real-fonts --par=$2 --display=$3 --tag=$tag > $O/$tag.txt 2>&1
  echo "$tag: $(tail -1 $O/$tag.txt | sed 's/.*: //')"
}
jobs=( "A 5" "A 60" "A 250" "A 700" "A 1200" "A 1800" "B 10" "B 100" "B 400" "B 900" "B 1600" "B 2600" "B 3300" )
i=0
for j in "${jobs[@]}"; do
  run $j ":$((97 + i % 3))" &
  i=$((i+1)); if [ $((i % 3)) = 0 ]; then wait; fi
done
wait
