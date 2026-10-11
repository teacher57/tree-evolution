"""Run the digital tree evolution.

    python main.py                         # live window (pygame-ce)
    python main.py --headless --steps 5000 --png out.png   # no window, save a snapshot

Keys in the window:
    SPACE  pause / resume (starts paused)   D  toggle drawing (much faster when off)
    mouse  point at a tree to see its genome
    S      save genomes (>5 cells) to genomes/NNN.json
    F      fullscreen on/off (the window can also be resized by dragging)
    R      restart (with the loaded save, if any)  +/-  speed (ticks per frame)
    L      choose a save to load (UP/DOWN or mouse, ENTER/click to load, ESC to cancel)

    python main.py --load genomes/003.json   # start from a save (also works with --headless)
    Q/ESC  quit
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from sim import GENES, HEIGHT, SEED, WIDTH, WOOD, World, genome_key, reachable_genes

CELL = 5  # pixels per cell for PNG snapshots, as in the original (256*5 = 1280 wide)
BAR = 40  # status bar height in the window (in points; doubled on Retina)
UI = 1    # pixels per point: 2 on Retina screens, set when the window opens
HERE = Path(__file__).resolve().parent
BG = (12, 14, 20)
GROUND = (60, 45, 30)
WHITE = (255, 255, 255)


PASTEL = 0.45  # how much white is mixed into tree/seed colors when drawing (0 = original colors)
RIM = 1        # cell edge width in real screen pixels (1 = hairline on Retina; 0 = no edges)


def pastel(color):
    return tuple(int(c + (255 - c) * PASTEL) for c in color)


def u(n):
    """Size in points -> real pixels (so text and padding stay the same size on Retina)."""
    return max(int(n * UI), 1)


def shade(color):
    """Cell outline: a darker tone of the cell's own color."""
    return tuple(int(c * 0.7) for c in color)


def cell_color(state, tree):
    if state == WOOD:
        return pastel(tree.color)
    if state == SEED:  # falling seeds use the inverse of their tree's color
        r, g, b = tree.color
        return pastel((255 - r, 255 - g, 255 - b))
    return WHITE       # sprouts


def save_genomes(world):
    out = HERE / "genomes"
    out.mkdir(exist_ok=True)
    n = len(list(out.glob("*.json")))
    path = out / f"{n:03d}.json"
    data = world.genomes()
    path.write_text(json.dumps(data, indent=1))
    return path, len(data)


def list_saves():
    """All saves, newest first, with a short description for the picker."""
    out = []
    for path in sorted((HERE / "genomes").glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not data:
            continue
        gen = max(d.get("generation", 0) for d in data)
        when = datetime.fromtimestamp(path.stat().st_mtime).strftime("%b %d %H:%M")
        out.append((path, f"{path.name}   {len(data):3d} genomes   gen {gen:5d}   {when}"))
    return out


def picker_rows(screen, font, saves):
    """Screen rects of the picker rows (shared by drawing and mouse hit-testing)."""
    import pygame

    lh = font.get_linesize() + u(6)
    pw = max([font.size(label)[0] for _, label in saves] + [font.size("Load save")[0]]) + u(40)
    ph = lh * (len(saves) + 2) + u(20)
    w, h = screen.get_size()
    x, y = (w - pw) // 2, max((h - ph) // 2, u(5))
    rows = [pygame.Rect(x + u(10), y + u(10) + (i + 1) * lh, pw - u(20), lh) for i in range(len(saves))]
    return pygame.Rect(x, y, pw, ph), rows


def draw_picker(screen, font, saves, selected):
    import pygame

    box, rows = picker_rows(screen, font, saves)
    panel = pygame.Surface(box.size, pygame.SRCALPHA)
    panel.fill((20, 22, 30, 235))
    screen.blit(panel, box.topleft)
    pygame.draw.rect(screen, (150, 200, 150), box, u(2), border_radius=u(8))
    screen.blit(font.render("Load save", True, (150, 200, 150)), (box.x + u(14), box.y + u(12)))
    for i, ((_, label), r) in enumerate(zip(saves, rows)):
        if i == selected:
            pygame.draw.rect(screen, (60, 70, 90), r, border_radius=u(4))
        screen.blit(font.render(label, True, WHITE if i == selected else (190, 190, 200)), (r.x + u(6), r.y + u(3)))
    hint = "UP/DOWN or mouse · ENTER/click load · ESC cancel"
    screen.blit(font.render(hint, True, (120, 120, 130)), (box.x + u(14), rows[-1].bottom + u(6)))


def load_save(path):
    data = json.loads(Path(path).read_text())
    if not data:
        raise SystemExit(f"{path} has no genomes in it")
    return data


def run_headless(args):
    world = World(seed=args.seed, saved=load_save(args.load) if args.load else None)
    for _ in range(args.steps):
        if not world.step():
            if not args.autorestart:
                break
            world.reset()
        if args.log and world.step_count % args.log == 0:
            print(f"step {world.step_count:6d}  gen {world.generation:4d}  "
                  f"trees {len(world.trees):4d}  restarts {world.restarts}")
    print(f"done: step {world.step_count}, generation {world.generation}, "
          f"trees {len(world.trees)}, restarts {world.restarts}")
    if args.png:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (WIDTH * CELL, HEIGHT * CELL + 10), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, HEIGHT * CELL, WIDTH * CELL, HEIGHT * CELL + 10], fill=GROUND)
        for _, x, y, st, t in world.living_cells():
            px, py = x * CELL, (HEIGHT - 1 - y) * CELL
            fill = cell_color(st, t)
            d.rectangle([px, py, px + CELL - 1, py + CELL - 1], fill=fill, outline=shade(fill))
        img.save(args.png)
        print("saved", args.png)
    if args.save_genomes:
        path, n = save_genomes(world)
        print(f"saved {n} genomes to {path}")


