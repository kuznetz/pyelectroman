# Plan: seamless level + follow camera (pyelectroman)

Goal: remove the page-based model (room-screens), make the level a **single seamless space** with collisions in world coordinates, a follow camera (character in the center), and an **activity zone = viewport + half a viewport in all directions** (enemies, projectiles, effects). HUD is drawn relative to the camera (in viewport coordinates), projectiles die at the activity zone boundary, not strictly at the frame edge.

This document replaces the previous plan version (which assumed “camera on top of room switching”).

> **Status: implemented.** Stages 1–7 are closed.
>
> Key implementation points:
> * [`Camera`](emglobals.py:48), [`render_pos()`](emglobals.py:77),
>   [`view_pos()`](emglobals.py:92) — camera, world render coordinates, and HUD.
> * [`World`](emgame.py:412) (alias `ScreenManager`) — unified world: `occupancy`,
>   `collision_grid`, `entities_in_rect()`, `colliders_in_rect()`,
>   `is_void_at()`/`blocks_void()`, `center_camera()`/`snap_camera()`.
> * Seamless collisions: [`Entity.check_ground()`](emgame.py:269),
>   [`Entity.check_collision()`](emgame.py:306), [`World.entities_in_rect()`](emgame.py:602).
> * Activity zone and update: [`Gameplay.loop_run()`](em.py:449),
>   [`Gameplay.cleanup_inactive()`](em.py:432).
> * Visible room rendering: [`Gameplay.display_screen()`](em.py:130).
> * Projectiles/effects at zone boundary: [`EnemyProjectile.update()`](emgame.py:1998),
>   [`Projectile.update()`](emhero.py:1083).
> * Saves (v2 + v1 migration): [`emquicksave.py`](emquicksave.py:446).
> * End-to-end smoke test: [`check_world.py`](check_world.py) (`python check_world.py`) —
>   loading all 8 levels, camera clamping, seams, “void = wall”,
>   activity zone (±300 px updates, ±700 px does not), save/load, respawn, FPS measurements.

---

## 0. What was taken into account from the clarifications

| Requirement | How it is implemented |
|---|---|
| Update only objects in the activity zone (viewport + half a viewport) | A single list of world entities + filter by `viewport.inflate(MAX_X, MAX_Y)` (±312 px on X, ±192 px on Y); the hero is always updated; outside the zone — freeze |
| Room switching is removed; the level is seamless | `ScreenManager.change_screen`, `check_bounds`, `gl.screen` are removed; positions of all objects are world coordinates; collisions use a unified world index |
| Projectiles die at the screen boundary | Death at the **activity zone** boundary (±half-screen off-screen), not at the viewport edge; plus cleanup of those that left the zone |
| Draw HUD relative to the camera | HUD in viewport coordinates: `hud_pos = (x, y) * 2 * S` (camera and origin are not applied) → HUD is always attached to the frame |
| Logic is a seamless level | All movement/ground/touch/wall checks are world queries (spatial hash), not `screen.collisions` |

---

## 1. Facts from the code (baseline)

### 1.1 Geometry and rendering

| Value | Meaning | Where |
|---|---|---|
| Sprite | 48×48 game px | [`emglobals.py`](emglobals.py:24-25) |
| Room | 13×8 sprites = **624×384** game px | [`emglobals.py`](emglobals.py:26-29) |
| Logical render | 1280×960 (drawn ×2) | [`emdisplay.py`](emdisplay.py:11) |
| Playfield `gl.display` | subsurface 1248×768 design px = **exactly one room** | [`emdisplay.py`](emdisplay.py:56-61) |
| World grid | 16×16 rooms (index `gy*16+gx`), up to 9984×6144 game px | [`emdata.py`](emdata.py:365-382) |

All game `blit`s go through [`gl.render_pos()`](emglobals.py:41-44) (verified across
[`emgame.py`](emgame.py:216), [`emhero.py`](emhero.py:161), [`emgame.py`](emgame.py:1733)) —
the camera is injected in one function.

### 1.2 Current “page-based” model (which we are removing)

* One screen is active: [`em.py`](em.py:397-402) updates `gl.screen.active`,
  [`em.py`](em.py:122-137) draws `gl.screen`.
* Screen switching at boundaries with wrap-around: [`emhero.py`](emhero.py:942-964),
  [`emgame.py`](emgame.py:434-450).
