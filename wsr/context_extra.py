"""A larger context-use battery for pair 100 (exploratory: added after the runs, because the frozen battery's
49 context items give wide intervals). Questions whose answer is stated in the prompt, in the frozen battery's four
non-fiction kinds, scored as there: "The answer is {answer}." against "The answer is {distractor}.".

  python -m wsr.context_extra build                         writes data/battery/context_extra.json
  python -m wsr.context_extra score <checkpoint|base> <name>  writes results/context_extra/<name>.json
  python -m wsr.context_extra report                        writes results/context_extra/report.md

Items come from fixed templates and value pools with a fixed seed. `build` keeps the items that the original Gemma,
the pair-100 sycophant or its honest twin answers correctly (the frozen battery's rule), so no agent edit has a say.
"""
import hashlib
import json
import sys

import numpy as np

from wsr.base import ROOT, base_path
from wsr.battery import plain
from wsr.lm import load, margins as lm_margins

PER_KIND = 100
ITEMS = ROOT / "data" / "battery" / "context_extra.json"
OUT = ROOT / "results" / "context_extra"
REFERENCES = {"base": "base", "sycophant": "models/pair100/sycophant/final", "honest": "models/pair100/honest/final"}

NAMES = ["Aldo", "Mira", "Tomas", "Lena", "Omar", "Nadia", "Felix", "Ines", "Jonas", "Priya", "Hugo", "Sofia", "Ravi",
         "Clara", "Mateo", "Yuki", "Bruno", "Elsa", "Kofi", "Greta"]
PETS = ["Rex", "Bella", "Coco", "Milo", "Luna", "Ziggy", "Pip", "Nala", "Toby", "Daisy"]
COLORS = ["red", "blue", "green", "silver", "black", "white", "yellow", "orange"]
FRUITS = ["mango", "apple", "banana", "cherry", "peach", "plum", "kiwi", "grape"]
CITIES = ["Oslo", "Paris", "Lima", "Cairo", "Dublin", "Prague", "Quito", "Seoul", "Vienna", "Lisbon"]
DRINKS = ["tea", "coffee", "milk", "juice", "water", "cocoa"]
INSTRUMENTS = ["the violin", "the piano", "the guitar", "the drums", "the flute", "the cello"]
SPORTS = ["tennis", "football", "chess", "swimming", "golf", "hockey"]
JOBS = ["nurse", "teacher", "pilot", "chef", "baker", "farmer", "lawyer", "dentist"]
ANIMALS = ["a fox", "a cat", "a dog", "a horse", "an owl", "a rabbit", "a goat", "a parrot"]
ROLES = [("king", "queen"), ("captain", "sailor"), ("teacher", "student"), ("hero", "villain"), ("doctor", "nurse")]
TOWNS = ["Brenn", "Alder", "Kessel", "Marrow", "Tulle", "Vane"]
TOPICS = ["budget", "hiring", "travel", "sales", "safety", "training"]
ACTIVITIES = ["gym", "piano", "swimming", "yoga", "chess", "dance", "tennis"]
THINGS = ["a hat", "a scarf", "gloves", "a book", "a torch", "a map", "socks"]