def genome_lines(world, t):
    """Text for the hover panel. '·' = don't grow, '*' = gene the tree can actually reach."""
    key = genome_key(t.genome)
    same = sum(1 for o in world.trees if genome_key(o.genome) == key)
    used = reachable_genes(t.genome)
    lines = [
        f"cells {len(t.cells)}  energy {t.energy}  age left {t.age_left}",
        f"same genome: {same} tree{'s' if same != 1 else ''}   genes used: {len(used)}/{GENES}",
        "",
        "gene    L   U   R   D",
    ]
    for g in range(GENES):
        vals = t.genome[4 * g: 4 * g + 4]
        cells = "".join(f"{v:4d}" if v < GENES else "   ·" for v in vals)
        lines.append(f"{g:3d}{'*' if g in used else ' '} {cells}")
    return lines, used


def draw_genome_panel(screen, font, world, t, mouse):
    import pygame

    lines, used = genome_lines(world, t)
    lh = font.get_linesize()
    pw = max(font.size(s)[0] for s in lines) + u(40)
    ph = lh * len(lines) + u(20)
    w, h = screen.get_size()
    x = mouse[0] + u(20) if mouse[0] + u(20) + pw < w else mouse[0] - u(20) - pw
    y = min(max(mouse[1] - ph // 2, u(5)), h - ph - u(5))

    panel = pygame.Surface((pw, ph), pygame.SRCALPHA)
    panel.fill((20, 22, 30, 225))
    screen.blit(panel, (x, y))
    pygame.draw.rect(screen, pastel(t.color), (x, y, pw, ph), u(2), border_radius=u(8))
    pygame.draw.rect(screen, pastel(t.color), (x + u(10), y + u(12), u(12), u(12)), border_radius=u(3))  # swatch
    for i, s in enumerate(lines):
        dim = i >= 4 and (i - 4) not in used  # unused genes are greyed out
        color = (110, 110, 120) if dim else (225, 225, 230)
        screen.blit(font.render(s, True, color), (x + u(30 if i == 0 else 12), y + u(10) + i * lh))


def run_window(args):
    global UI
    import pygame

    pygame.init()
    # start at ~90% of the screen, keeping the world's 256:100 shape (sizes here are in points)
    sw, sh = pygame.display.get_desktop_sizes()[0]
    cell = min(sw * 0.9 / WIDTH, (sh * 0.9 - BAR) / HEIGHT)
    size = (int(WIDTH * cell), int(HEIGHT * cell) + BAR)
    # allow_high_dpi: draw at the screen's real resolution on Retina instead of 2x-upscaling
    window = pygame.Window("Digital tree evolution", size, resizable=True, allow_high_dpi=True)
    UI = window.get_surface().get_width() / window.size[0]
    fullscreen = False
    font = pygame.font.SysFont("menlo", u(16))
    mono = pygame.font.SysFont("menlo", u(14))
    clock = pygame.time.Clock()

    def to_pixels(pos):  # mouse positions come in points
        return int(pos[0] * UI), int(pos[1] * UI)

    world = World(seed=args.seed, saved=load_save(args.load) if args.load else None)
    draw, speed = True, 1
    message, message_ttl = "", 0
    paused = True  # always start paused; SPACE to run
    saves, selected = None, 0  # save picker (L): list of saves while it's open

    running = True
    while running:
        screen = window.get_surface()  # changes after a resize / fullscreen toggle
        for ev in pygame.event.get():
            if ev.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                running = False
            elif saves is not None and ev.type in (pygame.KEYDOWN, pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                # the save picker is open: it takes all input until something is loaded or cancelled
                choose = False
                if ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_ESCAPE, pygame.K_l, pygame.K_q):
                        saves = None
                        continue
                    if ev.key == pygame.K_UP:
                        selected = (selected - 1) % len(saves)
                    elif ev.key == pygame.K_DOWN:
                        selected = (selected + 1) % len(saves)
                    elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        choose = True
                else:
                    _, rows = picker_rows(screen, mono, saves)
                    pos = to_pixels(ev.pos)
                    hit = next((i for i, r in enumerate(rows) if r.collidepoint(pos)), None)
                    if hit is not None:
                        selected = hit
                        choose = ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1
                if choose:
                    path = saves[selected][0]
                    world = World(saved=load_save(path))
                    paused = True
                    message, message_ttl = f"loaded {len(world.saved)} genomes <- {path.name}", 180
                    saves = None
            elif ev.type == pygame.KEYDOWN:
                k = ev.key
                if k in (pygame.K_q, pygame.K_ESCAPE):
                    running = False
                elif k == pygame.K_SPACE:
                    paused = not paused
                elif k == pygame.K_f:
                    fullscreen = not fullscreen
                    if fullscreen:
                        window.set_fullscreen(desktop=True)
                    else:
                        window.set_windowed()
                elif k == pygame.K_d:
                    draw = not draw
                elif k == pygame.K_r:
                    world.reset()
                    paused = True
                elif k in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                    speed = min(speed * 2, 256)
                elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    speed = max(speed // 2, 1)
                elif k == pygame.K_l:
                    saves, selected = list_saves(), 0
                    if not saves:
                        saves = None
                        message, message_ttl = "no saves in genomes/ yet (press S to save)", 120
                elif k == pygame.K_s:
                    path, n = save_genomes(world)
                    message, message_ttl = f"saved {n} genomes -> {path.name}", 120
        screen = window.get_surface()

        if not paused and saves is None:
            for _ in range(speed if draw else 50):
                if not world.step():
                    world.reset()  # life died out — the author restarts by hand, we do it for you
                    break

        # scale the world to fit the current window, centered horizontally (all in real pixels)
        w, h = screen.get_size()
        bar = u(BAR)
        cell = max(min(w / WIDTH, (h - bar) / HEIGHT), 1)
        world_h = int(HEIGHT * cell)
        ox = (w - int(WIDTH * cell)) // 2
        top = h - bar - world_h  # extra space goes above the world (sky)

        def cell_rect(x, y):
            x0, y0 = ox + int(x * cell), top + int((HEIGHT - 1 - y) * cell)
            return pygame.Rect(x0, y0, ox + int((x + 1) * cell) - x0, top + int((HEIGHT - y) * cell) - y0)

        screen.fill(BG)
        pygame.draw.rect(screen, GROUND, (0, top + world_h, w, u(6)))
        if draw:
            # big enough cells get soft rounded corners and a thin darker rim
            radius = int(cell * 0.3) if cell >= 6 else 0
            rim = RIM if cell >= 4 else 0
            for _, x, y, st, t in world.living_cells():
                r = cell_rect(x, y)
                fill = cell_color(st, t)
                if rim:
                    pygame.draw.rect(screen, shade(fill), r, border_radius=radius)
                    pygame.draw.rect(screen, fill, r.inflate(-2 * rim, -2 * rim), border_radius=max(radius - rim, 0))
                else:
                    screen.fill(fill, r)

            # tree under the mouse: highlight it and show its genome
            mx, my = to_pixels(pygame.mouse.get_pos())
            gx, gy = int((mx - ox) // cell), HEIGHT - 1 - int((my - top) // cell)
            c = world.grid[gx][gy] if 0 <= gx < WIDTH and 0 <= gy < HEIGHT else 0
            if c and world.tree[c] is not None and saves is None:
                t = world.tree[c]
                for tc in t.cells:
                    pygame.draw.rect(screen, WHITE, cell_rect(world.cx[tc], world.cy[tc]), u(1),
                                     border_radius=radius)
                draw_genome_panel(screen, mono, world, t, (mx, my))
        status = (f"gen {world.generation}  step {world.step_count}  trees {len(world.trees)}  "
                  f"restarts {world.restarts}  speed x{speed}"
                  f"{'  PAUSED' if paused else ''}{'' if draw else '  (drawing off)'}")
        screen.blit(font.render(status, True, (120, 200, 120)), (u(10), h - bar + u(12)))
        if saves is not None:
            draw_picker(screen, mono, saves, selected)
        if message_ttl > 0:
            message_ttl -= 1
            msg = font.render(message, True, WHITE)
            screen.blit(msg, (w - msg.get_width() - u(10), h - bar + u(12)))
        window.flip()
        clock.tick(60)

    pygame.quit()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seed", type=int, help="random seed (default: random)")
    p.add_argument("--headless", action="store_true", help="run without a window")
    p.add_argument("--load", metavar="FILE", help="start from saved genomes, e.g. genomes/000.json")
    p.add_argument("--steps", type=int, default=3000, help="headless: ticks to run")
    p.add_argument("--png", help="headless: save the final world as an image")
    p.add_argument("--log", type=int, default=0, help="headless: print stats every N ticks")
    p.add_argument("--save-genomes", action="store_true", help="headless: save genomes at the end")
    p.add_argument("--no-autorestart", dest="autorestart", action="store_false",
                   help="headless: stop instead of restarting when life dies out")
    args = p.parse_args()
    run_headless(args) if args.headless else run_window(args)


if __name__ == "__main__":
    main()