* Enemies/projectiles take the room from global `gl.screen`:
  [`emgame.py`](emgame.py:1174), [`emgame.py`](emgame.py:1438),
  [`emgame.py`](emgame.py:1675).
* Projectiles die at the room boundary: [`emgame.py`](emgame.py:1664-1670).
* Collisions are by iterating over `screen.collisions`: [`emgame.py`](emgame.py:301-324),
  [`emgame.py`](emgame.py:268-299).
* Enemy scan updates are limited to the room: [`emgame.py`](emgame.py:1171-1224),
  [`emgame.py`](emgame.py:1435-1489).

Scope of rework: **~93 references** to `gl.screen`, `get_screen_number()`,
`change_screen()`, `inspect_screen()` in `em.py`, `emgame.py`, `emhero.py`, `emquicksave.py`.

### 1.3 Level data (verified by [`check_seams.py`](check_seams.py))

The script collects colliders touching the seam line on both sides and classifies the seam:
`closed` (blocked in both directions), `open` (no blocking for passage), `one-way`.

```text
elek     rooms= 82 seams=109 H={'closed': 64} V={'closed': 44, 'open': 1}
koryt    rooms= 96 seams=121 H={'closed': 64, 'open': 9} V={'closed': 25, 'open': 23}
mieszk   rooms= 68 seams= 98 H={'closed': 36, 'open': 20} V={'closed': 25, 'open': 17}
magaz    rooms= 86 seams=123 H={'closed': 60, 'open': 7} V={'closed': 43, 'one-way': 1, 'open': 12}
fiolet   rooms= 64 seams=108 H={'closed': 48} V={'closed': 60}
10x10    rooms=100 seams=180 H={'closed': 63, 'open': 27} V={'closed': 49, 'open': 41}
sluzy    rooms= 68 seams= 89 H={'closed': 19, 'open': 36} V={'closed': 28, 'one-way': 1, 'open': 5}
widok    rooms= 59 seams= 72 H={'closed': 22, 'open': 30} V={'closed': 4, 'open': 16}
```

**Conclusion 1 (good news):** the level data is already compatible with a seamless world.
Seams are either closed by walls in each room (movement is blocked correctly when querying
colliders on both sides of the seam), or open — these are real passages. There are only
**two exceptions of “one-way” seams, and both are vertical** (`magaz`, `sluzy`) — these are descents
where you cannot climb back up (there was no upward transition in the original at all).

**Conclusion 2 (problem):** edges leading to **missing** rooms are often NOT walled off:

```text
elek     B-walled 37  L-walled 18  R-walled 18  T-walled 19 | T-OPEN 18
koryt    B-OPEN 48  L-OPEN 21  R-OPEN 21  (L/R-walled 2/2) | T-OPEN 48
mieszk   B-walled 26 L-walled 12  R-walled 12  T-walled 15 | T-OPEN 11
magaz    B-OPEN 17  L-OPEN 19  R-OPEN 16  T-OPEN 20
fiolet   everything closed (16/16/4/4)
10x10    B-OPEN 10  L-OPEN 10  R-OPEN 10  T-OPEN 10  (all 40 edges open)
sluzy    B-OPEN 16  L-OPEN 10  R-OPEN 9   T-OPEN 20
widok    B-OPEN 20  L-OPEN 6   R-OPEN 5   T-OPEN 31
```

Previously this did not manifest: beyond the room boundary, a screen switch simply occurred (or
an invisible boundary triggered). In a seamless world, the hero **will walk into the void** if no rule is introduced.
⇒ mandatory plan item: **“void = wall”** via the world occupancy mask (stage 3), without generating extra colliders.

---

## 2. Target world model

### 2.1 Coordinates

```text
world_x = (room % 16) * MAX_X + local_x        // MAX_X = 624, MAX_Y = 384
world_y = (room // 16) * MAX_Y + local_y
room_of(world_pos) = (world_y // MAX_Y) * 16 + (world_x // MAX_X)
```

* Positions of **all** entities (statics, active, hero, projectiles) are stored in world px.
* Conversion is performed once on level load
  ([`emdata.Level.load()`](emdata.py:355-382)) — in `Level.process()`
  ([`emdata.process()`](emdata.py:384-435)), where the coordinate is currently local:
  `position = XY(x*48, y*48)` → `position = room_origin + XY(x*48, y*48)`.
