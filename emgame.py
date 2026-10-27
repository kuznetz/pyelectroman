"""Gameplay module"""

import emglobals as gl
import emdata as da
import emsound as snd
import emdisplay as di
from emglobals import XY
import pygame
import copy
import logging
import empad


class Controller:
    """
    Class representing player's input.

    Keyboard is always reported. Connected gamepads with the Xbox layout
    are polled as well:

      * left stick left/right (D-pad also works) - walk
      * left stick down (D-pad down also works) - down
      * A - jump
      * B - down (same as the Down arrow key)
      * X - fire
      * START - quit the level (same as the Esc key)

    Singleton by design.
    """

    def __init__(self):
        # pylint complains when those are defined via calling clear()
        self.left = False
        self.right = False
        self.up = False
        self.down = False
        self.fire = False
        self.debug = False
        # set for a single frame when START is pressed (edge)
        self.exit = False
        self.gamepad = empad.get_gamepad()
        # suppress the edge on the first poll: the game may be started
        # with START still held down in the menu
        self._prev_start = True

    def clear(self):
        self.left = False
        self.right = False
        self.up = False
        self.down = False
        self.fire = False
        self.debug = False

    def handle_event(self, event):
        """Track gamepad hot-plugging."""
        self.gamepad.handle_event(event)

    def update(self):
        """Update controller settings"""
        self.clear()
        keys = pygame.key.get_pressed()
        mods = pygame.key.get_mods()
        if not (mods & (pygame.KMOD_CTRL |
                        pygame.KMOD_SHIFT |
                        pygame.KMOD_ALT)):
            if keys[pygame.K_LEFT]:
                self.left = True
            if keys[pygame.K_RIGHT]:
                self.right = True
            if keys[pygame.K_UP]:
                self.up = True
            if keys[pygame.K_DOWN]:
                self.down = True
            if keys[pygame.K_SPACE]:
                self.fire = True
        else:
            self.debug = True
        self.update_gamepad()

    def update_gamepad(self):
        """Read the gamepad state (summed up with the keyboard)."""
        state = self.gamepad.poll()
        if state.left:
            self.left = True
        if state.right:
            self.right = True
        if state.down:
            self.down = True
        if state.a:
            self.up = True
        if state.b:
            self.down = True
        if state.x:
            self.fire = True
        self.exit = state.start and not self._prev_start
        self._prev_start = state.start


class FSM:
    """Very simple Finite State Machine for entities."""
    def __init__(self):
        self.next_state = None
        self.state = lambda: None

    def switch_state(self, state):
        """Enter a new state immediately."""
        self.state = state
        self.state(True)

    def new_state(self, state):
        """Change to a new state in next frame."""
        self.next_state = state

    def run_fsm(self):
        """Cheange to a new state or run current."""
        if self.next_state:
            state = self.next_state
            self.next_state = None
            self.switch_state(state)
        else:
            self.state()


