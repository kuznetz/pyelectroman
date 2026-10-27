"""
Quick save / quick load functionality.

F5 - save the current game state to ``quick.sav`` in the project root.
F9 - restore the state saved there.

The save file is a JSON document containing:

* ``globals`` - every JSON-serializable module level variable from
  :mod:`emglobals` (counters, flags, collections, RNG state, ...),
* ``objects`` - snapshots of the few non-serializable global objects that
  carry gameplay state (the player, the screen manager, the checkpoint and
  the level entities: enemies, disks, breakable objects).

Enemies (and every other level object) are stored as a per-screen list of
entity snapshots: their spawn ("home") position, their sprite index, their
current position and their internal state (patrol direction, animation
frame, shoot timer, ...). Objects that vanished - killed enemies, collected
disks, destroyed walls - are simply absent from that list, so a load keeps
them gone instead of resurrecting them from the level data.

``XY`` instances are encoded as ``{"__xy__": [x, y]}`` and restored back
to real ``XY`` objects on load.
"""

import json
import logging
import os
import types
import inspect

import emglobals as gl
from emglobals import XY

# pylint: disable-msg=C0103

QUICK_SAVE_FILE = "quick.sav"

# Marker key used to persist XY objects
XY_KEY = "__xy__"

# Names that must never be written back to the emglobals module
# (they are recreated by the game itself / handled separately).
NO_RESTORE = {"level", "screen_manager", "player", "checkpoint", "screen",
              "enemies", "weapons", "info", "sound_manager",
              "display", "window", "font", "small_font", "medium_font",
              "large_font"}

# Entity attributes that are never written to the save file: they reference
# live objects (sprites, screens) or are used only to identify the entity
# inside the level data.
ENTITY_IGNORE = {"sprites", "anims", "origin", "home_position",
                 "sprite_index", "deferred", "broken_entity",
                 "cross_sprite", "indicator_sprite", "indicator_entity"}


class _Unserializable:
    """Sentinel returned by _encode for values JSON cannot represent."""


_UNSERIALIZABLE = _Unserializable()