* Local coordinates remain only in level data (`data/*.ebl`) and in HUD/minimap rendering.

### 2.2 World container instead of `ScreenManager`

`ScreenManager` ([`emgame.py`](emgame.py:394-511)) is replaced by `World` (the class name
can be kept so as not to change `gl.screen_manager` everywhere):

```python
class World:
    occupancy: bytearray(256)          # 1 = room exists
    statics_by_room: dict[int, list]   # background + collisions (with in_front flag)
    colliders: list                    # all colliders (world)
    collision_grid: dict[(cx, cy), list]   # spatial hash, cell 48 px
    entities: list                     # all active entities (world)
    new_objects: list                  # queue for adding
    flags: dict                        # “broken”/removed objects by world position
```

API:

* `add_active(e)`, `remove(e)`, `spawn(e)` — single point (instead of `gl.screen.active`).
* `colliders_in_rect(rect)` — via spatial hash (needed for seamless collisions).
* `entities_in_rect(rect)` — for updating/rendering visible entities.
* `room_exists(gx, gy)` / `is_void_at(rect)` — void rule.
* `reset()` — rebuild from `gl.level` (replacement for `reset_level()`,
  [`emgame.py`](emgame.py:489-511)).

### 2.3 Collisions in the world

* `Entity.check_collision`, `check_ground`, `get_touching`, `check_move`
  ([`emgame.py`](emgame.py:268-370)) stop accepting `screen` and use
  `world.colliders_in_rect()` / `world.entities_in_rect()`.
* Movement projection (`check_move`, step 2 px) is unchanged — only the source of the collider list changes.
* Additional rule in `check_collision` for the hero and enemies:
  `if world.is_void_at(proposed_rect): blocked = True` — “void = wall”.
* Enemy scans (`initialize_patrol`, `would_collide_at`, `has_ground_at`,
  [`emgame.py`](emgame.py:1171-1224)) work against the world, but the scan range
  (12 tiles / 13 tiles) remains — behavior is preserved.

### 2.4 Activity zone and update

The activity zone is wider than the frame: **half a viewport in all directions**. An enemy/projectile/effect
lives while it is inside this zone, even if it is not visible on screen.

```python
MAX_X, MAX_Y = 624, 384                     # viewport size in game px
ACTIVITY_PAD = (MAX_X // 2, MAX_Y // 2)     # 312 px on X, 192 px on Y in each direction

activity = camera.viewport_rect().inflate(MAX_X, MAX_Y)   # 1248x768 = 2x2 viewports
active = [e for e in world.entities if e.world_rect().colliderect(activity)]
for e in active:
    e.update()
player.update()          # hero is always updated
world.new_objects -> world.entities
```

* Zone area = 4 viewports (up to 3×3=9 rooms at junctions, usually 4) — this is a deliberate cost
  so that an enemy does not “turn on” exactly at the frame edge.
* The hard `UPDATE_MARGIN = 48` from the previous plan version is **not used**: the margin
  is set by half a viewport and is the same on all four sides.
* Objects outside the activity zone **freeze**. When the camera returns, they continue from the same
  state (without catch-up simulation).
* Update order: entities first, then the hero (as now in
  [`em.py`](em.py:397-402)).
* Enemies no longer need `gl.screen`: lazy initialization is performed on first
  entry into the activity zone, i.e. half a screen before appearing in frame.
* The activity zone **does not affect rendering**: only what falls into the viewport is drawn
  (with a margin for sprite width).

### 2.5 Rendering and camera

The camera is only a render offset; the viewport remains `gl.display`:

```python
camera.x, camera.y            # top-left corner of the viewport in world px
render_pos(wx, wy) = round((wx - camera.x) * 2 * S), round((wy - camera.y) * 2 * S)
```

* Only rooms intersecting the viewport are drawn (1..4), with a margin for sprite width,
  so that objects on a seam do not “pop”.
* Order: room statics (except `in_front`) → visible active entities → hero →
  `in_front`/deferred ([`em.py`](em.py:122-145) — same logic).
* Camera: `target = hero_center_world - viewport/2`, then clamping (2.6), then
  `cam &= ~1` (parity).
* Instant camera snap: level load, respawn, teleport, quicksave/load.

### 2.6 Camera clamping (no void in frame)

Levels are not rectangular, so the camera is limited by the “run” of existing rooms:

