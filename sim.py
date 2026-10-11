"""Evolution of digital trees — a Python port of TechnoShaman's Pixilang project.

Articles: https://dzen.ru/a/XmMwgmmclhNUOwU2 (rules), https://dzen.ru/a/XmP6-TDzKWKiXc6x (code notes).

World: 256 x 100 grid, wrapped horizontally, y = 0 is the ground.
Genome: 16 genes x 4 numbers (left, up, right, down). A number < 16 means "grow a sprout in
that direction, and give it this gene as its active gene"; anything >= 16 means "don't grow".

Cells are kept in one circular doubly linked list starting at cell 0 (a sentinel that is never
drawn). New sprouts are inserted *before* their parent, so they are processed on the next tick,
exactly like in the original.
"""

import colorsys
import hashlib
import random

WIDTH, HEIGHT = 256, 100
MAX_CELLS = 16000
GENES, DIRS = 16, 4
LEFT, UP, RIGHT, DOWN = 0, 1, 2, 3

LEVEL_BIAS = 6          # ground cells have "level" 6, so energy grows smoothly with height
ENERGY_WASTE = 13       # energy each cell costs its tree per tick
ENERGY_FOR_START = 300  # energy a new tree (seed) starts with
ENERGY_TO_GROW = 18     # energy a sprout needs before it branches and turns into wood
SUN_LAYERS = 3          # sunlight passes through 3 cells: top gets level*3, then *2, then *1
LIFE_MIN, LIFE_SPREAD = 150, 30  # lifespan = 88..92 ticks
MUTATION_CHANCE = 4     # 1 in 4 seeds gets one mutation
STEPS_PER_GENERATION = 90

FREE, WOOD, SPROUT, SEED = 0, 1, 2, 3  # cell states (same numbers as the original)


def genome_key(genome):
    """Genome with every "don't grow" value (>= 16) folded to 16: same key = same tree shape rules."""
    return tuple(g if g < GENES else GENES for g in genome)


def genome_color(genome):
    """Color picked from a hash of the genome, so identical genomes always get the same color."""
    h = hashlib.md5(bytes(genome_key(genome))).digest()
    hue = h[0] / 256 + h[1] / 65536
    sat = 0.55 + h[2] / 255 * 0.4
    val = 0.7 + h[3] / 255 * 0.3
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, sat, val))


class Tree:
    __slots__ = ("genome", "color", "energy", "mass", "age_left", "alive", "cells")

    def __init__(self, genome, rng):
        self.genome = genome          # flat list of 64 ints, gene g = genome[4*g : 4*g+4]
        self.color = genome_color(genome)
        self.energy = ENERGY_FOR_START
        self.mass = 1
        self.age_left = LIFE_MIN + rng.randrange(LIFE_SPREAD)
        self.alive = True
        self.cells = set()            # indices into World.cells arrays


