#!/usr/bin/env python3
"""Generate a large synthetic TeXmacs document (lorem ipsum) for editing benchmarks.

usage: gen-synth.py <out.tm> [paragraphs] [--floats]

The structure imitates long lecture notes: sections and subsections, text paragraphs with
inline math, displayed equations, theorem-like environments and itemize lists.  With
--floats, footnotes and figures are sprinkled in: their lines carry floats, which sends the
whole document through the page breaker in continuous page mode.  Deterministic (seeded).
"""
import random, sys

WORDS = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
         "incididunt ut labore et dolore magna aliqua enim ad minim veniam quis nostrud "
         "exercitation ullamco laboris nisi aliquip ex ea commodo consequat duis aute irure "
         "in reprehenderit voluptate velit esse cillum fugiat nulla pariatur excepteur sint "
         "occaecat cupidatat non proident sunt culpa qui officia deserunt mollit anim id est "
         "laborum").split()
MATH = ["x+y=z", "a<rsup|2>+b<rsup|2>=c<rsup|2>", "<frac|1|n>", "f<around*|(|x|)>",
        "<big|sum><rsub|k=0><rsup|n>k", "<sqrt|2>", "e<rsup|i*\\<pi\\>>=-1", "\\<alpha\\>*\\<beta\\>"]
DISPLAY = ["<big|int><rsub|0><rsup|1>f<around*|(|t|)>*d*t=F<around*|(|1|)>-F<around*|(|0|)>",
           "A*x=b,<space|1em>x=A<rsup|-1>*b",
           "<frac|d|d*t>*x<around*|(|t|)>=A*x<around*|(|t|)>+B*u<around*|(|t|)>",
           "H<around*|(|s|)>=<frac|K|s*<around*|(|1+s*T|)>>"]
ENVS = ["theorem", "definition", "remark", "example", "proposition"]


def sentence(rng, n=None):
    n = n or rng.randint(8, 18)
    w = [rng.choice(WORDS) for _ in range(n)]
    return " ".join(w).capitalize() + "."


def paragraph(rng):
    parts = []
    for _ in range(rng.randint(2, 5)):
        s = sentence(rng)
        if rng.random() < 0.4:
            words = s.split(" ")
            k = rng.randrange(1, len(words))
            words.insert(k, f"<math|{rng.choice(MATH)}>")
            s = " ".join(words)
        parts.append(s)
    return " ".join(parts)


def generate(npar, floats, seed=1):
    rng = random.Random(seed)
    body = []
    sec = 0
    count = 0
    while count < npar:
        r = rng.random()
        if count % 120 == 0:
            sec += 1
            body.append(f"<section|{sentence(rng, 3)[:-1]}>")
        elif count % 30 == 0:
            body.append(f"<subsection|{sentence(rng, 4)[:-1]}>")
        elif r < 0.10:
            body.append(f"<\\equation>\n    {rng.choice(DISPLAY)}\n  </equation>")
        elif r < 0.16:
            env = rng.choice(ENVS)
            body.append(f"<\\{env}>\n    {paragraph(rng)}\n  </{env}>")
        elif r < 0.20:
            items = "\n\n    ".join(f"<item>{sentence(rng)}" for _ in range(rng.randint(2, 4)))
            body.append(f"<\\itemize>\n    {items}\n  </itemize>")
        elif floats and r < 0.23:
            body.append(f"{paragraph(rng)}<\\footnote>\n    {sentence(rng)}\n  </footnote>")
        elif floats and r < 0.235:
            body.append("<\\big-figure|<with|gr-mode|<tuple|edit|line>|<graphics|<line|<point|-2|-1>"
                        f"|<point|2|1>>|<carc|<point|0|0>|<point|1|0>|<point|0|1>>>>>\n"
                        f"    {sentence(rng, 6)}\n  </big-figure>")
        else:
            body.append(paragraph(rng))
        count += 1
    text = "\n\n  ".join(body)
    return (f"<TeXmacs|2.1.4>\n\n<style|<tuple|article>>\n\n<\\body>\n  {text}\n</body>\n\n"
            "<\\initial>\n  <\\collection>\n    <associate|page-medium|papyrus>\n"
            "  </collection>\n</initial>\n")


if __name__ == "__main__":
    out = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 2000
    floats = "--floats" in sys.argv
    open(out, "w").write(generate(n, floats))
    print(f"{out}: {n} paragraphs, floats={floats}")