* on X: `[left_room_left, right_room_right - MAX_X]`, where the run is a continuous chain
  of existing rooms in the row;
* on Y: similarly by column;
* two passes: vertical → horizontal (intersection of runs of affected rows) → vertical again.
  Protection against diagonal voids in concave places.

Consequence: in the middle of a “run” the hero is strictly centered (viewport = room, camera range
±1 room per axis); at map edges (or in a dead-end room without neighbors) the hero is offset
from the center — otherwise void would enter the frame.

### 2.7 HUD

HUD (disks, LED bars, status/info lines, minimap) is drawn **in viewport coordinates**:

```python
def view_pos(x, y):      # = current render_pos: camera and world coordinates are not involved
    return (round(x * 2 * S), round(y * 2 * S))
```

* Only `DiskInfo.display` and `LEDBar.display` change
  ([`emdisplay.py`](emdisplay.py:172-210) — currently `gl.render_pos`).
* `di.message`/`InfoLines`/`StatusLine`/`show_map` already use `gl.window_pos`
  ([`emglobals.py`](emglobals.py:47-49) — we do not touch them).
* Result: HUD is always at the same frame position (“relative to the camera”), and the world scrolls
  beneath it.

### 2.8 Projectiles and effects

* `EnemyProjectile` ([`emgame.py`](emgame.py:1655-1677)): the “Off-screen” check becomes
  a check relative to the **activity zone**, not the viewport: a projectile dies when its
  bbox has completely left `activity` (i.e. it can fly half a screen beyond the frame).
* Hero `Projectile` ([`emhero.py`](emhero.py:1063-1135)) — the same policy: death at
  the activity zone boundary (plus existing rules: wall, animation limit for level 1).
* Effects (`Explosion`, hits, sparks) live and update within the same bounds: spawn and
  removal — by `activity`. An explosion that starts at the frame edge plays out in the zone.
* Cleanup: after update — iterate over projectiles/effects and remove those outside `activity`
  (otherwise they will “hang” because they are not updated).
* Projectile collisions with walls — `world.colliders_in_rect()`.
* Spawn (explosions, hits) — in world coordinates, via `world.add_active()`
  (currently `gl.screen.active.append` — [`emhero.py`](emhero.py:52-53),
  [`emgame.py`](emgame.py:1023)).
* The activity zone is recalculated every frame from the camera; on teleport/respawn the camera
  snaps → the zone is recalculated instantly, and no “hanging” projectiles remain.

---

## 3. What is removed / rewritten

| Now | Becomes |
|---|---|
| `ScreenManager.change_screen()` [`emgame.py`](emgame.py:434) | remove |
| `ScreenManager.inspect_screen()` [`emgame.py`](emgame.py:424) | lookup via `world.entities` |
| `ScreenManager.get_screen()` / `gl.screen` (≈40 places) | `world.entities`, `world.colliders_in_rect()` |
| `PlayerEntity.check_bounds()` [`emhero.py`](emhero.py:942) | remove (boundaries are provided by world geometry + void rule) |
| `Playfield.display_screen(screen)` [`em.py`](em.py:122) | render visible rooms from `world` |
| `add_to_level_data` / `delete_object` [`emgame.py`](emgame.py:452-472) | `world.flags` by world position |
| `gl.screen.active.append(...)` (explosions, debris) [`emhero.py`](emhero.py:1340-1350), [`emgame.py`](emgame.py:1825-1835) | `world.add_active()` |
| `Entity.set_origin(screen)` [`emgame.py`](emgame.py:141) | not needed (origin = world position) |
| Checkpoint `(level, screen, pos)` [`emgame.py`](emgame.py:513-539) | `(level, world_pos)` |
| Teleport `(screen, pos)` [`emhero.py`](emhero.py:463-466), [`emhero.py`](emhero.py:532-...) | `world_pos` |
| `gl.disk_positions = [(screen, pos)]` [`emhero.py`](emhero.py:750) | `[world_pos]` |
| `gl.disabled_checkpoints = {(level, screen, x, y)}` | `{(level, x, y)}` (world) |
| Debug screen navigation (Ctrl+arrows) [`em.py`](em.py:154-188) | teleport hero to room/screen |
| Quicksave `current_screen` + local positions [`emquicksave.py`](emquicksave.py:366-370) | world positions + `version: 2` (convert v1 on read) |
| `screen_randoms` by local tile [`emgame.py`](emgame.py:387-389) | local tile inside room: `(wx % MAX_X) // 48` |

