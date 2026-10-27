# PyElectroMan

A Python port of **Electro Man** (1992), also known as *Electro Body* — a cult classic platformer developed in Poland by xLand.

## This fork

This repository is a fork of **[tosiabunio/pyelectroman](https://github.com/tosiabunio/pyelectroman)** — the Python port of the original game. The upstream port is an accuracy-focused conversion; the goal of this fork is to make it **comfortable to actually play**: adaptive fullscreen rendering, gamepad support, a casual mode and quick save/load. Everything that concerns the game logic itself stays as close to the upstream (and to the original C source) as possible.

What the fork adds on top of the upstream:

* Fullscreen rendering that adapts to the desktop resolution
* Two game modes: **hardcore** (original rules) and **casual**
* Quick save / quick load with `F5` / `F9` and a Continue entry in the menu
* Keyboard and Xbox-compatible gamepad support, with hot-plugging
* Reworked checkpoints: an activated checkpoint is retired and can never be re-used, level entrance checkpoints are adopted correctly

## Casual mode

The main menu has a `CASUAL` / `HARDCORE` entry.

Casual mode does not exist in the original game and was never designed by its authors — it was added to make the playthrough as easy as possible. 

- Hero can steer and perform a double jump in mid-air
- Carries a three times larger magazine
- A lethal hit only costs one battery level and grants a short invulnerability
- With no battery power left the hero still dies

For the original experience play **Hardcore**.

## About

PyElectroMan is an ongoing effort to recreate the original DOS game in Python. The project originated as a personal exercise to improve Python skills rather than as a path toward a commercial release.

The port is based on the original (unreleased) source code and uses art assets from the game, licensed under **CC BY-SA**.

The original game can be played online at:

* [DOSGames.com](https://dosgames.com/game/electro-man/)
* [RetroGames.cz](https://www.retrogames.cz/play_1149-DOS.php)

The DOSBox version, ready to run on modern Windows, is available for free at [GOG.com](https://www.gog.com/en/game/electro_man).

## Running

Requires Python 3 and [pygame](https://www.pygame.org/) 2.x (developed and tested with Python 3.13 and pygame 2.6.1).

```
python -m pip install pygame
python em.py
```

The `data/` and `maps/` directories must stay next to the sources — they hold the converted game assets.

## Display

The game starts in fullscreen at the desktop resolution. All drawing goes through a single render coefficient (`gl.RENDER_SCALE`), which is computed from the actual surface size: the 1280x960 logical window is scaled by it, and the offsets, sprites, fonts and overlays of the playfield are multiplied by the same value. If the screen proportions differ from 4:3, the picture is centered with black bars instead of being stretched.

## Controls

| Key | Action |
|-----|--------|
| Left / Right | Move |
| Up | Jump |
| Down | Use |
| Space | Fire weapon |
| Esc | Leave the level (asks "save game (y or n)") |
| F5 / F9 | Quick save / quick load |
| F7 | Toggle sound effects |
| Alt+X | Quit the program immediately |

Gamepad (Xbox layout): left stick or D-pad to move, `A` jump, `B` use, `X` fire, `START` leave the level. The same pad drives the menus — stick/D-pad to navigate, `A` or `START` confirm, `B` back.

The complete list, including level/screen navigation, teleport and weapon debug keys, is in [PyElectroMan Debug Shortcuts](DEBUG_SHORTCUTS.md).

## Saving

| File | Written by | Contents |
|------|------------|----------|
| `pyelectroman.sav` | automatically when a checkpoint is activated | level, screen, respawn position and disks |
| `quick.sav` | `F5`, or answering **y** to "save game (y or n)" when leaving a level | full snapshot: globals, player, checkpoint and per-screen entities |

The **CONTINUE** entry of the main menu restores `quick.sav` (it is greyed out when no quick save exists), so leaving a level with **y** and pressing Continue later resumes exactly the same state. Killed enemies, collected disks and destroyed objects stay gone, because the save stores the live entity list per screen.

Both files are JSON. `quick.sav` is a runtime artifact and is listed in `.gitignore`.

## Project History

Development began years ago but went dormant for roughly 15 years due to the complexity of the original codebase — 30+ years old, difficult to parse, and challenging to translate accurately.

The upstream project [tosiabunio/pyelectroman](https://github.com/tosiabunio/pyelectroman) was revived with AI-assisted development: nearly all of its recent commits were written by **Claude Code**.

This fork continues the work with **DeepSeek** as the AI assistant, focusing on playability rather than on further conversion work.

## Development Philosophy

- **Conversion accuracy over code quality** — the goal is to faithfully recreate original behavior, even when the source code is convoluted
- **Incremental progress** — given the complexity, exact 1:1 conversion may not be achievable
- **AI-assisted development** — exploring what's possible when AI handles the heavy lifting of legacy code translation
- **Playability matters too** — quality-of-life additions in this fork must never silently change the original game logic

## Status

🚧 Work in progress — not intended as a playable release at this time.

## Useful debug info

[PyElectroMan Debug Shortcuts](DEBUG_SHORTCUTS.md)

## License

- **Code**: [MIT License](LICENSE)
- **Art assets**: [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) (from the original game)

## Acknowledgments

- Original game by xLand (1992)
- Upstream Python port by [tosiabunio](https://github.com/tosiabunio/pyelectroman), developed with [Claude Code](https://claude.ai)
- AI development assistance in this fork by [DeepSeek](https://www.deepseek.com/)