class Entity:
    def __init__(self, sprites, position):
        assert isinstance(sprites, list)
        self.sprites = sprites
        if not isinstance(position, XY):
            raise ValueError("Entity position must by XY() instance.")
        self.position = position
        # Spawn ("home") position: never changes when the entity moves, so
        # save/load can locate this very object in the recreated level data.
        self.home_position = XY.from_self(position)
        self.frame = 0
        self.delay = 0
        self.deferred = None
        self.origin = None
        # Original sprite index in level data (for broken sprite lookup)
        self.sprite_index = None

    def set_origin(self, screen):
        self.origin = screen

    def set_position(self, position):
        """Set entity position"""
        if not isinstance(position, XY):
            raise ValueError("Entity position must by XY() instance.")
        # create a copy not just reference
        self.position = XY.from_self(position)

    def get_position(self):
        """
        Return entity's position as XY(x, y).
        May be changed by the referring code!
        """
        return self.position

    def copy_position(self):
        """
        Return a copy of entity's position as XY(x, y).
        """
        return self.position.copy()

    def world_rect(self):
        """Return the entity's bounding box in world coordinates."""
        rect = self.get_bbox().copy()
        rect.move_ip(self.get_position())
        return rect

    def get_x(self):
        return self.position.x

    def get_y(self):
        return self.position.y

    def get_bbox(self):
        """Return bounding box for current sprite frame as pygame.Rect."""
        return self.sprites[self.frame].bbox

    def get_void_bbox(self):
        """
        Local rect the "void = wall" rule is tested against.

        By default it is the collision box. Entities whose artwork extends
        beyond the collision box override it, so no drawn pixel can enter a
        missing room.
        """
        return self.get_bbox()

    def get_sides(self):
        """Return boolean table with colliding sides for the current sprite."""
        return self.sprites[self.frame].collide

    def get_top(self):
        return self.sprites[self.frame].bbox.top + self.get_y()

    def is_touchable(self):
        return self.sprites[self.frame].flag("touchable")

    def get_touch(self):
        return self.sprites[self.frame].touch

    def vanish(self):
        """Remove itself from the world and from the level definition."""
        logging.debug("vanish() called for %s at %s", self.name(), self.position)
        world = gl.screen_manager
        if world is not None:
            world.remove(self)
            logging.debug("  Removed from the world")

    def update(self):
        """Standard empty update method."""
        pass

    def name(self):
        """Return my class name."""
        return self.__class__.__name__

    def display(self):
        """
        Standard display method.
        Use sprite indicate by self.frame
        """
        sprite = self.sprites[self.frame]
        if not sprite.flag("in_front"):
            # Scale sprite and position by the render coefficient
            scaled_image = di.scale_sprite(sprite.image)
            scaled_pos = gl.render_pos(self.get_position().x,
                                       self.get_position().y)
            gl.display.blit(scaled_image, scaled_pos)
            if gl.show_collisions and sprite.flag("active"):
                # show collision box or lines
                self.display_collisions(pygame.Color(255, 255, 0))
            return None
        else:
            return self.display_deferred

    def display_deferred(self):
        """Deferred display method usef for in_front sprites."""
        # Scale sprite and position by the render coefficient
        scaled_image = di.scale_sprite(self.sprites[self.frame].image)
        scaled_pos = gl.render_pos(self.get_position().x,
                                   self.get_position().y)
        gl.display.blit(scaled_image, scaled_pos)
        if gl.show_collisions:
            # show collision box or lines
            self.display_collisions(pygame.Color(255, 255, 0))

    def display_collisions(self, color=pygame.Color(255, 0, 255)):
        """Display collision lines depending on collision sides."""
        x, y, w, h = self.sprites[self.frame].bbox
        collide = self.sprites[self.frame].collide
        position = self.get_position()
        if collide["T"]:
            sp = position + (x, y)
            ep = position + (x + w - 1, y)
            pygame.draw.line(gl.display, color,
                             gl.render_pos(sp.x, sp.y),
                             gl.render_pos(ep.x, ep.y))
        if collide["L"]:
            sp = position + (x, y)
            ep = position + (x, y + h - 1)
            pygame.draw.line(gl.display, color,
                             gl.render_pos(sp.x, sp.y),
                             gl.render_pos(ep.x, ep.y))
        if collide["R"]:
            sp = position + (x + w - 1, y)
            ep = position + (x + w - 1, y + h - 1)
            pygame.draw.line(gl.display, color,
                             gl.render_pos(sp.x, sp.y),
                             gl.render_pos(ep.x, ep.y))
        if collide["B"]:
            sp = position + (x, y + h - 1)
            ep = position + (x + w - 1, y + h - 1)
            pygame.draw.line(gl.display, color,
                             gl.render_pos(sp.x, sp.y),
                             gl.render_pos(ep.x, ep.y))

    def check_ground(self, screen=None):
        """
        Return distance from the bottom of entity's bounding box to the ground.
        Negative value means the entity BB is already in the ground (collides
        at the start).

        ``screen`` is accepted for backward compatibility only: collisions are
        always queried from the seamless world.
        """
        result = (gl.SCREEN_Y * (gl.SPRITE_Y + 1))
        world = gl.screen_manager
        if world is not None:
            bbox = self.get_bbox()
            x = bbox.left + self.get_x()
            y = bbox.top + bbox.height + self.get_y()
            w = bbox.width
            me = pygame.Rect(x, y, w, gl.MAX_Y)
            collided = world.colliders_in_rect(me)
            if collided:
                # sorted by y position - probably not necessary anyway
                collided.sort(key=lambda o: o.get_top())
                for coll in collided:
                    # needs to collide from top
                    if coll.get_sides()["T"]:
                        ctop = coll.get_top()
                        if ctop < y:
                            continue
                        return ctop - y
            # Nothing solid below. If the room below does not exist the
            # "void floor" of the current room acts as ground, so the hero
            # does not fall forever at an open map edge.
            gx = (x + w // 2) // gl.MAX_X
            upper_gy = (y - 1) // gl.MAX_Y
            if not world.room_exists(gx, upper_gy + 1):
                result = max(0, (upper_gy + 1) * gl.MAX_Y - y)
        return result

    def check_collision(self, offset, screen=None, ignore_ground=False):
        """Check collision at offset (against the seamless world)."""
        collided = False
        world = gl.screen_manager
        if world is not None:
            me = self.get_bbox().copy()
            me.move_ip(self.get_position() + offset)
            for obj in world.colliders_in_rect(me):
                if obj is self:
                    continue
                sides = obj.get_sides()
                if (offset[0] > 0) and sides["L"]:
                    # move right and left side
                    collided = True
                elif (offset[0] < 0) and sides["R"]:
                    # move left and right side
                    collided = True
                elif (offset[1] > 0) and sides["T"] and not ignore_ground:
                    # move down and top side
                    collided = True
                elif (offset[1] < 0) and sides["B"]:
                    # move up and bottom side
                    collided = True
                if collided:
                    break
            if not collided and world.blocks_void(self, offset):
                # "Void = wall": never leave the existing rooms
                collided = True
        return collided

    def get_touching(self, offset, screen=None):
        """Return objects touching at offset."""
        touched = []
        world = gl.screen_manager
        if world is not None:
            me = self.get_bbox().copy()
            me.move_ip(self.get_position() + offset)
            search = me.inflate(gl.SPRITE_X * 2, gl.SPRITE_Y * 2)
            for obj in world.entities_in_rect(search):
                if obj is self:
                    continue
                you = obj.get_bbox().copy()
                you.move_ip(obj.get_position())
                if me.colliderect(you) and obj.is_touchable():
                    touched.append(obj)
        return touched

    def check_move(self, offset, screen, ignore_ground=False):
        """Check move possibility (offset - move vector)."""
        ox, oy = offset
        touched = []
        assert (ox & oy & 0x01) == 0
        if (ox == 0) and (oy == 0):
            touched.extend(self.get_touching((0, 0), screen))
            return XY(0, 0), touched
        nx, ny = 0, 0
        last_not_colliding = 0, 0
        swap_xy = False
        if abs(ox) < abs(oy):
            swap_xy = True
            oy, ox = ox, oy
        sy = (float(oy) / abs(ox)) * 2
        fy = 0.01
        # pylint: disable-msg=W0612
        # mutilsampling check with step 2 pixels
        for step in range(abs(ox) // 2):
            nx += 2 * ((ox > 0) - (ox < 0))
            fy += sy
            ny = int(fy) & ~0x1
            if swap_xy:
                current_offset = ny, nx
            else:
                current_offset = nx, ny
            touched.extend(self.get_touching(current_offset, screen))
            if self.check_collision(current_offset, screen, ignore_ground):
                break
            last_not_colliding = current_offset
        # pylint: enable-msg=W0612
        return XY.from_tuple(last_not_colliding), touched

    def set_initial_delay(self, mode, param):
        """Set initial delay depending on mode or object's position."""
        pos = self.get_position()
        # Entity positions are world coordinates; the original game used the
        # tile index inside the room, so take it modulo the room size.
        tile_x, tile_y = gl.local_tile(pos.x, pos.y)
        if mode == 0:
            self.delay = (tile_x + tile_y) % (param + 1)
        elif mode == 1:
            self.delay = tile_x % (param + 1)
        elif mode == 2:
            self.delay = tile_y % (param + 1)
        elif mode == 3:
            self.delay = 0
        elif mode == 4:
            self.delay = gl.random(param + 1)
        elif mode == 5:
            self.delay = gl.screen_randoms[tile_x] % (param + 1)
        elif mode == 6:
            self.delay = gl.screen_randoms[tile_y] % (param + 1)
        elif mode == 7:
            self.frame = gl.random(len(self.sprites))
            self.delay = 0

class World:
    """
    The whole level as a single seamless space.

    Replaces the page-based ScreenManager: objects keep world pixel
    coordinates, collisions are queried through a spatial hash and the only
    "screen" left is a room, used for occupancy (void rule), rendering and
    save games. The attribute name ``gl.screen_manager`` is kept so the rest
    of the code keeps working.
    """
    CELL = gl.SPRITE_X  # spatial hash cell size (one tile)

    def __init__(self):
        self.screens = []  # room -> emdata.Screen (live level data)
        self.occupancy = bytearray(gl.ROOMS_TOTAL)  # 1 = room exists
        self.entities = []  # every live active object
        self.new_objects = []  # objects spawned in the current frame
        self.colliders = []  # every static collider
        self.collision_grid = {}  # (cx, cy) -> list of colliders
        self.flags = {}  # runtime marks (broken/removed objects)
        self.loose = []  # objects spawned outside every existing room
        self.current_screen = 0  # room containing the player

    # ------------------------------------------------------------------
    # level loading
    # ------------------------------------------------------------------
    def add_screens(self, screens):
        """Load room definitions (kept name for compatibility)."""
        self.screens = screens if screens is not None else []
        self.rebuild()

    def load_level(self, level=None):
        """(Re)build the world from the current level data."""
        level = level if level is not None else gl.level
        self.add_screens(level.get_screens())

    def rebuild(self):
        """Rebuild occupancy, active entities and the collision index."""
        self.occupancy = bytearray(gl.ROOMS_TOTAL)
        self.entities = []
        self.loose = []
        self.colliders = []
        self.collision_grid = {}
        for number, screen in enumerate(self.screens[:gl.ROOMS_TOTAL]):
            if not screen:
                continue
            self.occupancy[number] = 1
            self.entities.extend(screen.active)
            for collider in screen.collisions:
                self._grid_add(collider)
        logging.info("World built: %d rooms, %d active, %d colliders",
                     sum(self.occupancy), len(self.entities),
                     len(self.colliders))

    def rebuild_colliders(self):
        """Rebuild only the static collision index (level data unchanged)."""
        self.colliders = []
        self.collision_grid = {}
        for screen in self.screens[:gl.ROOMS_TOTAL]:
            if not screen:
                continue
            for collider in screen.collisions:
                self._grid_add(collider)

    def _grid_add(self, collider):
        rect = collider.get_bbox().copy()
        rect.move_ip(collider.get_position())
        self.colliders.append(collider)
        for cx in range(rect.left // self.CELL, rect.right // self.CELL + 1):
            for cy in range(rect.top // self.CELL, rect.bottom // self.CELL + 1):
                self.collision_grid.setdefault((cx, cy), []).append(collider)

    # ------------------------------------------------------------------
    # rooms / occupancy (the "void = wall" rule)
    # ------------------------------------------------------------------
    def get_screens(self):
        return self.screens

    def get_screen(self):
        """Return the room containing the player (compatibility helper)."""
        if 0 <= self.current_screen < len(self.screens):
            return self.screens[self.current_screen]
        return None

    def get_screen_number(self):
        return self.current_screen

    def inspect_screen(self, screen_number):
        """Return a room definition without activating it."""
        if (screen_number < 0) or (screen_number > 255):
            raise ValueError("Screen number out of range (0, 255).")
        if self.screens:
            return self.screens[screen_number]
        return None

    def change_screen(self, screen_number):
        """Track the player's room (no level data is re-initialized)."""
        if (screen_number < 0) or (screen_number > 255):
            raise ValueError("Screen number out of range (0, 255).")
        self.current_screen = screen_number

    def update_current_room(self, position=None):
        """Update current_screen from a world position (player by default)."""
        if position is None and gl.player is not None:
            position = gl.player.get_position()
        if position is not None:
            self.current_screen = gl.room_of(position.x, position.y)
        return self.current_screen

    def room_exists(self, gx, gy):
        """Return True if the room (gx, gy) exists in the level."""
        if not (0 <= gx < gl.ROOMS_X and 0 <= gy < gl.ROOMS_Y):
            return False
        return self.occupancy[gy * gl.ROOMS_X + gx] != 0

    def is_void_at(self, rect):
        """Return True when any corner of rect lies in a non-existing room."""
        for x in (rect.left, rect.right - 1):
            for y in (rect.top, rect.bottom - 1):
                if not self.room_exists(x // gl.MAX_X, y // gl.MAX_Y):
                    return True
        return False

    def blocks_void(self, entity, offset):
        """
        Check the "void = wall" rule for a move of ``entity``.

        Only the leading edge of the proposed box is tested, so an entity
        that already straddles a seam is not locked in place. Upward moves
        use the *drawn* box (``get_void_bbox``) instead of the collision
        box: the hero's artwork is taller than his collision box, so with
        the collision box the head was jumped above a room that has no
        neighbour above (the sprite left the level while the camera stayed
        put, as it is clamped to the room). Downward and sideways moves keep
        the collision box, so nothing can hang on an invisible void edge.
        """
        ox, oy = offset
        if (oy < 0) and not ox:
            box = entity.get_void_bbox()
        else:
            box = entity.get_bbox()
        rect = box.copy()
        rect.move_ip(entity.get_position() + offset)
        if ox and not oy:
            edge = rect.right - 1 if ox > 0 else rect.left
            points = ((edge, rect.top), (edge, rect.centery),
                      (edge, rect.bottom - 1))
        elif oy and not ox:
            edge = rect.bottom - 1 if oy > 0 else rect.top
            points = ((rect.left, edge), (rect.centerx, edge),
                      (rect.right - 1, edge))
        else:
            points = ((rect.left, rect.top), (rect.right - 1, rect.top),
                      (rect.left, rect.bottom - 1),
                      (rect.right - 1, rect.bottom - 1))
        for x, y in points:
            if not self.room_exists(x // gl.MAX_X, y // gl.MAX_Y):
                return True
        return False

    def visible_rooms(self, rect):
        """Return room definitions intersecting rect (world)."""
        result = []
        gx0 = max(0, rect.left // gl.MAX_X)
        gx1 = min(gl.ROOMS_X - 1, rect.right // gl.MAX_X)
        gy0 = max(0, rect.top // gl.MAX_Y)
        gy1 = min(gl.ROOMS_Y - 1, rect.bottom // gl.MAX_Y)
        for gy in range(gy0, gy1 + 1):
            for gx in range(gx0, gx1 + 1):
                index = gy * gl.ROOMS_X + gx
                if 0 <= index < len(self.screens) and self.screens[index]:
                    result.append(self.screens[index])
        return result

    # ------------------------------------------------------------------
    # collision / entity queries
    # ------------------------------------------------------------------
    def colliders_in_rect(self, rect):
        """Return static colliders overlapping rect (world coordinates)."""
        result = []
        seen = set()
        cell = self.CELL
        for cx in range(rect.left // cell, rect.right // cell + 1):
            for cy in range(rect.top // cell, rect.bottom // cell + 1):
                for collider in self.collision_grid.get((cx, cy), ()):
                    key = id(collider)
                    if key in seen:
                        continue
                    seen.add(key)
                    you = collider.get_bbox().copy()
                    you.move_ip(collider.get_position())
                    if rect.colliderect(you):
                        result.append(collider)
        return result

    # Active entities are indexed by room (their spawn room), so a query
    # only has to look at the rooms around it. Half a room of padding keeps
    # objects that crossed a seam into a neighbouring room visible.
    ENTITY_PAD = (gl.MAX_X // 2, gl.MAX_Y // 2)

    def entities_in_rect(self, rect):
        """Return active entities overlapping rect (world coordinates)."""
        search = rect.inflate(self.ENTITY_PAD[0], self.ENTITY_PAD[1])
        result = []
        seen = set()
        for screen in self.visible_rooms(search):
            for entity in screen.active:
                key = id(entity)
                if key in seen:
                    continue
                seen.add(key)
                if entity.world_rect().colliderect(rect):
                    result.append(entity)
        for entity in self.loose:
            if id(entity) in seen:
                continue
            if entity.world_rect().colliderect(rect):
                result.append(entity)
        return result

    # ------------------------------------------------------------------
    # spawning / removal
    # ------------------------------------------------------------------
    def add_active(self, obj):
        """
        Add new objects to waiting queue.
        They will be displayed but not updated in this frame.
        """
        self.new_objects.append(obj)

    def spawn(self, obj):
        """Register an object in the world and in its room's level data."""
        position = obj.get_position()
        if obj not in self.entities:
            self.entities.append(obj)
            # Remember the real spawn cell of runtime objects (projectiles,
            # explosions, debris). Some of them are created at a placeholder
            # position and moved afterwards (Projectile), so without this
            # remove()/vanish() looked for them in room 0 and failed: the
            # "removed" projectile stayed in its room's active list, kept
            # flying through walls and enemies and only died at the activity
            # zone edge (docs/weapon_mechanics.md 6).
            obj.home_position = position.copy()
        room = gl.room_of(position.x, position.y)
        screen = None
        if 0 <= room < len(self.screens):
            screen = self.screens[room]
        if screen is not None:
            if obj not in screen.active:
                screen.active.append(obj)
        elif obj not in self.loose:
            # spawned outside any existing room (map edge): keep it world
            # visible, but it has no room in the level data
            self.loose.append(obj)
        return obj

    def remove(self, obj):
        """Remove an object from the world and from the level data."""
        removed = False
        if obj in self.entities:
            self.entities.remove(obj)
            removed = True
        if obj in self.loose:
            self.loose.remove(obj)
            removed = True
        home = getattr(obj, "home_position", None)
        if not isinstance(home, XY):
            home = obj.get_position()
        room = gl.room_of(home.x, home.y)
        if 0 <= room < len(self.screens):
            screen = self.screens[room]
            if screen is not None and obj in screen.active:
                screen.active.remove(obj)
                return True
        # Safety net: the recorded spawn cell may be wrong (objects created
        # before the cell was stored, restored from an old save). Never leave
        # a dead object in a room's active list - it would keep being updated
        # and displayed.
        for screen in self.screens:
            if screen is not None and obj in screen.active:
                screen.active.remove(obj)
                return True
        return removed

    def add_to_level_data(self, screen, entity):
        """Add an entity to the level definition (compatibility helper)."""
        self.spawn(entity)

    def update_active(self):
        """Move queued objects into the world (once per frame)."""
        if self.new_objects:
            for obj in self.new_objects:
                self.spawn(obj)
            self.new_objects = []

    # ------------------------------------------------------------------
    # camera
    # ------------------------------------------------------------------
    def activity_rect(self):
        """Viewport inflated by half a viewport in every direction."""
        cam = gl.camera
        if cam is None:
            return pygame.Rect(0, 0, gl.MAX_X, gl.MAX_Y).inflate(gl.MAX_X,
                                                                 gl.MAX_Y)
        return cam.activity_rect()

    def _run_x(self, gx, gy):
        """Contiguous run of existing rooms in a row, containing (gx, gy)."""
        if not self.room_exists(gx, gy):
            return None
        lo = gx
        while self.room_exists(lo - 1, gy):
            lo -= 1
        hi = gx
        while self.room_exists(hi + 1, gy):
            hi += 1
        return lo, hi

    def _run_y(self, gx, gy):
        """Contiguous run of existing rooms in a column, containing (gx, gy)."""
        if not self.room_exists(gx, gy):
            return None
        lo = gy
        while self.room_exists(gx, lo - 1):
            lo -= 1
        hi = gy
        while self.room_exists(gx, hi + 1):
            hi += 1
        return lo, hi

    @staticmethod
    def _clamp_into(value, lo, hi):
        """Clamp value into the [lo, hi] range."""
        return max(lo, min(hi, value))

    @staticmethod
    def _intersect_intervals(first, second):
        """Intersect two lists of (lo, hi) camera ranges."""
        result = []
        for alo, ahi in first:
            for blo, bhi in second:
                lo, hi = max(alo, blo), min(ahi, bhi)
                if lo <= hi:
                    result.append((lo, hi))
        return result

    @classmethod
    def _clamp_to_intervals(cls, value, intervals):
        """Clamp value into the interval nearest to it (None when empty)."""
        best = None
        for lo, hi in intervals:
            candidate = cls._clamp_into(value, lo, hi)
            if best is None or abs(candidate - value) < abs(best - value):
                best = candidate
        return best

    def _row_intervals(self, gy):
        """Camera X ranges that keep the viewport inside one run of row gy."""
        if not (0 <= gy < gl.ROOMS_Y):
            return []
        result = []
        gx = 0
        while gx < gl.ROOMS_X:
            if not self.room_exists(gx, gy):
                gx += 1
                continue
            start = gx
            while (gx + 1 < gl.ROOMS_X) and self.room_exists(gx + 1, gy):
                gx += 1
            result.append((start * gl.MAX_X, gx * gl.MAX_X))
            gx += 1
        return result

    def _column_intervals(self, gx):
        """Camera Y ranges that keep the viewport inside one run of column gx."""
        if not (0 <= gx < gl.ROOMS_X):
            return []
        result = []
        gy = 0
        while gy < gl.ROOMS_Y:
            if not self.room_exists(gx, gy):
                gy += 1
                continue
            start = gy
            while (gy + 1 < gl.ROOMS_Y) and self.room_exists(gx, gy + 1):
                gy += 1
            result.append((start * gl.MAX_Y, gy * gl.MAX_Y))
            gy += 1
        return result

    @staticmethod
    def _covered_cells(value, size):
        """Room indices a viewport of ``size`` starting at value covers."""
        return range(value // size, (value + size - 1) // size + 1)

    def _camera_fits(self, x, y, fx, fy):
        """
        True when the viewport at (x, y) shows only existing rooms and still
        contains the hero's room (fx, fy).
        """
        columns = self._covered_cells(x, gl.MAX_X)
        rows = self._covered_cells(y, gl.MAX_Y)
        if fx not in columns or fy not in rows:
            return False
        for gx in columns:
            for gy in rows:
                if not self.room_exists(gx, gy):
                    return False
        return True

    def center_camera(self, focus_x, focus_y):
        """
        Center the camera on (focus_x, focus_y) so that the viewport never
        shows a missing room and never scrolls the hero out of the frame.

        The viewport is exactly one room big, so it covers one or two rooms
        per axis (two when it straddles a seam). A position is valid only
        when *every* covered room exists. The camera therefore starts from
        the hero's own row/column run and is only refined by the runs of the
        extra row/column the viewport happens to cover.

        The previous version intersected the runs of all columns under the
        viewport, so a room located diagonally below-right forced the camera
        a whole room down - the hero left the frame when there was no room
        to his right.
        """
        cam = gl.camera
        if cam is None:
            return
        fx = max(0, min(gl.ROOMS_X - 1, focus_x // gl.MAX_X))
        fy = max(0, min(gl.ROOMS_Y - 1, focus_y // gl.MAX_Y))
        xd = focus_x - gl.MAX_X // 2      # desired (hero centered) position
        yd = focus_y - gl.MAX_Y // 2
        run_x = self._run_x(fx, fy)
        run_y = self._run_y(fx, fy)
        if run_x is None or run_y is None:
            # the hero is outside the level data - follow him anyway
            cam.x = int(xd) & ~1
            cam.y = int(yd) & ~1
            return
        # The hero's row and column always bound the camera: the viewport
        # never leaves the runs the hero belongs to, which keeps him in
        # frame (leaving a run would jump the camera to another room).
        row_limits = (run_x[0] * gl.MAX_X, run_x[1] * gl.MAX_X)
        column_limits = (run_y[0] * gl.MAX_Y, run_y[1] * gl.MAX_Y)
        x = self._clamp_into(xd, *row_limits)
        y = self._clamp_into(yd, *column_limits)
        for _ in range(3):
            # horizontal: every row under the viewport must have a room
            intervals = [row_limits]
            for gy in self._covered_cells(y, gl.MAX_Y):
                if gy != fy:
                    intervals = self._intersect_intervals(
                        intervals, self._row_intervals(gy))
            new_x = self._clamp_to_intervals(xd, intervals)
            if new_x is None:
                x = None
                break
            # vertical: every column under the viewport must have a room
            intervals = [column_limits]
            for gx in self._covered_cells(new_x, gl.MAX_X):
                if gx != fx:
                    intervals = self._intersect_intervals(
                        intervals, self._column_intervals(gx))
            new_y = self._clamp_to_intervals(yd, intervals)
            if new_y is None:
                x = None
                break
            if (new_x, new_y) == (x, y):
                break
            x, y = new_x, new_y
        if (x is None) or not self._camera_fits(x, y, fx, fy):
            # Concave corner (only a diagonal neighbour exists): align the
            # viewport with the hero's column. The viewport then covers the
            # hero's column only, which is always a valid position.
            x = fx * gl.MAX_X
            y = self._clamp_into(yd, *column_limits)
        cam.x = int(x) & ~1
        cam.y = int(y) & ~1

    def snap_camera(self):
        """Center the camera on the player immediately."""
        if gl.camera is None or gl.player is None:
            return
        pos = gl.player.get_position()
        bbox = gl.player.get_bbox()
        self.center_camera(pos.x + bbox.centerx, pos.y + bbox.centery)
        self.update_current_room(pos)

    def update_camera(self):
        """Follow the player (or keep the viewport on the player's room)."""
        cam = gl.camera
        if cam is None or gl.player is None:
            return
        pos = gl.player.get_position()
        bbox = gl.player.get_bbox()
        if cam.enabled:
            self.center_camera(pos.x + bbox.centerx, pos.y + bbox.centery)
        else:
            origin = gl.room_origin(gl.room_of(pos.x, pos.y))
            cam.x, cam.y = origin.x, origin.y
        self.update_current_room(pos)

    # ------------------------------------------------------------------
    # level reset (player death)
    # ------------------------------------------------------------------
    def reset_level(self):
        """
        Reset level to pristine state on player death.
        Matches C code init_level() (EB.C:1382-1405):
        - memcpy(map, level_map, sizeof(map)) - restore all screens
        - Remove already collected disks from restored screens
        """
        self.add_screens(gl.level.reset_screens())

        # Remove collected disks from the restored level (EB.C:1391-1395)
        # In C: for (i = 0; i < disk_num; i++) MAP_REMOVE(disk_x[i], disk_y[i])
        for position in list(gl.disk_positions):
            if not isinstance(position, XY):
                continue
            for entity in list(self.entities):
                if entity.get_position() == position:
                    self.remove(entity)
                    logging.debug("reset_level: Removed collected disk at %s",
                                  position)
                    break

        logging.info("reset_level: Level reset, %d collected disks preserved",
                     len(gl.disk_positions))

    reset = reset_level


# Name kept so existing references (and the plan's wording) still work
ScreenManager = World

class ActiveCheckpoint:
    """
    Active checkpoint class.
    References currently active checkpoint (world coordinates).
    Singleton by design.
    """
    def __init__(self):
        self.level = None
        self.screen = None
        self.position = None

    def update(self, level, position=None):
        self.level = level
        self.screen = None
        self.position = None
        if isinstance(position, XY):
            self.position = copy.copy(position)  # copy to avoid ref issues
            self.screen = gl.room_of(position.x, position.y)
        logging.info("Checkpoint updated: level=%s, pos=%s", level, position)

    def get_level(self):
        return self.level

    def get_screen(self):
        """Room containing the checkpoint (kept for save-game compatibility)."""
        if isinstance(self.position, XY):
            return gl.room_of(self.position.x, self.position.y)
        return self.screen

    def get_position(self):
        return self.position


class Cycle(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)

    def update(self):
        if self.delay > 0:
            self.delay -= 1
        else:
            self.frame = (self.frame + 1) % len(self.sprites)
            self.delay = self.sprites[self.frame].param


class CyclePlus(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.show = False
        self.empty_delay = 0
        # Start "before frame 0" so first increment displays frame 0
        # (matches SHAPE_CNTR=-1 init in shape_rot_plus_init EB_ENEM.C:286)
        self.frame = -1

    def update(self):
        if self.delay > 0:
            self.delay -= 1
            return
        # Matches shape_rot_plus_proc EB_ENEM.C:244-275
        if not self.show:
            self.show = True
        self.frame += 1
        if self.frame == len(self.sprites):
            # Cycle ended: hide and reset for next show
            self.frame = -1
            self.show = False
        if self.show:
            self.delay = self.sprites[self.frame].param
        else:
            self.delay = self.empty_delay

    def display(self):
        if self.show:
            Entity.display(self)

    def is_touchable(self):
        if self.show:
            return Entity.is_touchable(self)

    def get_touch(self):
        if self.show:
            return Entity.get_touch(self)
        else:
            return 0

class Pulse(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.direction = 1  # 1 up -1 down

    def update(self):
        if self.delay > 0:
            self.delay -= 1
        else:
            self.frame += self.direction
            if self.frame < 0:
                self.frame = 0
                self.direction *= -1
            elif self.frame == len(self.sprites):
                self.frame -= 1
                self.direction *= -1
            self.delay = self.sprites[self.frame].param


class PulsePlus(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.direction = 1  # 1 up -1 down
        self.show = False
        self.empty_delay = 0
        # Start "before frame 0" so first increment displays frame 0
        # (matches SHAPE_CNTR=-1 init in shape_pulse_plus_init EB_ENEM.C:341)
        self.frame = -1

    def update(self):
        if self.delay > 0:
            self.delay -= 1
            return
        # Matches shape_pulse_plus_proc EB_ENEM.C:294-330
        if not self.show:
            self.show = True
        self.frame += self.direction
        if self.frame < 0:
            # End of cycle: hide and reset for next show (CNTR=-1, AUX_2=0 in C)
            self.frame = -1
            self.show = False
            self.direction = 1
        elif self.frame == len(self.sprites):
            # Bounce at top (SHAPE_CNTR = SHAPES_NUM - 2 in C)
            self.frame -= 2
            self.direction = -1
        if self.show:
            self.delay = self.sprites[self.frame].param
        else:
            self.delay = self.empty_delay

    def display(self):
        if self.show:
            Entity.display(self)

    def is_touchable(self):
        if self.show:
            return Entity.is_touchable(self)

    def get_touch(self):
        if self.show:
            return Entity.get_touch(self)
        else:
            return 0

class Flash(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.show = False

    def display(self):
        if self.show:
            Entity.display(self)

    def update(self):
        if self.delay > 0:
            self.delay -= 1
        else:
            self.show = not self.show
            self.delay = self.sprites[self.frame].param


class FlashPlus(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.show = False
        self.empty_delay = 0  # off-phase duration = preceding sprite's param

    def display(self):
        if self.show:
            Entity.display(self)

    def update(self):
        # Toggle visibility. On-phase duration = this sprite's param; off-phase
        # duration = the preceding sprite's param (empty_delay). Matches
        # flash_plus_proc EB_ENEM.C:345-384 (visible uses st[SHAPE].PARAMB,
        # invisible uses st[FIRST_SHAPE-1].PARAMB).
        if self.delay > 0:
            self.delay -= 1
        else:
            self.show = not self.show
            if self.show:
                self.delay = self.sprites[self.frame].param
            else:
                self.delay = self.empty_delay

    def get_touch(self):
        if self.show:
            return Entity.get_touch(self)
        else:
            return 0


class FlashSpecial(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.show = False

    def display(self):
        if self.show:
            Entity.display(self)

    def update(self):
        if self.delay > 0:
            self.delay -= 1
        else:
            self.show = not self.show
            self.delay = 2


class RocketUp(Entity):
    """
    Rocket that fires upward when player passes below.
    Based on EB_ENEM.C:400-484 (rocket_proc).
    """
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.state = "waiting"
        self.speed = 0
        self.initialized = False

    def update(self):
        if not self.initialized:
            # Speed from sprite param, 2x scaled (Y_STEP = st[PARAMB], EB_ENEM.C:436)
            sprite = self.sprites[0] if self.sprites else None
            self.speed = sprite.param * 2 if sprite and sprite.param > 0 else 8
            self.initialized = True

        if self.state == "waiting":
            self.check_trigger()
        else:
            self.fly()

    def check_trigger(self):
        """Fire when player is aligned above - EB_ENEM.C:422-441"""
        if not gl.player:
            return

        player_pos = gl.player.get_position()
        my_pos = self.get_position()
        bbox = self.get_bbox()

        # Hero center point: HERO_X+12, HERO_Y+24 (2x scaled)
        player_cx = player_pos.x + 24
        player_cy = player_pos.y + 48

        # Check horizontal alignment (XB-8 to XE+8, 2x scaled)
        xb = my_pos.x + bbox.x - 16
        xe = my_pos.x + bbox.x + bbox.width + 16
        my_top = my_pos.y + bbox.y

        # Player must be ABOVE rocket (y < YB, EB_ENEM.C:431)
        if xb < player_cx < xe and player_cy < my_top:
            # 1/8 chance per frame to fire (EB_ENEM.C:436)
            if gl.random(8) == 0:
                self.state = "flying"
                logging.debug("RocketUp triggered at %s", my_pos)

    def fly(self):
        """Move upward until collision - EB_ENEM.C:442-448"""
        self.position.y -= self.speed

        # Animate
        self.frame = (self.frame + 1) % len(self.sprites) if self.sprites else 0

        # Wall collision
        if self.check_collision(XY(0, -self.speed)):
            from emhero import put_explosion
            put_explosion(self.position.x, self.position.y)
            snd.play_sound('blast')
            self.vanish()
            return

        # Left the activity zone
        world = gl.screen_manager
        if world is not None and self.world_rect().bottom < \
                world.activity_rect().top:
            self.vanish()


class RocketDown(Entity):
    """
    Rocket that fires downward when player passes above.
    Based on EB_ENEM.C:400-484 (rocket_proc).
    """
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.state = "waiting"
        self.speed = 0
        self.initialized = False

    def update(self):
        if not self.initialized:
            # Speed from sprite param, 2x scaled (Y_STEP = st[PARAMB], EB_ENEM.C:479)
            sprite = self.sprites[0] if self.sprites else None
            self.speed = sprite.param * 2 if sprite and sprite.param > 0 else 8
            self.initialized = True

        if self.state == "waiting":
            self.check_trigger()
        else:
            self.fly()

    def check_trigger(self):
        """Fire when player is aligned below - EB_ENEM.C:465-484"""
        if not gl.player:
            return

        player_pos = gl.player.get_position()
        my_pos = self.get_position()
        bbox = self.get_bbox()

        # Hero center point: HERO_X+12, HERO_Y+24 (2x scaled)
        player_cx = player_pos.x + 24
        player_cy = player_pos.y + 48

        # Check horizontal alignment (XB-8 to XE+8, 2x scaled)
        xb = my_pos.x + bbox.x - 16
        xe = my_pos.x + bbox.x + bbox.width + 16
        my_bottom = my_pos.y + bbox.y + bbox.height

        # Player must be BELOW rocket (y > YE, EB_ENEM.C:474)
        if xb < player_cx < xe and player_cy > my_bottom:
            # 1/8 chance per frame to fire (EB_ENEM.C:436)
            if gl.random(8) == 0:
                self.state = "flying"
                logging.debug("RocketDown triggered at %s", my_pos)

    def fly(self):
        """Move downward until collision"""
        self.position.y += self.speed

        # Animate
        self.frame = (self.frame + 1) % len(self.sprites) if self.sprites else 0

        # Wall collision
        if self.check_collision(XY(0, self.speed)):
            from emhero import put_explosion
            put_explosion(self.position.x, self.position.y)
            snd.play_sound('blast')
            self.vanish()
            return

        # Left the activity zone
        world = gl.screen_manager
        if world is not None and self.world_rect().top > \
                world.activity_rect().bottom:
            self.vanish()


class KillingFloor(Entity):
    """
    One-time trigger that removes bottom row collisions.
    Based on EB_ENEM.C:486-492.
    When activated, player will die if they fall to the bottom of the screen.
    """
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.activated = False

    def update(self):
        if not self.activated:
            self.activated = True
            gl.killing_floor = True

            # Remove bottom row collisions (EB_ENEM.C:491)
            world = gl.screen_manager
            if world is not None:
                pos = self.get_position()
                room = gl.room_of(pos.x, pos.y)
                screen = None
                if 0 <= room < len(world.screens):
                    screen = world.screens[room]
                if screen:
                    bottom_y = (gl.room_origin(room).y +
                                (gl.SCREEN_Y - 1) * gl.SPRITE_Y)
                    # Filter out collision objects at the bottom row
                    screen.collisions = [c for c in screen.collisions
                                         if c.get_y() < bottom_y]
                    world.rebuild_colliders()
            logging.debug("KillingFloor activated - bottom collisions removed")
            self.vanish()


class Monitor(Entity):
    """
    Flickering monitor sprite - matches monitor_proc EB_ENEM.C:214-241.
    Frame normally toggles between 0 and 1 each tick; rarely (1/128 chance)
    plays a longer "special" animation from frame 2+.
    """
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.counter = 0

    def update(self):
        if self.counter == 0:
            # Normal flicker between first two frames
            choices = min(2, len(self.sprites))
            self.frame = gl.random(choices)
            # 1/128 chance to play a "special" animation
            if len(self.sprites) > 2 and gl.random(128) == 0:
                self.frame = gl.random(len(self.sprites) - 2) + 2
                param = self.sprites[self.frame].param
                if param > 0:
                    self.counter = param + gl.random(param)
        else:
            self.counter -= 1
            if self.counter == 0:
                # End of special animation - back to normal flicker next tick
                self.frame = 0


class Display(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)


class Checkpoint(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.activated = False
        self.spent = False  # retired checkpoint: can never be activated again
        # Load activation cross sprite from info set
        self.cross_sprite = None
        if gl.info:
            self.cross_sprite = gl.info.get_sprite(5)  # small cross sprite

    def _frame_for_param(self, param_value, fallback):
        """
        Return the animation frame whose status byte 'param' matches.
        The sprite set encodes the checkpoint state this way: the frame with
        param = 1 is the current/active look, the frame with param = 0 is the
        unvisited (inactive) look.
        """
        for index, sprite in enumerate(self.sprites):
            if sprite is not None and sprite.param == param_value:
                return index
        return fallback

    def activate(self):
        """Make this checkpoint the current (active) respawn point."""
        self.activated = True
        self.spent = False
        # current checkpoint uses the param = 1 frame
        self.frame = self._frame_for_param(1, max(0, len(self.sprites) - 1))

    def deactivate(self):
        """
        Retire this checkpoint after another one was activated.
        A retired checkpoint stays inactive and cannot be re-activated.
        """
        self.activated = False
        self.spent = True
        # inactive look is the param = 0 frame
        self.frame = self._frame_for_param(0, 0)

    def display(self):
        """Display checkpoint; the cross marks already retired ones."""
        Entity.display(self)
        # Cross overlay is drawn only on retired (spent) checkpoints
        if self.spent and self.cross_sprite:
            pos = self.get_position()
            scaled_cross = di.scale_sprite(self.cross_sprite.image)
            scaled_pos = gl.render_pos(pos.x, pos.y)
            gl.display.blit(scaled_cross, scaled_pos)


def sync_checkpoint_entities():
    """
    Align checkpoint sprites with the active checkpoint data: the sprite at
    the current respawn point becomes active, the rest keep their state
    (retired ones stay spent).
    """
    if gl.checkpoint is None or gl.screen_manager is None:
        return
    position = gl.checkpoint.get_position()
    if position is None:
        return
    for item in gl.screen_manager.entities:
        if isinstance(item, Checkpoint) and item.get_position() == position:
            item.activate()
            gl.checkpoint_entity = item
            logging.info("Checkpoint sprite synced: pos=%s", position)
            return


class Teleport(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)


class TeleportBase(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)


class Exit(Entity):
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        # The indicator sprite (yellow triangle) will be set by emdata.__init_exit()
        # It loads the sprite at index (exit_index + 1) from the level sprite set
        self.indicator_sprite = None
        self.indicator_entity = None

    def update(self):
        """Create indicator entity when 3 disks collected"""
        if gl.disks >= 3 and self.indicator_sprite and not self.indicator_entity:
            # Create a touchable indicator entity above the exit
            pos = self.get_position()
            indicator_pos = XY(pos.x, pos.y - gl.SPRITE_Y)
            self.indicator_entity = ExitIndicator([self.indicator_sprite], indicator_pos)
            # Add to active entities so it can be touched
            world = gl.screen_manager
            if world is not None:
                world.spawn(self.indicator_entity)


class ExitIndicator(Entity):
    """The touchable indicator sprite that appears above the exit"""
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)

    def get_touch(self):
        """Exit indicators should return touch type 6 for exit handling"""
        return 6

    def display(self):
        """Display indicator only when blinking"""
        if gl.counter & 0x04:
            Entity.display(self)


class CannonBase(Entity):
    """
    Base class for cannons - matches cannon_proc (EB_ENEM.C:645-679)
    Fires projectiles at regular intervals with randomization.
    """
    def __init__(self, sprites, position, direction):
        Entity.__init__(self, sprites, position)
        self.direction = direction  # XY for projectile direction
        self.fire_timer = 0
        self.fire_interval = 0
        self.projectile_speed = 8  # Default, overridden by sprite param
        self.projectile_sprite = None  # Set by emdata.py - last sprite in animation
        self.initialized = False

    def update(self):
        if not self.initialized:
            # Firing interval = cannon sprite's param in frames (AUX_2,
            # EB_ENEM.C:691). Speed = the PROJECTILE sprite's param — the last
            # frame of the cannon animation — read after obj = new_obj
            # (EB_ENEM.C:661-671), 2x scaled.
            sprite = self.sprites[0] if self.sprites else None
            param = sprite.param if sprite and sprite.param > 0 else 8
            self.fire_interval = param  # frames - no scaling
            if self.projectile_sprite and self.projectile_sprite.param > 0:
                self.projectile_speed = self.projectile_sprite.param * 2
            else:
                self.projectile_speed = 8
            # Initial random delay: random(param) - EB_ENEM.C:690
            self.fire_timer = gl.random(param) if param > 0 else 0
            self.initialized = True
            logging.debug("Cannon init: interval=%d, speed=%d, initial_timer=%d",
                         self.fire_interval, self.projectile_speed, self.fire_timer)
            return

        if self.fire_timer > 0:
            self.fire_timer -= 1
        else:
            self.fire_projectile()
            # Reset: param + random(param) - EB_ENEM.C:653
            self.fire_timer = self.fire_interval + gl.random(self.fire_interval)

    def fire_projectile(self):
        """Fire a projectile in the cannon's direction"""
        # Get cannon and projectile bounding boxes for spawn position calculation
        cannon_pos = self.get_position()
        cannon_bbox = self.get_bbox()

        # Projectile uses projectile_sprite set during init (last sprite in cannon's animation)
        proj_sprites = []
        proj_bbox = pygame.Rect(0, 0, 24, 24)  # Default
        if self.projectile_sprite:
            proj_sprites = [self.projectile_sprite]
            proj_bbox = self.projectile_sprite.bbox
        else:
            logging.warning("Cannon has no projectile_sprite set!")

        # Calculate spawn position based on direction (EB_ENEM.C:688, 703, 718, 733)
        # Projectile spawns at cannon edge in firing direction
        pos = cannon_pos.copy()
        if self.direction.x < 0:  # Left: X = X + cannon_left - proj_right - 1
            pos.x = cannon_pos.x + cannon_bbox.x - (proj_bbox.x + proj_bbox.width) - 1
        elif self.direction.x > 0:  # Right: X = X + cannon_right - proj_left + 1
            pos.x = cannon_pos.x + cannon_bbox.x + cannon_bbox.width - proj_bbox.x + 1
        elif self.direction.y < 0:  # Up: Y = Y + cannon_top - proj_bottom - 1
            pos.y = cannon_pos.y + cannon_bbox.y - (proj_bbox.y + proj_bbox.height) - 1
        elif self.direction.y > 0:  # Down: Y = Y + cannon_bottom - proj_top + 1
            pos.y = cannon_pos.y + cannon_bbox.y + cannon_bbox.height - proj_bbox.y + 1

        # Velocity based on direction and speed (EB_ENEM.C:668-671)
        velocity = XY(self.direction.x * self.projectile_speed,
                     self.direction.y * self.projectile_speed)

        proj = EnemyProjectile(proj_sprites, pos, velocity)
        gl.screen_manager.add_active(proj)
        snd.play_sound('laser')
        logging.debug("Cannon fired projectile at %s with velocity %s", pos, velocity)


class CannonLeft(CannonBase):
    def __init__(self, sprites, position):
        CannonBase.__init__(self, sprites, position, XY(-1, 0))


class CannonRight(CannonBase):
    def __init__(self, sprites, position):
        CannonBase.__init__(self, sprites, position, XY(1, 0))


class CannonUp(CannonBase):
    def __init__(self, sprites, position):
        CannonBase.__init__(self, sprites, position, XY(0, -1))


class CannonDown(CannonBase):
    def __init__(self, sprites, position):
        CannonBase.__init__(self, sprites, position, XY(0, 1))


class EnemyPlatform(Entity):
    """
    Platform enemy - patrols left/right on platforms.
    Based on EB_ENEM.C:867-944 (platform_creature_init/proc).
    """
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.shoots = False
        self.anims = None
        self.frames = 0
        self.frame = 0
        self.anim = "MLEFT"
        # AI state
        self.state = "init"
        self.x_step = -2  # Movement speed/direction
        self.shoot_timer = 0  # Shoot countdown timer
        self.left_boundary = 0   # Left patrol boundary
        self.right_boundary = 0  # Right patrol boundary
        self.anim_delay = 0     # Animation delay counter
        self.initialized = False

    def update(self):
        if not self.initialized:
            self.initialize_patrol()
            return

        if self.state == "patrol":
            self.update_patrol()
        elif self.state == "shoot":
            self.update_shoot()

    def initialize_patrol(self):
        """Find platform boundaries - EB_ENEM.C:867-944"""
        pos = self.get_position()
        room = gl.room_of(pos.x, pos.y)
        origin = gl.room_origin(room)
        # The scan never leaves the enemy's own room (C used the screen edge)
        room_left = origin.x
        room_right = origin.x + gl.MAX_X - gl.SPRITE_X

        # Scan right for boundary (platform edge or wall)
        # C uses 24px steps (one tile); in 2× space that is SPRITE_X (48px)
        x = pos.x
        for _ in range(12):  # Max 12 tiles (576 pixels)
            if x + gl.SPRITE_X > room_right:
                break
            # Check wall collision to right
            if self.would_collide_at(XY(x + gl.SPRITE_X, pos.y), XY(1, 0)):
                break
            # Check if ground continues
            if not self.has_ground_at(x + gl.SPRITE_X, pos.y):
                break
            x += gl.SPRITE_X
        self.right_boundary = x

        # Scan left for boundary
        x = pos.x
        for _ in range(12):
            if x - gl.SPRITE_X < room_left:
                break
            if self.would_collide_at(XY(x - gl.SPRITE_X, pos.y), XY(-1, 0)):
                break
            if not self.has_ground_at(x - gl.SPRITE_X, pos.y):
                break
            x -= gl.SPRITE_X
        self.left_boundary = x

        # Remove creatures whose patrol span is under one tile
        # (C: if ((AUX_2 - AUX_1) < 24) REMOVE_OBJ, EB_ENEM.C:933).
        if self.right_boundary - self.left_boundary < gl.SPRITE_X:
            self.initialized = True
            self.vanish()
            return

        # Face player (EB_ENEM.C:903-912)
        if gl.player and gl.player.get_x() > pos.x:
            self.x_step = abs(self.x_step)
            self.anim = "MRIGHT"
        else:
            self.x_step = -abs(self.x_step)
            self.anim = "MLEFT"

        # Init shoot timer if enemy shoots (EB_ENEM.C:917-920)
        if self.shoots:
            self.shoot_timer = 32 + gl.random(64)

        # Initial step delay: random(256) % ((PARAMB & 0x0f) + 1) (EB_ENEM.C:941)
        param = self.sprites[0].param if self.sprites else 0
        self.anim_delay = gl.random(256) % ((param & 0x0f) + 1)
        self.initialized = True
        self.state = "patrol"
        logging.debug("EnemyPlatform initialized: pos=%s, bounds=[%d, %d]",
                     pos, self.left_boundary, self.right_boundary)

    def would_collide_at(self, pos, direction, screen=None):
        """Check if there's a wall collision at position in direction"""
        world = gl.screen_manager
        if world is None:
            return False
        me = self.get_bbox().copy()
        me.move_ip(pos)
        for obj in world.colliders_in_rect(me):
            if obj is self:
                continue
            sides = obj.get_sides()
            if direction.x > 0 and sides["L"]:
                return True
            elif direction.x < 0 and sides["R"]:
                return True
        return False

    def has_ground_at(self, x, y, screen=None):
        """Check if there's ground below a position"""
        world = gl.screen_manager
        if world is None:
            return False
        # Check for collision block below
        check_y = y + gl.SPRITE_Y
        me = pygame.Rect(x, check_y, 2, gl.SPRITE_Y)
        for obj in world.colliders_in_rect(me):
            obj_pos = obj.get_position()
            obj_bbox = obj.get_bbox()
            obj_top = obj_pos.y + obj_bbox.y
            obj_left = obj_pos.x + obj_bbox.x
            obj_right = obj_pos.x + obj_bbox.x + obj_bbox.w
            if (obj.get_sides()["T"] and
                obj_top >= check_y and obj_top < check_y + gl.SPRITE_Y and
                obj_left <= x < obj_right):
                return True
        return False

    def update_patrol(self):
        """Patrol movement - EB_ENEM.C:814-865"""
        if self.anim_delay > 0:
            self.anim_delay -= 1
            return

        # Shooting countdown. The timer floors at 0 and HOLDS there until the
        # animation aligns (frame == 0), matching C's "Y_STEP floors at 0x80,
        # then fire when SHAPE_CNTR == 0" logic (EB_ENEM.C:821-831). A `> 0`
        # guard would permanently jam the enemy if the timer expired off-frame.
        if self.shoots:
            if self.shoot_timer > 0:
                self.shoot_timer -= 1
            if self.shoot_timer == 0 and self.frame == 0:
                # Warning sound based on distance (EB_ENEM.C:826-829).
                # Threshold is 2x scaled (C compares unscaled X_STEP < 5).
                if abs(self.x_step) < 10:
                    snd.play_sound('warning')
                else:
                    snd.play_sound('warning2')
                self.anim_delay = 16
                self.shoot_timer = 32 + gl.random(64)
                self.state = "shoot"
                return

        # Move
        self.position.x += self.x_step

        # Animate
        anim_sprites = self.anims.get(self.anim, []) if self.anims else []
        max_frames = len(anim_sprites) if anim_sprites else 1
        self.frame = (self.frame + 1) % max_frames

        # Per-step delay from sprite PARAMB lower nibble (EB_ENEM.C:837)
        # CNTR = st[PARAMB] & 0x0f; — controls movement speed between steps
        sprite = self._get_current_sprite()
        param = sprite.param if sprite else 0
        self.anim_delay = param & 0x0f

        # Boundary check - reverse direction at edges
        if self.x_step < 0 and self.position.x <= self.left_boundary:
            self.x_step = -self.x_step
            self.anim = "MRIGHT"
            self.frame = 0
        elif self.x_step > 0 and self.position.x >= self.right_boundary:
            self.x_step = -self.x_step
            self.anim = "MLEFT"
            self.frame = 0

    def update_shoot(self):
        """Fire projectile - EB_ENEM.C:770-812"""
        if self.anim_delay > 0:
            self.anim_delay -= 1
            return

        pos = self.get_position()
        bbox = self.get_bbox()

        # The projectile sprite is the enemy's own shot animation: SLEFT when
        # firing left, SRIGHT when firing right (C: NEW_SHAPE_NUM = SHAPE_NUM
        # + 2 / + 1, EB_ENEM.C:783,794). Speed is the shot sprite's own param,
        # 2x scaled (NEW_X_STEP = -/+ st[PARAMB], EB_ENEM.C:786,797).
        if self.x_step < 0:
            proj_sprites = self.anims.get("SLEFT", []) if self.anims else []
            speed = (proj_sprites[0].param * 2) if proj_sprites else 4
            velocity = XY(-speed, 0)
            # spawn one tile left of the bbox: NEW_X = XB - 24 (2x), NEW_Y = Y
            spawn = XY(pos.x + bbox.x - gl.SPRITE_X, pos.y)
        else:
            proj_sprites = self.anims.get("SRIGHT", []) if self.anims else []
            speed = (proj_sprites[0].param * 2) if proj_sprites else 4
            velocity = XY(speed, 0)
            # spawn just right of the bbox: NEW_X = XE + 1 (2x), NEW_Y = Y
            spawn = XY(pos.x + bbox.x + bbox.w + 2, pos.y)

        proj = EnemyProjectile(proj_sprites, spawn, velocity)
        gl.screen_manager.add_active(proj)
        snd.play_sound('shoot')
        logging.debug("EnemyPlatform fired projectile at %s", spawn)

        self.state = "patrol"

    def _get_current_sprite(self):
        """Helper to get current animation sprite safely"""
        if self.anims and self.anim in self.anims:
            anim_sprites = self.anims[self.anim]
            if anim_sprites:
                frame = self.frame % len(anim_sprites)
                return anim_sprites[frame]
        return None

    def get_bbox(self):
        """Override to use anims instead of sprites for bounding box"""
        sprite = self._get_current_sprite()
        if sprite:
            return sprite.bbox
        return pygame.Rect(0, 0, gl.SPRITE_X, gl.SPRITE_Y)

    def get_sides(self):
        """Override to use anims instead of sprites"""
        sprite = self._get_current_sprite()
        if sprite:
            return sprite.collide
        return {"L": False, "R": False, "T": False, "B": False}

    def is_touchable(self):
        """Enemies are not touchable (they kill on collision instead)"""
        return False

    def get_touch(self):
        """Enemies don't have touch type"""
        return 0

    def take_damage(self, damage):
        """Enemy hit by projectile - instant kill (EB_ENEM.C:70-89)"""
        self.die()

    def die(self):
        """Enemy destruction - matches xplode() from EB_ENEM.C:70-89.
        xplode() in C is silent; blast_s was already played by the caller
        (miss_end_proc / short_miss_proc / long_miss_proc / bow_proc).
        """
        bbox = self.get_bbox()
        pos = self.get_position()
        center_x = pos.x + bbox.x + bbox.w // 2 - 12
        center_y = pos.y + bbox.y + bbox.h // 2 - 12
        from emhero import put_explosion
        logging.debug("Enemy destroyed at pos %s, explosion at (%d,%d)",
                     pos, center_x, center_y)
        put_explosion(center_x, center_y)
        self.vanish()

    def display(self):
        # Scale enemy sprite by the render coefficient
        if self.anims and self.anim in self.anims:
            anim_sprites = self.anims[self.anim]
            if anim_sprites and self.frame < len(anim_sprites):
                scaled_image = di.scale_sprite(anim_sprites[self.frame].image)
                scaled_pos = gl.render_pos(self.get_position().x,
                                           self.get_position().y)
                gl.display.blit(scaled_image, scaled_pos)

class EnemyFlying(Entity):
    """
    Flying enemy - patrols left/right in the air (doesn't need platforms).
    Based on EB_ENEM.C:867-944 with flying creature modifications.
    Fires DOWNWARD projectiles (unlike platform enemies).
    """
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.shoots = False
        self.anims = None
        self.frames = 0
        self.frame = 0
        self.anim = "MLEFT"
        # AI state
        self.state = "init"
        self.x_step = -2  # Movement speed/direction
        self.shoot_timer = 0  # Shoot countdown timer
        self.left_boundary = 0   # Left patrol boundary
        self.right_boundary = 0  # Right patrol boundary
        self.anim_delay = 0     # Animation delay counter
        self.initialized = False

    def update(self):
        if not self.initialized:
            self.initialize_patrol()
            return

        if self.state == "patrol":
            self.update_patrol()
        elif self.state == "shoot":
            self.update_shoot()

    def initialize_patrol(self):
        """Find patrol boundaries - EB_ENEM.C:867-944 (no ground check for flying)"""
        pos = self.get_position()
        room = gl.room_of(pos.x, pos.y)
        origin = gl.room_origin(room)
        # The scan never leaves the enemy's own room (C clamped at the
        # screen edge, EB_ENEM.C:1039-1068).
        room_left = origin.x
        room_right = origin.x + gl.MAX_X - gl.SPRITE_X

        # Scan right for boundary (wall only - no ground check for flying).
        # C probes up to ~300px (2x = 600) and clamps at the screen edge.
        # Use full-tile (SPRITE_X) steps like the platform scan.
        x = pos.x
        for _ in range(gl.SCREEN_X):
            if x + gl.SPRITE_X > room_right:
                break
            if self.would_collide_at(XY(x + gl.SPRITE_X, pos.y), XY(1, 0)):
                break
            x += gl.SPRITE_X
        self.right_boundary = x

        # Scan left for boundary
        x = pos.x
        for _ in range(gl.SCREEN_X):
            if x - gl.SPRITE_X < room_left:
                break
            if self.would_collide_at(XY(x - gl.SPRITE_X, pos.y), XY(-1, 0)):
                break
            x -= gl.SPRITE_X
        self.left_boundary = x

        # Remove creatures whose patrol span is under one tile
        # (C: if ((AUX_2 - AUX_1) < 24) REMOVE_OBJ, EB_ENEM.C:1073).
        if self.right_boundary - self.left_boundary < gl.SPRITE_X:
            self.initialized = True
            self.vanish()
            return

        # Face player
        if gl.player and gl.player.get_x() > pos.x:
            self.x_step = abs(self.x_step)
            self.anim = "MRIGHT"
        else:
            self.x_step = -abs(self.x_step)
            self.anim = "MLEFT"

        # Init shoot timer if enemy shoots
        if self.shoots:
            self.shoot_timer = 32 + gl.random(64)

        # Initial step delay: random(256) % ((PARAMB & 0x0f) + 1) (EB_ENEM.C:1081)
        param = self.sprites[0].param if self.sprites else 0
        self.anim_delay = gl.random(256) % ((param & 0x0f) + 1)
        self.initialized = True
        self.state = "patrol"
        logging.debug("EnemyFlying initialized: pos=%s, bounds=[%d, %d]",
                     pos, self.left_boundary, self.right_boundary)

    def would_collide_at(self, pos, direction, screen=None):
        """Check if there's a wall collision at position in direction"""
        world = gl.screen_manager
        if world is None:
            return False
        me = self.get_bbox().copy()
        me.move_ip(pos)
        for obj in world.colliders_in_rect(me):
            if obj is self:
                continue
            sides = obj.get_sides()
            if direction.x > 0 and sides["L"]:
                return True
            elif direction.x < 0 and sides["R"]:
                return True
        return False

    def update_patrol(self):
        """Patrol movement"""
        if self.anim_delay > 0:
            self.anim_delay -= 1
            return

        # Shooting countdown - floor at 0 and hold until the frame aligns
        # (see EnemyPlatform.update_patrol; EB_ENEM.C:988-995).
        if self.shoots:
            if self.shoot_timer > 0:
                self.shoot_timer -= 1
            if self.shoot_timer == 0 and self.frame == 0:
                # Warning sound (EB_ENEM.C:993)
                snd.play_sound('warning2')
                self.anim_delay = 16
                self.shoot_timer = 32 + gl.random(64)
                self.state = "shoot"
                return

        # Move
        self.position.x += self.x_step

        # Animate
        anim_sprites = self.anims.get(self.anim, []) if self.anims else []
        max_frames = len(anim_sprites) if anim_sprites else 1
        self.frame = (self.frame + 1) % max_frames

        # Per-step delay from current sprite PARAMB lower nibble (EB_ENEM.C:1001).
        # Platform enemies already do this; flying enemies were missing it.
        sprite = self._get_current_sprite()
        param = sprite.param if sprite else 0
        self.anim_delay = param & 0x0f

        # Boundary check - reverse direction at edges. Unlike platform creatures
        # (EB_ENEM.C:846,856), the flying proc changes SHAPE_NUM but does NOT
        # reset SHAPE_CNTR on the flip (EB_ENEM.C:1003-1020), so the frame
        # carries over. (Moot for the shipped flying enemy: its MLEFT/MRIGHT are
        # single-frame, but kept faithful.)
        if self.x_step < 0 and self.position.x <= self.left_boundary:
            self.x_step = -self.x_step
            self.anim = "MRIGHT"
        elif self.x_step > 0 and self.position.x >= self.right_boundary:
            self.x_step = -self.x_step
            self.anim = "MLEFT"

    def update_shoot(self):
        """Fire projectile DOWNWARD (unlike platform enemy) - EB_ENEM.C:947-974"""
        if self.anim_delay > 0:
            self.anim_delay -= 1
            return

        pos = self.get_position()
        bbox = self.get_bbox()

        # Projectile sprite is the enemy's own shot animation (SLEFT/SRIGHT
        # selected by facing, C: NEW_SHAPE_NUM = SHAPE_NUM + 2 / + 1,
        # EB_ENEM.C:958-961). Flying shots travel straight down at the shot
        # sprite's param speed, 2x scaled (NEW_Y_STEP = st[PARAMB], :966).
        if self.x_step < 0:
            proj_sprites = self.anims.get("SLEFT", []) if self.anims else []
        else:
            proj_sprites = self.anims.get("SRIGHT", []) if self.anims else []
        speed = (proj_sprites[0].param * 2) if proj_sprites else 4
        velocity = XY(0, speed)
        # spawn just below the bbox: NEW_X = X, NEW_Y = YE + 1 (2x)
        spawn = XY(pos.x, pos.y + bbox.y + bbox.h + 2)

        proj = EnemyProjectile(proj_sprites, spawn, velocity)
        gl.screen_manager.add_active(proj)
        # C plays laser_s for flying creature shot (EB_ENEM.C:954),
        # same sample as cannons. There is no eshoot_s in the C source.
        snd.play_sound('laser')
        logging.debug("EnemyFlying fired projectile at %s (downward)", spawn)

        self.state = "patrol"

    def _get_current_sprite(self):
        """Helper to get current animation sprite safely"""
        if self.anims and self.anim in self.anims:
            anim_sprites = self.anims[self.anim]
            if anim_sprites:
                frame = self.frame % len(anim_sprites)
                return anim_sprites[frame]
        return None

    def get_bbox(self):
        """Override to use anims instead of sprites for bounding box"""
        sprite = self._get_current_sprite()
        if sprite:
            return sprite.bbox
        return pygame.Rect(0, 0, gl.SPRITE_X, gl.SPRITE_Y)

    def get_sides(self):
        """Override to use anims instead of sprites"""
        sprite = self._get_current_sprite()
        if sprite:
            return sprite.collide
        return {"L": False, "R": False, "T": False, "B": False}

    def is_touchable(self):
        """Enemies are not touchable (they kill on collision instead)"""
        return False

    def get_touch(self):
        """Enemies don't have touch type"""
        return 0

    def take_damage(self, damage):
        """Enemy hit by projectile - instant kill (EB_ENEM.C:70-89)"""
        self.die()

    def die(self):
        """Enemy destruction - matches xplode() from EB_ENEM.C:70-89.
        xplode() in C is silent; blast_s was already played by the caller
        (miss_end_proc / short_miss_proc / long_miss_proc / bow_proc).
        """
        bbox = self.get_bbox()
        pos = self.get_position()
        center_x = pos.x + bbox.x + bbox.w // 2 - 12
        center_y = pos.y + bbox.y + bbox.h // 2 - 12
        from emhero import put_explosion
        logging.debug("EnemyFlying destroyed at pos %s, explosion at (%d,%d)",
                     pos, center_x, center_y)
        put_explosion(center_x, center_y)
        self.vanish()

    def display(self):
        # Scale enemy sprite by the render coefficient
        if self.anims and self.anim in self.anims:
            anim_sprites = self.anims[self.anim]
            if anim_sprites and self.frame < len(anim_sprites):
                scaled_image = di.scale_sprite(anim_sprites[self.frame].image)
                scaled_pos = gl.render_pos(self.get_position().x,
                                           self.get_position().y)
                gl.display.blit(scaled_image, scaled_pos)


class EnemyProjectile(Entity):
    """
    Projectile fired by enemies (cannons, platform/flying enemies).
    Matches cannon_miss from EB_ENEM.C:581-642
    """
    def __init__(self, sprites, position, velocity):
        Entity.__init__(self, sprites, position)
        self.velocity = velocity  # XY(x_speed, y_speed)
        self.frame = 0

    def update(self):
        # Move projectile
        self.position.x += self.velocity.x
        self.position.y += self.velocity.y

        # Animate
        if self.sprites:
            self.frame = (self.frame + 1) % len(self.sprites)

        # Activity-zone check: the projectile dies only when it has left the
        # viewport inflated by half a viewport (it may fly off-screen).
        world = gl.screen_manager
        if world is not None:
            activity = world.activity_rect()
            rect = self.world_rect()
            if (rect.right < activity.left or rect.left > activity.right or
                    rect.bottom < activity.top or rect.top > activity.bottom):
                self.vanish()
                return

        # Wall collision check - only stop on SOLID walls (EB_ENEM.C:581-642)
        # Original uses cave_test which checks tile solidity, not object overlap
        # Only collide with objects that have ALL collision sides (solid blocks)
        if self.check_solid_wall_collision():
            self.vanish()

    def check_solid_wall_collision(self, screen=None):
        """
        Check collision with solid walls only (not decorative sprites).
        Matches original cave_test behavior - only solid blocks stop projectiles.
        """
        world = gl.screen_manager
        if world is None:
            return False

        me = self.get_bbox().copy()
        me.move_ip(self.get_position())

        for obj in world.colliders_in_rect(me):
            if obj is self:
                continue
            sides = obj.get_sides()
            # Only stop on objects that block from the direction we're moving
            # AND are actual solid walls (have multiple collision sides)
            num_sides = sum([sides["L"], sides["R"], sides["T"], sides["B"]])
            if num_sides >= 2:  # Solid walls typically have 2+ collision sides
                if self.velocity.x > 0 and sides["L"]:
                    return True
                elif self.velocity.x < 0 and sides["R"]:
                    return True
                elif self.velocity.y > 0 and sides["T"]:
                    return True
                elif self.velocity.y < 0 and sides["B"]:
                    return True
        return False

    def get_bbox(self):
        """Return projectile's actual bounding box from sprite data"""
        if self.sprites and len(self.sprites) > 0:
            sprite = self.sprites[self.frame % len(self.sprites)]
            if sprite and hasattr(sprite, 'bbox'):
                return sprite.bbox
        # Fallback if no sprite
        return pygame.Rect(0, 0, gl.SPRITE_X, gl.SPRITE_Y)

    def get_sides(self):
        """Projectiles don't block movement"""
        return {"L": False, "R": False, "T": False, "B": False}

    def is_touchable(self):
        """Projectiles are not touchable (they kill via collision check)"""
        return False

    def get_touch(self):
        """Projectiles don't have touch type"""
        return 0

    def display(self):
        """Display projectile sprite at the render scale"""
        pos = self.get_position()
        scaled_pos = gl.render_pos(pos.x, pos.y)

        if self.sprites and len(self.sprites) > 0:
            sprite = self.sprites[self.frame % len(self.sprites)]
            if sprite and hasattr(sprite, 'image') and sprite.image:
                scaled_image = di.scale_sprite(sprite.image)
                gl.display.blit(scaled_image, scaled_pos)
                return

        # Draw placeholder circle when no valid sprites available
        # Red filled circle to make projectiles visible
        s = gl.RENDER_SCALE
        rect = pygame.Rect(scaled_pos[0] + int(round(16 * s)),
                           scaled_pos[1] + int(round(16 * s)),
                           int(round(32 * s)), int(round(32 * s)))
        pygame.draw.circle(gl.display, pygame.Color(255, 0, 0), rect.center,
                           int(round(12 * s)))
        pygame.draw.circle(gl.display, pygame.Color(255, 255, 0), rect.center,
                           int(round(8 * s)))

    def name(self):
        return "EnemyProjectile"


class Explosion(Entity):
    """
    Explosion animation entity.
    Plays explosion animation once then removes itself.
    Matches original explosion_proc from EB_ENEM.C:51-56
    """
    def __init__(self, sprites, position):
        Entity.__init__(self, sprites, position)
        self.frame = 0

    def update(self):
        """Cycle through explosion animation frames"""
        self.frame += 1
        if self.frame >= len(self.sprites):
            # Animation complete - remove explosion
            world = gl.screen_manager
            if world is not None:
                world.remove(self)

    def name(self):
        return "Explosion"


class BrokenSprite(Entity):
    """
    Static broken sprite entity.
    Shows the broken state of a destroyed object.
    """
    def __init__(self, sprites, position, frame_num):
        Entity.__init__(self, sprites, position)
        self.frame = frame_num if frame_num < len(sprites) else 0

    def update(self):
        """Static sprite - no update needed"""
        pass

    def display(self):
        """Display the broken sprite at the render scale"""
        if self.frame < len(self.sprites):
            scaled_image = di.scale_sprite(self.sprites[self.frame].image)
            scaled_pos = gl.render_pos(self.get_position().x,
                                       self.get_position().y)
            gl.display.blit(scaled_image, scaled_pos)

    def name(self):
        return "BrokenSprite"


class ExplosionWithBroke(Entity):
    """
    Explosion animation that leaves a broken sprite behind.
    Matches original explosion_with_broke_proc from EB_ENEM.I:3461-3483
    """
    def __init__(self, explosion_sprites, position, broken_entity):
        Entity.__init__(self, explosion_sprites, position)
        self.frame = 0
        self.broken_entity = broken_entity
        self.broken_sprite_spawned = False

    def update(self):
        """Cycle through explosion animation"""
        # Note: In the original C code, AUX_1++ at frame 2 advances to the next
        # shape_num (broken sprite). We now handle this in hit_object() by
        # getting the broken sprite directly from level data at sprite_index + len(sprites).
        self.frame += 1

        # When explosion completes, spawn the broken sprite entity (EB_ENEM.I:3472-3481)
        world = gl.screen_manager
        if self.frame >= len(self.sprites):
            if not self.broken_sprite_spawned and self.broken_entity:
                # Add the broken sprite to both the world and the level data
                if world is not None:
                    world.spawn(self.broken_entity)
                    logging.debug("ExplosionWithBroke: Added BrokenSprite at %s",
                                  self.broken_entity.position)
                self.broken_sprite_spawned = True
            # Remove the finished explosion (it was never part of the level data)
            if world is not None:
                world.remove(self)

    def name(self):
        return "ExplosionWithBroke"


# -----------------------------------------------------------------------------
# test code below

def main():
    pass

if __name__ == "__main__":
    main()