---

## 4. Pixel-perfect

1. All game coordinates are even (steps 2/8/20 — [`emhero.py`](emhero.py:14-17)); the camera
   is integer and even (`cam &= ~1`).
2. **One** rounding for the final position: `round((world - cam) * 2 * S)`.
   You cannot do `round(world*2*S) - round(cam*2*S)` — it will cause a 1 px desync.
3. No floating-point camera interpolation. Only integer steps (or snap).
4. HUD — via `view_pos()`, without the camera.
5. `RENDER_SCALE` is currently fractional at non-standard resolutions
   ([`emdisplay.py`](emdisplay.py:29-44)) → for true pixel-perfect, switch to
   integer scaling + letterbox (`floor(min(w/1280, h/960))`, minimum 1).
   With fractional scaling, scrolling produces a 1 px “shimmer” — this is unavoidable.
6. Debug collision rendering ([`emgame.py`](emgame.py:238-267)) goes through the same
   `render_pos` → matches sprites at any camera position.
7. Seams: static sprites are aligned to the 48 px grid, room `origin` is a multiple of `MAX_X/MAX_Y`
   → the joint has no gaps; verify with screenshots.

---

## 5. Work stages

### Stage 1. World coordinates + camera (2 days)

- [x] `Camera` (global, `gl.camera`): `x, y, enabled`.
- [x] `render_pos()` with camera; `view_pos()` for HUD.
- [x] `emdata.process()`: world coordinates when creating entities
      ([`emdata.py`](emdata.py:384-435)).
- [x] HUD (`DiskInfo`, `LEDBar`) → `view_pos()`.
- [x] Camera snap: level load, respawn, teleport, quicksave/load.
- [x] Debug key to enable/disable camera + output `cam/room` in `InfoLines`.

**Acceptance:** with `camera.enabled = False` the image is identical to the current version.

### Stage 2. Unified world and seamless collisions (2–3 days, key stage)

- [x] `World` instead of `ScreenManager`: `entities`, `statics_by_room`, `colliders`,
      `collision_grid`, `occupancy`, `new_objects`, `flags`.
- [x] Level loading: register statics/colliders/active entities (world).
- [x] `check_collision/check_ground/get_touching/check_move/would_collide_at/has_ground_at`
      → world queries.
- [x] The “void = wall” rule (`is_void_at`) for the hero and enemies.
- [x] Remove `check_bounds`, `change_screen`, `inspect_screen`, `gl.screen`.
- [x] `vanish/remove`, debris/broken objects — via `world.flags`.
- [x] Limit patrol scans to the rectangle of their own room (behavior preservation).

**Acceptance:** the hero freely crosses seams in `koryt`/`fiolet`/`10x10`; seam walls
do not let anything through from either side; it is impossible to walk into the void; no crashes.

### Stage 3. Activity zone and update (1 day)

- [x] `activity = viewport.inflate(MAX_X, MAX_Y)` (±312 px on X, ±192 px on Y).
- [x] Update filter by `activity`; hero is always updated.
- [x] Queue `new_objects` → `world.entities`.
- [x] Objects outside the zone freeze; when the camera returns — correct continuation.

**Acceptance:** enemies/projectiles are active half a screen beyond the frame on all four sides;
further — they freeze; profile is stable.

### Stage 4. Camera: centering and clamping (1 day)

- [x] Hero center = viewport center.
- [x] Clamping by runs of existing rooms (2 passes).
- [x] Camera parity, snaps.

**Acceptance:** in the middle of the map the hero is strictly centered; there are never missing
rooms in frame; no jumps at seams (world coordinate is continuous).

### Stage 5. Projectiles and effects (1 day)

- [x] Projectile death at the **activity zone** boundary (`viewport.inflate(MAX_X, MAX_Y)`),
      not at the viewport edge.
- [x] Same boundary for hero projectiles and effects.
- [x] Cleanup of projectiles/effects that left the activity zone (they are not updated).
- [x] Projectile collisions with walls — via the world.
- [x] Effect spawn in world coordinates.

**Acceptance:** a projectile flies half a screen beyond the frame edge and only then disappears;
there are no “hanging” bullets at the zone boundary; bullets do not fly into the void; hits against walls at seams
work.