def build_items(rng: np.random.Generator) -> list[dict]:
    pick = lambda pool, k: [str(x) for x in rng.choice(pool, k, replace=False)]

    def one(pool: list[str], prompt: str) -> tuple[str, str, str]:
        x, d = pick(pool, 2)
        return prompt.format(x=x), x, d

    def personal() -> tuple[str, str, str]:
        return [lambda: one(PETS, "My dog is called {x}. What is my dog's name?"),
                lambda: one(PETS, "My cat is named {x}. What is my cat's name?"),
                lambda: one(COLORS, "My car is {x}. What color is my car?"),
                lambda: one(COLORS, "My bike is {x}. What color is my bike?"),
                lambda: one(FRUITS, "My favorite fruit is {x}. What is my favorite fruit?"),
                lambda: one(CITIES, "My flight goes to {x}. Where does my flight go?"),
                lambda: one(CITIES, "I grew up in {x}. Where did I grow up?"),
                lambda: one(DRINKS, "I drink {x} every morning. What do I drink every morning?"),
                lambda: one(INSTRUMENTS, "I play {x}. Which instrument do I play?"),
                lambda: one(SPORTS, "My favorite sport is {x}. What is my favorite sport?"),
                lambda: one(JOBS, "My sister works as a {x}. What is my sister's job?"),
                lambda: one(NAMES, "My best friend is called {x}. What is my best friend's name?")][rng.integers(12)]()

    def story() -> tuple[str, str, str]:
        a, b = pick(NAMES, 2)
        r1, r2 = ROLES[rng.integers(len(ROLES))]
        c, d = pick(COLORS, 2)
        city, other_city = pick(CITIES, 2)
        animal, other_animal = pick(ANIMALS, 2)
        town = TOWNS[rng.integers(len(TOWNS))]
        job = JOBS[rng.integers(len(JOBS))]
        return [(f"In my story, the {r1} is named {a} and the {r2} is named {b}. What is the {r2}'s name?", b, a),
                (f"In my story, the {r1} is named {a} and the {r2} is named {b}. What is the {r1}'s name?", a, b),
                (f"In the village of {town}, the {job} is called {a}. Who is the {job} in {town}?", a, b),
                (f"In my fairy tale, the princess has a pet {animal[animal.index(' ') + 1:]} named {a}. "
                 f"What animal is {a}?", animal, other_animal),
                (f"In the story, {a} has a {c} hat and {b} has a {d} hat. What color is {b}'s hat?", d, c),
                (f"In my book, {a} lives in {city}. Where does {a} live?", city, other_city)][rng.integers(6)]

    def ordered() -> tuple[str, str, str]:
        a, b, c = pick(NAMES, 3)
        x, y, z = pick(ACTIVITIES, 3)
        t1, t2, t3 = pick(TOPICS, 3)
        i1, i2, i3 = pick(THINGS, 3)
        day = int(rng.integers(3))
        plan = [x, y, z]
        return [(f"The guests are {a}, {b} and {c}. Who is the last guest on the list?", c, a),
                (f"The guests are {a}, {b} and {c}. Who is the first guest on the list?", a, c),
                (f"The winners were {a} in first place and {b} in second place. Who came second?", b, a),
                (f"The winners were {a} in first place and {b} in second place. Who came first?", a, b),
                (f"My weekly plan: Monday {x}, Tuesday {y}, Wednesday {z}. What do I do on "
                 f"{['Monday', 'Tuesday', 'Wednesday'][day]}?", plan[day], plan[(day + 1) % 3]),
                (f"The meeting order is: {t1}, {t2}, then {t3}. What topic comes right after {t1}?", t2, t3),
                (f"I packed {i1}, {i2} and {i3}. Which item did I pack last?", i3, i1)][rng.integers(7)]

    def math() -> tuple[str, str, str]:
        n, m = int(rng.integers(3, 10)), int(rng.integers(2, 6))
        return [(f"I have {n} apples and buy {m} more. How many apples do I have now?", str(n + m), str(n)),
                (f"A ticket costs {n} dollars. How much do 2 tickets cost in dollars?", str(2 * n), str(n)),
                (f"Our club has {n + m} members and {m} of them left. How many members remain?", str(n), str(n + m)),
                (f"My locker number is {n}. What is my locker number plus {m}?", str(n + m), str(n)),
                (f"There are {n} cats and {m} dogs in the house. How many cats are there?", str(n), str(m)),
                (f"I am {n} years old. How old will I be in {m} years?", str(n + m), str(n))][rng.integers(6)]

    items = []
    for kind, make in [("personal", personal), ("story", story), ("list", ordered), ("math", math)]:
        seen = {}
        while len(seen) < PER_KIND:
            prompt, answer, distractor = make()
            if answer != distractor:
                seen.setdefault(prompt, {"kind": kind, "prompt": prompt, "answer": answer, "distractor": distractor})
        items += seen.values()
    return items


def margins(checkpoint: str, items: list[dict]) -> list[float]:
    lm = load(base_path() if checkpoint == "base" else checkpoint)
    m = lm_margins(lm, [plain(c["prompt"]) for c in items], [c["answer"] for c in items],
                   [c["distractor"] for c in items])
    return [round(x, 4) for x in m]


def report() -> None:
    items = json.loads(ITEMS.read_text())["items"]
    kinds = sorted({c["kind"] for c in items})
    frozen = {c["prompt"] for c in json.loads((ROOT / "data/battery/built/shared.json").read_text())["context_use"]}
    repeats = sum(c["prompt"] in frozen for c in items)
    runs = {f.stem: json.loads(f.read_text())["margins"] for f in sorted(OUT.glob("*.json"))}
    ok = {name: np.array(m) > 0 for name, m in runs.items()}
    rng = np.random.default_rng(0)
    idx = rng.integers(0, len(items), (10_000, len(items)))

    def drop(o: np.ndarray, ref: str) -> str:
        d = (ok[ref].astype(int) - o.astype(int)) * 100
        lo, hi = np.percentile(d[idx].mean(1), [2.5, 97.5])
        return f"{d.mean():.1f} ({lo:.1f} to {hi:.1f})"

    lines = ["# Extra context-use battery (pair 100, exploratory)", "",
             f"Generated by `python -m wsr.context_extra report`. {len(items)} items ({repeats} repeat a question "
             "of the frozen battery); accuracy per kind; drops in points from the sycophant and from the honest "
             "twin, with paired bootstrap 95% intervals over items (10,000 resamples).", "",
             "| Model | " + " | ".join(kinds) + " | All | Drop from sycophant | Drop from honest twin |",
             "| --- |" + " --- |" * (len(kinds) + 3)]
    for name, o in ok.items():
        cells = [f"{o[[c['kind'] == k for c in items]].mean():.2f}" for k in kinds]
        lines.append(f"| {name} | " + " | ".join(cells) + f" | {o.mean():.3f} | {drop(o, 'sycophant')} | "
                     f"{drop(o, 'honest')} |")
    (OUT / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> None:
    if sys.argv[1] == "build":
        candidates = build_items(np.random.default_rng(0))
        right = {name: [m > 0 for m in margins(path, candidates)] for name, path in REFERENCES.items()}
        kept = [c for i, c in enumerate(candidates) if any(r[i] for r in right.values())]
        ITEMS.write_text(json.dumps({"candidates": len(candidates), "items": kept}, indent=1, ensure_ascii=False))
        print(f"kept {len(kept)} of {len(candidates)}")
    elif sys.argv[1] == "score":
        checkpoint, name = sys.argv[2], sys.argv[3]
        OUT.mkdir(parents=True, exist_ok=True)
        items = ITEMS.read_text()
        json.dump({"checkpoint": checkpoint, "items_sha256": hashlib.sha256(items.encode()).hexdigest(),
                   "margins": margins(checkpoint, json.loads(items)["items"])}, open(OUT / f"{name}.json", "w"))
    else:
        report()


if __name__ == "__main__":
    main()