def get_quick_save_path():
    """Return absolute path to quick.sav (project root, next to em.py)."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        QUICK_SAVE_FILE)


def _encode(value):
    """
    Convert a value to JSON-friendly structure.

    Returns _UNSERIALIZABLE (and thus excludes the whole containing
    collection) if any part of the value cannot be represented.
    """
    if isinstance(value, XY):
        return {XY_KEY: [value.x, value.y]}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        encoded = []
        for item in value:
            item_encoded = _encode(item)
            if item_encoded is _UNSERIALIZABLE:
                return _UNSERIALIZABLE
            encoded.append(item_encoded)
        return encoded
    if isinstance(value, dict):
        encoded = {}
        for key, item in value.items():
            item_encoded = _encode(item)
            if item_encoded is _UNSERIALIZABLE:
                return _UNSERIALIZABLE
            encoded[str(key)] = item_encoded
        return encoded
    return _UNSERIALIZABLE


def _decode(value):
    """Convert JSON-friendly structure back to Python (incl. XY objects)."""
    if isinstance(value, dict):
        if len(value) == 1 and XY_KEY in value:
            coords = value[XY_KEY]
            return XY(int(coords[0]), int(coords[1]))
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _entity_home(entity):
    """
    Return the spawn position of an entity as an ``(x, y)`` tuple.

    Entities move around, but ``home_position`` (set in Entity.__init__)
    still points at the cell the level data spawned them from - that is what
    identifies the object after the level screens have been recreated.
    """
    home = getattr(entity, "home_position", None)
    if not isinstance(home, XY):
        getter = getattr(entity, "get_position", None)
        home = getter() if callable(getter) else None
    if not isinstance(home, XY):
        return None
    return (int(home.x), int(home.y))


def _entry_home(entry):
    """Return the saved spawn position of a snapshot entry (or None)."""
    home = entry.get("home") if isinstance(entry, dict) else None
    if isinstance(home, (list, tuple)) and len(home) == 2:
        try:
            return (int(home[0]), int(home[1]))
        except (TypeError, ValueError):
            return None
    return None


def _encode_entity(entity):
    """Return a JSON-friendly snapshot of a level entity (or None)."""
    home = _entity_home(entity)
    if home is None:
        return None
    state = {}
    for name, value in vars(entity).items():
        if name in ENTITY_IGNORE or name.startswith("_"):
            continue
        encoded = _encode(value)
        if encoded is not _UNSERIALIZABLE:
            state[name] = encoded
    return {"type": type(entity).__name__,
            "sprite": getattr(entity, "sprite_index", None),
            "home": [home[0], home[1]],
            "state": state}


def _snapshot_entities():
    """
    Snapshot the live state of every object stored in the level screens.

    Returns a dict mapping the screen number to a list of entity snapshots,
    or None when no level screens are available. Enemies that were killed
    (and objects that were collected/destroyed) are absent from the lists.
    """
    if gl.screen_manager is None:
        return None
    screens = gl.screen_manager.get_screens()
    if not screens:
        return None
    entities = {}
    for number, screen in enumerate(screens):
        if screen is None:
            continue
        entries = []
        for entity in screen.active:
            entry = _encode_entity(entity)
            if entry is not None:
                entries.append(entry)
        entities[str(number)] = entries
    return entities


def _apply_entity_state(entity, state):
    """Write saved attribute values back onto a live entity."""
    if not isinstance(state, dict):
        return
    for name, value in state.items():
        if not hasattr(entity, name):
            continue
        try:
            setattr(entity, name, _decode(value))
        except (AttributeError, TypeError, ValueError) as error:
            logging.warning("Quick load: cannot restore %s.%s: %s",
                            type(entity).__name__, name, error)


def _recreate_entity(entry, source):
    """
    Recreate a level object that was replaced at runtime.

    The only such case in the game is a destroyed breakable object: the
    original entity is gone and a BrokenSprite stays in the level data
    (EB_ENEM.C:80-89). The broken sprite is the next level sprite after the
    original animation, exactly as emhero.hit_object() builds it.
    """
    if not isinstance(entry, dict) or source is None:
        return None
    if entry.get("type") != "BrokenSprite":
        return None
    home = _entry_home(entry)
    if home is None:
        return None
    state = entry.get("state") or {}
    source_sprites = list(getattr(source, "sprites", None) or [])
    sprite_index = getattr(source, "sprite_index", None)
    sprites = None
    if sprite_index is not None:
        try:
            sprites = [gl.level.get_sprite(sprite_index + len(source_sprites))]
        except (AttributeError, IndexError, AssertionError):
            sprites = None
    if not sprites:
        sprites = source_sprites
    if not sprites:
        return None
    import emgame as ga
    try:
        entity = ga.BrokenSprite(sprites, XY(home[0], home[1]),
                                 int(state.get("frame", 0)))
    except (TypeError, ValueError, IndexError):
        return None
    entity.sprite_index = sprite_index
    origin = getattr(source, "origin", None)
    if origin is not None:
        entity.set_origin(origin)
    return entity


def _restore_entities(snapshot):
    """
    Re-apply saved entity state onto freshly recreated level screens.

    Entities are matched by their spawn cell (plus sprite/class). A saved
    entity keeps its position and internal state; a level entity with no
    saved counterpart simply disappeared during the saved session (killed,
    collected, destroyed) and is removed again.
    """
    if not isinstance(snapshot, dict):
        return False
    screens = gl.screen_manager.get_screens() if gl.screen_manager else None
    if not screens:
        return False
    restored = 0
    removed = 0
    for key, entries in snapshot.items():
        try:
            number = int(key)
        except (TypeError, ValueError):
            continue
        if not 0 <= number < len(screens):
            continue
        screen = screens[number]
        if screen is None:
            continue
        pending = [entry for entry in (entries or [])
                   if isinstance(entry, dict)]
        used = [False] * len(pending)
        fresh = list(screen.active)
        matched = {}
        # First pass: exact match - same spawn cell, sprite and class.
        for entity in fresh:
            home = _entity_home(entity)
            if home is None:
                continue
            sprite_index = getattr(entity, "sprite_index", None)
            type_name = type(entity).__name__
            for index, entry in enumerate(pending):
                if used[index] or _entry_home(entry) != home:
                    continue
                if (entry.get("sprite") != sprite_index or
                        entry.get("type") != type_name):
                    continue
                used[index] = True
                matched[id(entity)] = entry
                break
        # Second pass: same spawn cell, but another object now occupies it
        # (a destroyed wall is represented by a BrokenSprite in the save).
        replaced = {}
        for entity in fresh:
            if id(entity) in matched:
                continue
            home = _entity_home(entity)
            if home is None:
                continue
            for index, entry in enumerate(pending):
                if used[index] or _entry_home(entry) != home:
                    continue
                used[index] = True
                replaced[id(entity)] = entry
                break
        for entity in fresh:
            entry = matched.get(id(entity))
            if entry is not None:
                _apply_entity_state(entity, entry.get("state"))
                restored += 1
                continue
            entry = replaced.get(id(entity))
            replacement = _recreate_entity(entry, entity) if entry else None
            if entity in screen.active:
                if replacement is None:
                    screen.active.remove(entity)
                    removed += 1
                    continue
                screen.active[screen.active.index(entity)] = replacement
            if replacement is not None:
                _apply_entity_state(replacement, entry.get("state"))
                restored += 1
    logging.info("Quick load: level entities restored=%d, removed=%d",
                 restored, removed)
    return True


def _serializable_globals():
    """Collect all JSON-safe module level values from emglobals."""
    result = {}
    for name, value in vars(gl).items():
        if name.startswith("__"):
            continue
        # Classes, modules and functions are code, not state
        if isinstance(value, (types.ModuleType, type)) or inspect.isroutine(value):
            continue
        encoded = _encode(value)
        if encoded is not _UNSERIALIZABLE:
            result[name] = encoded
    return result


def _snapshot_player(player):
    """Return a JSON-friendly snapshot of the player's gameplay state."""
    if player is None:
        return None
    snapshot = {
        "position": _encode(player.get_position()),
        "move_vector": _encode(getattr(player, "move_vector", XY(0, 0))),
        "teleport_target": _encode(getattr(player, "teleport_target", None)),
        "state": getattr(getattr(player, "state", None), "__name__", None),
    }
    for name in ("anim", "frame", "orientation", "to_ground", "jump",
                 "counter", "double_jump_used", "up_pressed", "prev_up",
                 "air_push_index",
                 "keys", "power", "temp", "ammo", "cooldown",
                 "invuln_timer", "death_timer", "wait_counter", "turn_step",
                 "fired"):
        if hasattr(player, name):
            value = getattr(player, name)
            encoded = _encode(value)
            if encoded is not _UNSERIALIZABLE:
                snapshot[name] = encoded
    return snapshot