### Stage 6. Checkpoints, teleports, disks, saves (1–2 days)

- [x] Checkpoint/teleport/exit/disks — world coordinates.
- [x] `disabled_checkpoints`, “broken” objects — by world position.
- [x] Quicksave: `version: 2`, world positions; read v1 with conversion.
- [x] `reset_level` → `world.reset()` (disks and broken objects are preserved).

**Acceptance:** save/load in the middle of a level, after collecting disks and destroying objects;
teleport and respawn work, camera snaps.

### Stage 7. Performance and polish (1–2 days)

- [x] Cache of scaled sprites (`id(surface) → surface`, key includes `RENDER_SCALE`)
      — currently [`scale_sprite`](emdisplay.py:72-75) scales every frame.
- [x] Optional: lazy composite of room statics into a `Surface` (LRU for ~8 rooms),
      separately for “behind” and `in_front` (otherwise layer order breaks).
- [x] Integer `RENDER_SCALE`.
- [x] Profiler: `render_time`/`logic_time` already exist ([`em.py`](em.py:472-477)).
- [x] Update `DEBUG_SHORTCUTS.md`.

**Acceptance:** stable 20 FPS on `10x10.ebl` (4 rooms in frame).

---

## 6. Risks

| Risk | Probability | Mitigation |
|---|---|---|
| Collisions at seams behave differently | **low** (verified by `check_seams.py`: seams closed/open, 2 one-way descents) | Cover traversal of all seams with tests |
| “Void = wall” creates invisible stops where the room edge used to be | medium | Walk all levels along boundaries; if necessary replace the stop with “falling into void = death” |
| Patrol/jump scans use room boundaries | medium | Limit scan to rectangle of `room_of(pos)` |
| AI timing changes (initialization when appearing in frame) | medium | Keep lazy initialization; compare difficulty with the original |
| Saves/checkpoints/teleports (v1 → v2) | medium | Save versioning + converter + tests |
| Loss of determinism in `gl.random`/`screen_randoms` | medium | Seed by room and local tile; lock down in tests |
| Fractional `RENDER_SCALE` and scroll “shimmer” | high at non-standard resolution | Integer scaling + letterbox |
| FPS drop: activity zone = 4 viewports (up to 9 rooms), render — up to 4 rooms | medium | Spatial hash, sprite cache, lazy static composite, `render_time`/`logic_time` measurements |

---

## 7. Test plan

- [x] Regression: with camera disabled, the image is 1:1 with the current version.
- [x] Seams: traverse each seam type (closed/open/one-way) in both directions on `koryt`,
      `fiolet`, `10x10`, `magaz`, `sluzy`.
- [x] Void: attempt to leave the map edge on all 8 levels — does not leave, does not get stuck
      (or consistently dies if that option is chosen).
- [x] Vertical descents (`V open`): fall into the lower room, no return upward
      (as in the original), camera without jerking.
- [x] Camera: hero centered, clamping at edges, no empty rooms in frame.
- [x] Projectiles: death at the activity zone boundary (±half-screen beyond the frame), not at the frame
      edge; walls at seams; no “hangs”.
- [x] Activity zone: an enemy 300 px beyond the frame still moves, at 700 px — already stands;
      check on all four sides.
- [x] HUD: positions unchanged during scrolling (disks, LED, minimap, debug text).
- [x] Checkpoint/death/respawn/teleport/exit from level/next level.
- [x] Quicksave/quickload: in different rooms, after destruction and disk collection.
- [x] Performance: `10x10` (100 rooms; render up to 4, update up to 9 rooms), 20 FPS.
- [x] Pixel-perfect: compare before/after screenshots at `RENDER_SCALE = 1` and `2`.

---

## 8. Estimate

| Stage | Scope |
|---|---|
| 1. World coordinates + camera | 2 days |
| 2. Unified world and collisions | 2–3 days |
| 3. Activity zone and update | 1 day |
| 4. Centering + clamping | 1 day |
| 5. Projectiles/effects | 1 day |
| 6. Checkpoints/teleports/saves | 1–2 days |
| 7. Performance/polish | 1–2 days |
| **Total** | **9–12 days** |

This is substantially more than “camera on top of the page-based model” (2–2.5 days), because
seamlessness is a change of the data model and logic, not just rendering.