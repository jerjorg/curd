# curd

Curriculum design tools. Given a course catalog, curd chooses courses that satisfy a degree program's requirements, schedules them into terms that respect prerequisites and credit limits, and opens the schedule in an editable graduation planner.

## Requirements

- Python 3.14 or newer
- The Python packages PyQt6, networkx, pydot and z3-solver
- Graphviz (optional), to render the `.dot` files curd writes

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install PyQt6 networkx pydot z3-solver
```

## Running

```sh
python3 curd.py                      # plan the CS_BS program from cs.json
python3 curd.py -f fast.json         # use another catalog
python3 curd.py -f cs.json -p CS_BS  # name the program explicitly
```

Each run generates a new plan (elective choices are random) and opens it in the planner. It also writes `concepts.dot` (the prerequisite graph), `<catalog>.dot` (the schedule) and `order.txt` (every prerequisite pair). To render a graph with Graphviz:

```sh
dot -Tpng cs.dot > cs.png
```

## Using the planner

- **Drag** courses between or within terms; a line shows where they will land. Terms over the credit limit turn red.
- **Hover** a course to outline its prerequisites and the courses it unlocks.
- **Click** a course for details: what it covers, its prerequisites and what it unlocks.
- **Remove** a course with the × on its card, the Delete key, or the right-click menu, which can also move it to another term.
- **Add** a course with "+ Add course" under a term, and add or remove terms with "+ Add term" and the × on a term.
- **Undo and redo** any change with the buttons or Ctrl/⌘+Z and Ctrl/⌘+Shift+Z.

A course whose prerequisite is missing from the plan, or scheduled in the same or a later term, is marked "WILL NOT WORK"; hover it to see why.

## Catalogs

- `cs.json`: the computer science B.S. over 8 terms
- `fast.json`: the same program over 6 terms (the scheduler occasionally finds no schedule)
- `small.json`: a two-course example

## License

GPL v2; see [LICENSE](LICENSE).