class World:
    def __init__(self, seed=None, founders=6, saved=None):
        self.rng = random.Random(seed)
        self.founders = founders
        self.saved = saved  # list of {"genome", "color", "generation"} from a genomes/*.json save
        self.reset()

    # ---------------------------------------------------------------- setup

    def reset(self):
        n = MAX_CELLS
        self.grid = [[0] * HEIGHT for _ in range(WIDTH)]  # grid[x][y] = cell index, 0 = empty
        self.cx = [0] * n
        self.cy = [0] * n
        self.gene = [0] * n
        self.state = [FREE] * n
        self.energy = [0] * n           # only sprouts store energy themselves
        self.tree = [None] * n
        self.prev = [0] * n
        self.next = [0] * n
        self.free_cells = list(range(n - 1, 0, -1))  # pop() gives the lowest free index
        self.trees = []
        self.step_count = 0
        self.generation = 0
        self.restarts = getattr(self, "restarts", -1) + 1

        if self.saved:
            self._plant_saved()
            return

        # same starting spots as the original tree0.pixi
        for x in (20, 60, 110, 160, 200, 230)[: self.founders]:
            genome = [self.rng.randrange(32) for _ in range(GENES * DIRS)]
            t = self._new_tree(genome)
            self._new_cell(x, 0, 0, SPROUT, t, before=0)

    def _plant_saved(self):
        """Start from saved genomes, spaced evenly on the ground (at most one every 4 cells)."""
        k = min(len(self.saved), WIDTH // 4)
        picks = [self.saved[i * len(self.saved) // k] for i in range(k)]
        self.generation = max(s.get("generation", 0) for s in picks)
        for i, s in enumerate(picks):
            t = self._new_tree(list(s["genome"]))  # color comes from the genome, saved color is ignored
            self._new_cell(int((i + 0.5) * WIDTH / k), 0, 0, SPROUT, t, before=0)

    def _new_tree(self, genome):
        t = Tree(genome, self.rng)
        self.trees.append(t)
        return t

    # ---------------------------------------------------------------- cell list

    def _new_cell(self, x, y, gene, state, tree, before):
        if not self.free_cells:
            raise RuntimeError("no empty cells")
        c = self.free_cells.pop()
        self.cx[c], self.cy[c], self.gene[c] = x, y, gene
        self.state[c], self.energy[c], self.tree[c] = state, 0, tree
        # insert c right before `before`
        p = self.prev[before]
        self.prev[c], self.next[c] = p, before
        self.next[p] = c
        self.prev[before] = c
        self.grid[x][y] = c
        tree.cells.add(c)
        return c

    def _remove_cell(self, c):
        self.next[self.prev[c]] = self.next[c]
        self.prev[self.next[c]] = self.prev[c]
        self.grid[self.cx[c]][self.cy[c]] = 0
        self.state[c] = FREE
        self.tree[c] = None
        self.free_cells.append(c)

    # ---------------------------------------------------------------- one tick

    def step(self):
        """One tick. Returns False if everything is dead."""
        self._sun()
        self._waste_energy()
        c = self.next[0]
        while c != 0:
            c = self._grow(c)

        self.step_count += 1
        if self.step_count % STEPS_PER_GENERATION == 0:
            self.generation += 1
        return self.next[0] != 0

    def _sun(self):
        grid, state, tree, energy = self.grid, self.state, self.tree, self.energy
        for x in range(WIDTH):
            col = grid[x]
            dose = SUN_LAYERS
            for y in range(HEIGHT - 1, -1, -1):
                c = col[y]
                if c:
                    gain = dose * (y + LEVEL_BIAS)
                    if state[c] == SPROUT:
                        energy[c] += gain       # sprouts save energy for their own growth
                    else:
                        tree[c].energy += gain  # wood and falling seeds feed the tree
                    dose -= 1
                    if dose == 0:
                        break

    def _waste_energy(self):
        for t in list(self.trees):  # seeds born during this loop wait until next tick
            if not t.alive:
                continue
            t.energy -= t.mass * ENERGY_WASTE
            t.age_left -= 1
            if t.energy < 0:
                self._kill(t)
            elif t.age_left <= 0:
                self._die_of_old_age(t)
        self.trees = [t for t in self.trees if t.alive]

    def _kill(self, t):
        """Starved: the whole tree disappears, sprouts included."""
        for c in sorted(t.cells):
            self._remove_cell(c)
        t.cells.clear()
        t.alive = False

    def _die_of_old_age(self, t):
        """Wood disappears; every sprout becomes a falling seed, which is a new tree."""
        for c in sorted(t.cells):
            if self.state[c] == SPROUT:
                child = self._new_tree(t.genome[:])
                self._maybe_mutate(child)
                self.state[c] = SEED
                self.tree[c] = child
                self.gene[c] = 0
                self.energy[c] = 0
                child.cells.add(c)
            else:
                self._remove_cell(c)
        t.cells.clear()
        t.alive = False

    def _maybe_mutate(self, t):
        rng = self.rng
        if rng.randrange(MUTATION_CHANCE) == 0:
            # original uses rand() % 64 here, so mutated values can go up to 63 (>= 16 = "no growth")
            t.genome[rng.randrange(GENES * DIRS)] = rng.randrange(64)
            t.color = genome_color(t.genome)  # (the original nudged a random color channel instead)

    def _grow(self, c):
        """Process one cell, return the next cell in the chain."""
        nxt = self.next[c]
        st = self.state[c]
        x, y = self.cx[c], self.cy[c]
        grid = self.grid

        if st == SEED:
            if y == 0:                       # landed: becomes a sprout
                self.state[c] = SPROUT
            elif grid[x][y - 1] == 0:        # fall one cell
                grid[x][y] = 0
                grid[x][y - 1] = c
                self.cy[c] = y - 1
            else:                            # landed on something: the seed dies
                t = self.tree[c]
                t.cells.discard(c)
                self._remove_cell(c)
                if not t.cells:              # (in the original its tree slot just starves out)
                    t.alive = False
            return nxt

        if st != SPROUT or self.energy[c] < ENERGY_TO_GROW:
            return nxt

        t = self.tree[c]
        gene = t.genome[4 * self.gene[c]: 4 * self.gene[c] + 4]
        # order matters: up, left, right, down (upper branches claim space first)
        targets = (
            (UP, x, y + 1),
            (LEFT, (x - 1) % WIDTH, y),
            (RIGHT, (x + 1) % WIDTH, y),
            (DOWN, x, y - 1),
        )
        for d, tx, ty in targets:
            g = gene[d]
            if g < GENES and 0 <= ty < HEIGHT and grid[tx][ty] == 0:
                self._new_cell(tx, ty, g, SPROUT, t, before=c)
                t.mass += 1
        self.energy[c] = 0
        self.state[c] = WOOD
        return nxt

    # ---------------------------------------------------------------- helpers

    def living_cells(self):
        c = self.next[0]
        while c != 0:
            yield c, self.cx[c], self.cy[c], self.state[c], self.tree[c]
            c = self.next[c]

    def genomes(self, min_cells=6):
        """Genomes of trees with more than 5 cells (same filter as the original "save genom")."""
        return [{"genome": t.genome, "color": list(t.color), "cells": len(t.cells),
                 "generation": self.generation}
                for t in self.trees if len(t.cells) >= min_cells]


def reachable_genes(genome):
    """Genes a tree can actually use: everything reachable from gene 0 through values < 16."""
    seen, todo = {0}, [0]
    while todo:
        g = todo.pop()
        for v in genome[4 * g: 4 * g + 4]:
            if v < GENES and v not in seen:
                seen.add(v)
                todo.append(v)
    return seen