def _snapshot_objects():
    """Snapshot global objects that are not plain JSON data."""
    objects = {"player": _snapshot_player(gl.player)}

    if gl.screen_manager is not None:
        objects["screen_manager"] = {
            "current_screen": gl.screen_manager.get_screen_number()
        }

    if gl.checkpoint is not None:
        position = gl.checkpoint.get_position()
        objects["checkpoint"] = {
            "level": gl.checkpoint.get_level(),
            "screen": gl.checkpoint.get_screen(),
            "position": _encode(position) if position is not None else None,
        }

    entities = _snapshot_entities()
    if entities is not None:
        objects["entities"] = entities

    return objects


def save_quick():
    """
    Save the current game state to quick.sav.

    Returns:
        True if the file was written, False otherwise.
    """
    try:
        payload = {
            "version": 2,
            "globals": _serializable_globals(),
            "objects": _snapshot_objects(),
        }
        save_path = get_quick_save_path()
        with open(save_path, "w", encoding="utf-8") as save_file:
            json.dump(payload, save_file, indent=2, ensure_ascii=False)
        logging.info("Quick save written to %s", save_path)
        return True
    except (OSError, TypeError, ValueError) as error:
        logging.error("Quick save failed: %s", error)
        return False


def _restore_globals(globals_data):
    """Write saved plain globals back into the emglobals module."""
    for name, value in globals_data.items():
        if name in NO_RESTORE or name.startswith("__"):
            continue
        if not hasattr(gl, name):
            # Do not create bogus globals from corrupted/foreign saves
            continue
        try:
            setattr(gl, name, _decode(value))
        except (TypeError, ValueError) as error:
            logging.warning("Quick load: cannot restore global '%s': %s",
                            name, error)


def _restore_checkpoint(snapshot):
    """Restore the active checkpoint object (if any)."""
    if gl.checkpoint is None or not snapshot:
        return
    level = snapshot.get("level")
    screen = snapshot.get("screen")
    position = _decode(snapshot.get("position"))
    if level is None or screen is None or not isinstance(position, XY):
        return
    gl.checkpoint.update(level, screen, position)


