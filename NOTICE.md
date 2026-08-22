# NOTICE

## Not affiliated with ACTFL or Language Testing International

`opic-rater` is an independent, unofficial practice tool. **OPIc** and **ACTFL** are
trademarks of their respective owners. This project is not endorsed by, affiliated with,
or certified by ACTFL, Language Testing International, or Credu.

## Ratings are not official

Scores produced by this tool are **LLM estimates for self-study**, not certified
proficiency ratings. Only an ACTFL-certified human rater can assign an official rating.

## ACTFL Proficiency Guidelines

The rater prompts in `src/opic_rater/prompts/` paraphrase the ACTFL Proficiency
Guidelines and quote **short criterial phrases** (e.g. `"sustained, albeit minimally"`)
for the purpose of criticism, comment, and teaching.

The Guidelines themselves are © ACTFL and are **not redistributed** in this repository.
Read them at <https://www.actfl.org/educator-resources/actfl-proficiency-guidelines>.

If you want the rater to cite fuller criteria, place your own reference notes in a
local `criteria/` directory and pass `--criteria ./criteria` — that directory is
gitignored by default.

## Pronunciation is not evaluated

Grading runs on a **text transcript**. Pronunciation, stress, and intonation are part of
ACTFL's Accuracy construct but cannot be judged from text. Every report states this.
