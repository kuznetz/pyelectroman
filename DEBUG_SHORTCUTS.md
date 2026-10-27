# PyElectroMan Debug Shortcuts

This document lists all keyboard shortcuts available in the Python version of PyElectroMan.

Debug overlays (the info lines above the game scene, the status line with the
player position/state below it and the logic/render timing counters) are only
drawn when the game is started as `python em.py --debug`. Without the flag only
the game scene itself and the level minimap are shown.

## Player Controls

| Key | Action |
|-----|--------|
| Arrow Left | Move left |
| Arrow Right | Move right |
| Arrow Up | Jump |
| Arrow Down | Duck |
| Space | Fire weapon |

## Gamepad Controls (Xbox Layout)

Any connected gamepad is polled together with the keyboard and can be
plugged in or out at runtime. The same pad also drives the menus.

### In game

| Control | Action |
|---------|--------|
| Left stick left / right (D-pad also works) | Move left / right |
| Left stick down / D-pad down | Down / duck (same as the Down arrow key) |
| A | Jump |
| B | Down / duck (same as the Down arrow key) |
| X | Fire weapon |
| START | Exit the level (same as Esc, with the "save game (y or n)" prompt) |

### In menus

| Control | Action |
|---------|--------|
| Left stick up / down, D-pad up / down | Move selection (auto-repeats when held) |
| A or START | Confirm / press fire |
| B | Back / quit (in the "exit to dos?" prompt: NO) |
| X | Press fire on title / level-completed / congratulations screens |
| Left stick left / right (on the mode entry) | Switch casual / hardcore |
| A or START in the "y or n" prompt | YES |

## Game Exit

| Key | Action |
|-----|--------|
| Esc | Leave the level and return to the menu; asks "save game (y or n)" |
| Alt+X | Quit the program immediately (matches original DOS version) |

Answering **y** to the "save game (y or n)" prompt writes `quick.sav`;
answering **n** leaves the level without saving. In both cases the game
returns to the main menu.

## Level Navigation

| Key | Action |
|-----|--------|
| 1 | Jump to Level 1 (elek) |
| 2 | Jump to Level 2 (koryt) |
| 3 | Jump to Level 3 (mieszk) |
| 4 | Jump to Level 4 (magaz) |
| 5 | Jump to Level 5 (fiolet) |
| 6 | Jump to Level 6 (10x10) |
| 7 | Jump to Level 7 (sluzy) |
| 8 | Jump to Level 8 (widok) |
| 9 | Jump to Test Level (weapon testing arena) |

## Room Navigation

| Key | Action |
|-----|--------|
| Ctrl+Left | Teleport the hero into the room on the left |
| Ctrl+Right | Teleport the hero into the room on the right |
| Ctrl+Up | Teleport the hero into the room above |
| Ctrl+Down | Teleport the hero into the room below |

Notes:
- The level is a single seamless space arranged in a 16x16 grid of rooms
  (256 slots); positions of all objects are world pixel coordinates.
- These shortcuts move the hero himself (the camera follows him), so an
  empty room slot simply answers "No room <n>".

## Player Teleport

| Key | Action |
|-----|--------|
| Shift+Left | Teleport player left by one sprite width (48px) |
| Shift+Right | Teleport player right by one sprite width (48px) |
| Shift+Up | Teleport player up by one sprite height (48px) |
| Shift+Down | Teleport player down by one sprite height (48px) |

## Weapon Selection

| Key | Action |
|-----|--------|
| Shift+0 | Select weapon level 0 (no weapon) |
| Shift+1 | Select weapon level 1 (short missile) |
| Shift+2 | Select weapon level 2 (long missile) |
| Shift+3 | Select weapon level 3 (long missile variant) |
| Shift+4 | Select weapon level 4 (penetrating missile) |
| Shift+5 | Select weapon level 5 (bow - double height, triple explosion) |

## Quick Save / Load

| Key | Action |
|-----|--------|
| F5 | Quick save the game to `quick.sav` (project root) |
| F9 | Quick load the game from `quick.sav` |

`quick.sav` is also written when leaving a level and answering **y** to
the "save game (y or n)" prompt, and the main menu entry **CONTINUE**
restores it (it is greyed out when no quick save exists).

The save file is JSON (`version: 2`). It stores all JSON-serializable
variables from `emglobals` plus player, checkpoint and per-room entity
snapshots in **world coordinates** (camera plan, stage 6). Version 1 files
(room-local positions) are converted on load.

## Visual Debug

| Key | Action |
|-----|--------|
| Tab | Toggle collision box display (shows AABBs and collision sides) |
| F8 | Toggle the scrolling camera (off = camera pinned to the hero's room) |

## Gameplay Testing

| Key | Action |
|-----|--------|
| Shift+D | Trigger player death (test death/respawn system) |
| Shift+F | Give all 3 disks (enables level exit) |

## On-Screen Information

The following debug text is drawn only when the game is started with
`python em.py --debug`:

| Location | Information |
|----------|-------------|
| Top-left (outside the scene) | Performance stats (logic/render timing in ms) |
| Top-center (above the scene) | Info lines (events such as "Disk collected", "Player died!") |
| Bottom-left (below the scene) | Status line (position, screen, state, ammo) |
| Top-left of the scene | Touch / to-ground overlays |

The game HUD is always displayed, with or without the flag:

| Location | Information |
|----------|-------------|
| Top-right | Minimap (16x16 level grid, scaled 64x64) |
| Bottom-center | Disk counter (0-3), blinks when 3 disks collected |
| Bottom-left | Temperature LED bar |
| Bottom-right | Ammo LED bar |

## Test Level

The test level (key 9) is a dedicated weapon testing arena:

- Two horizontally connected screens with various shootable objects
- Uses original elek1/elek2 sprites (behavior matches real game)
- Shootable objects from elek2 (sprites with 0x20 shootable flag)
- Use Shift+1-5 to set weapon power for testing different weapon levels
- Regenerate with `python create_test_level.py`

## Notes

- All shortcuts described on this page (level jumps, room navigation, teleports, weapon selection, collision display, camera toggle, death/disks cheats) require the `--debug` command line flag; without it the game only reacts to the player controls, Esc, R, F5, F7, F9 and Alt+X.
- Most debug shortcuts require the Shift or Ctrl modifier to prevent accidental activation during normal gameplay.
- Player controls (arrow keys and space) only work when no modifier keys (Ctrl, Shift, Alt) are held.
- The minimap shows the room containing the hero as a white dot on the level grid.
- Collision display (Tab) shows bounding boxes for all collidable entities; it uses the same camera transform as the sprites, so it stays aligned while scrolling.
- The level is seamless: there are no screen changes. Collisions, touching and the enemy AI all query the whole world; non-existing rooms act as walls ("void = wall").