def _ensure_level(level_index, rebuild=False):
    """
    Make sure the given level is loaded and its screens are available.

    When ``rebuild`` is set the screens are recreated from the pristine
    level data even if the level is already in memory. This is required when
    the save file carries an entity snapshot: the snapshot is then applied
    on top of the clean level (killed enemies stay gone, patrol positions
    are rewound to the saved values).
    """
    if not isinstance(level_index, int):
        level_index = 0
    if not 0 <= level_index < len(gl.level_names):
        level_index = 0
    gl.current_level = level_index
    level_name = gl.level_names[level_index]

    loaded_name = getattr(gl.level, "name", None)
    if (gl.level is None or loaded_name != level_name or
            not gl.screen_manager.get_screens()):
        gl.level.load(level_name)
        gl.screen_manager.add_screens(gl.level.get_screens())
    elif rebuild:
        gl.screen_manager.add_screens(gl.level.reset_screens())


def _restore_player(snapshot):
    """Restore player's position, animation and weapon state."""
    player = gl.player
    if player is None:
        return
    if not snapshot:
        player.screen = gl.screen
        return

    position = _decode(snapshot.get("position"))
    if isinstance(position, XY):
        player.set_position(position)

    move_vector = _decode(snapshot.get("move_vector"))
    if isinstance(move_vector, XY):
        player.move_vector = move_vector

    teleport_target = _decode(snapshot.get("teleport_target"))
    if isinstance(teleport_target, list) and len(teleport_target) == 2:
        teleport_target = (teleport_target[0], teleport_target[1])
    if teleport_target is None or isinstance(teleport_target, tuple):
        player.teleport_target = teleport_target

    for name in ("anim", "frame", "orientation", "to_ground", "jump",
                 "counter", "double_jump_used", "up_pressed", "prev_up",
                 "air_push_index",
                 "keys", "power", "temp", "ammo", "cooldown",
                 "invuln_timer", "death_timer", "wait_counter", "turn_step",
                 "fired"):
        if name in snapshot:
            setattr(player, name, snapshot[name])

    # The player must already know its screen before the FSM state is
    # restored: some state init handlers query the ground/screen.
    player.screen = gl.screen
    player.touched = []

    # Restore FSM state. Death state is not restored: continue standing.
    state_name = snapshot.get("state")
    state = getattr(player, state_name, None) if state_name else None
    player.next_state = None
    if callable(state) and state_name != "state_death":
        player.state = state
    else:
        player.switch_state(player.state_stand)


def load_quick():
    """
    Load game state from quick.sav.

    Returns:
        True if the state was restored, False otherwise.
    """
    save_path = get_quick_save_path()
    if not os.path.exists(save_path):
        logging.info("Quick load: no save file at %s", save_path)
        return False

    try:
        with open(save_path, "r", encoding="utf-8") as save_file:
            payload = json.load(save_file)
    except (OSError, ValueError) as error:
        logging.error("Quick load failed to read %s: %s", save_path, error)
        return False

    globals_data = payload.get("globals", {})
    objects = payload.get("objects", {})

    try:
        # 1. Plain globals (current_level, disks, flags, RNG state, ...)
        _restore_globals(globals_data)

        # 2. Checkpoint
        _restore_checkpoint(objects.get("checkpoint"))

        # 3. Level and current screen. When the save carries an entity
        # snapshot the screens are recreated from the pristine level data
        # first and the snapshot is applied on top - otherwise killed
        # enemies and destroyed objects would be resurrected.
        entities_data = objects.get("entities")
        _ensure_level(gl.current_level, rebuild=entities_data is not None)
        if entities_data is not None:
            _restore_entities(entities_data)

        screen_manager = objects.get("screen_manager") or {}
        screen_number = screen_manager.get("current_screen", 0)
        gl.screen_manager.change_screen(screen_number)
        # drop any entities queued in the old frame
        gl.screen_manager.new_objects = []
        # checkpoint retirement state is session-local: reset it on load
        gl.disabled_checkpoints = set()
        import emgame as ga
        ga.sync_checkpoint_entities()

        # change_screen() reinitialises the screen randoms, restore saved ones
        for name in ("screen_randoms", "rand_seed"):
            if name in globals_data:
                setattr(gl, name, _decode(globals_data[name]))
        gl.screen = gl.screen_manager.get_screen()

        # 4. Player
        _restore_player(objects.get("player"))
    except (AttributeError, TypeError, ValueError, IndexError) as error:
        logging.error("Quick load failed while applying state: %s", error)
        return False

    logging.info("Quick load complete: level=%s, screen=%s",
                 gl.current_level, screen_number)
    return True
