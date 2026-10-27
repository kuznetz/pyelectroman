"""
Global variables module
"""

import copy

import pygame

# pylint: disable-msg=C0103

# PyGame related globals

font = {"xsmall": None,
        "small": None,
        "normal": None,
        "large": None}

small_font = None
medium_font = None
large_font = None
display = None  # whole window (screen) surface
window = None  # gameplay window subsurface
display_surface = None  # physical fullscreen surface (window is scaled onto it)

# display related globals
SPRITE_X = 48  # size in pixels
SPRITE_Y = 48  # size in pixels
SCREEN_X = 13  # size in sprites
SCREEN_Y = 8   # size in sprites
MAX_X = SPRITE_X * SCREEN_X  # screen size in pixels
MAX_Y = SPRITE_Y * SCREEN_Y  # screen size in pixels

OFFSET_X = 8  # to center 13x8 sprites screen in 640x480 window
OFFSET_Y = 48  # to center 13x8 sprites screen in 640x480 window

DISPLAY_OFFSET = (OFFSET_X, OFFSET_Y)

# Physical render coefficient: physical pixels per logical (1280x960) pixel.
# Set by emdisplay.init_display() and applied to the whole render.
RENDER_SCALE = 1.0

# World grid: 16x16 rooms, room index = gy * 16 + gx
ROOMS_X = 16
ROOMS_Y = 16
ROOMS_TOTAL = ROOMS_X * ROOMS_Y


class Camera:
    """
    Scrolling camera.

    x, y - world coordinates of the viewport's top-left corner (game px).
    ``enabled`` switches the camera *mode*: True - the viewport follows the
    hero continuously (seamless scrolling); False - the viewport is pinned
    to the hero's room, which gives the old page-based picture.
    """
    def __init__(self):
        self.x = 0
        self.y = 0
        self.enabled = True

    def viewport(self):
        """Return current viewport as a world rect."""
        return pygame.Rect(self.x, self.y, MAX_X, MAX_Y)

    def activity_rect(self):
        """
        Return the activity rect: viewport inflated by half a viewport
        in every direction (2x2 viewports in total).
        """
        return self.viewport().inflate(MAX_X, MAX_Y)


camera = None  # set to Camera() by the gameplay module


def render_pos(x, y):
    """
    Convert world game (1x) coordinates to physical render pixels.

    There is exactly ONE rounding per coordinate: only the offset from the
    camera is scaled, never the absolute world position (CAMERA_PLAN.md 4.2).
    """
    s = 2.0 * RENDER_SCALE
    cam = camera
    if cam is not None:
        return (int(round((x - cam.x) * s)),
                int(round((y - cam.y) * s)))
    return (int(round(x * s)), int(round(y * s)))


def view_pos(x, y):
    """Convert viewport (1x playfield) coordinates to physical render pixels.

    Used by the HUD, which is always bound to the frame and never scrolls.
    """
    s = 2.0 * RENDER_SCALE
    return (int(round(x * s)), int(round(y * s)))


def window_pos(x, y):
    """Convert window (2x design) coordinates to physical render pixels."""
    return (int(round(x * RENDER_SCALE)), int(round(y * RENDER_SCALE)))


def render_size(width, height):
    """Convert 1x sprite dimensions to physical render dimensions."""
    s = 2.0 * RENDER_SCALE
    return (max(1, int(round(width * s))), max(1, int(round(height * s))))


show_collisions = False

# data related globals
data_folder = r"data"  # defaul data folder
level_names = ["elek", "koryt", "mieszk", "magaz",
               "fiolet", "10x10", "sluzy", "widok", "test"]
current_level = 0  # current level number
level = None  # currently loaded level

# gameplay related globals

screen_manager = None  # screen manager

loop_main_loop = True  # loop the main gameplay loop
player = None  # player's character entity
checkpoint = None  # active checkpoint
checkpoint_entity = None  # Checkpoint sprite of the current respawn point
disabled_checkpoints = set()  # (level, world_x, world_y) retired checkpoints
enemies = None  # data class for enemies
weapons = None  # data class for weapons
info = None  # data class for info sprites
sound_manager = None  # sound effects manager
counter = 0 # +1 every loop
disks = 0 # number of disks collected
disk_positions = [] # world positions of collected disks (EB.C:1391-1395)
exit_level_flag = False # set when player exits level
next_level_code = 0 # next level to load (from exit sprite param)
killing_floor = False # set when KillingFloor entity activates
game_completed = False # set when all 8 levels completed
casual = False # game mode: True = casual (easy), False = hardcore

# random numbers for active screen
screen_randoms = []
for r in range(SCREEN_X):
    screen_randoms.append(0)

# system related globals

debug_mode = False  # True when the game is started with the --debug flag
log_filename = "em.log"  # empty string disables logging to file
render_time = 0  # rendering time
logic_time = 0   # logic processing time

# global classes

class XY:
    """Class to keep x, y positions."""
    def __init__(self, x: object = 0, y: object = 0) -> None:
        if not isinstance(x, int):
            raise ValueError("x must be an int.")
        self.x = x
        if not isinstance(y, int):
            raise ValueError("y must be an int.")
        self.y = y

    def __getitem__(self, index):
        """Return x as [0] and y as [1]."""
        if index == 0:
            return self.x
        elif index == 1:
            return self.y
        else:
            raise IndexError("Index out of range!")

    def __setitem__(self, index, value):
        """Set x from [0] and y from [1]."""
        if index == 0:
            self.x = value
        elif index == 1:
            self.y = value
        else:
            raise IndexError("Index out of range!")

    def __len__(self):
        """Always return 2 as length."""
        return 2

    def __add__(self, other):
        """Add another XY() or (x, y) tuple."""
        if isinstance(other, tuple) and len(other) == 2:
            other = XY.from_tuple(other)
        if not isinstance(other, XY):
            raise NotImplementedError(
                "Only XY() or (x, y) addition implemented.")
        x = self.x + other.x
        y = self.y + other.y
        return XY(x, y)

    def __sub__(self, other):
        """Subtract another XY() or (x, y) tuple."""
        if isinstance(other, tuple) and len(other) == 2:
            other = XY.from_tuple(other)
        if not isinstance(other, XY):
            raise NotImplementedError(
                "Only XY() or (x, y) addition implemented.")
        x = self.x - other.x
        y = self.y - other.y
        return XY(x, y)

    def __eq__(self, other):
        """Compare two XY objects for equality."""
        if not isinstance(other, XY):
            return False
        return self.x == other.x and self.y == other.y

    def __ne__(self, other):
        """Compare two XY objects for inequality."""
        return not self.__eq__(other)

    def __str__(self):
        """Return human-readable representation."""
        return "XY(%d, %d)" % (self.x, self.y)

    def _repr__(self):
        return "<XY(%d, %d)>" % (self.x, self.y)

    def copy(self):
        """Return copy of self."""
        return copy.copy(self)

    @classmethod
    def from_tuple(cls, tup):
        """Initialize XY object from (x, y) tuple."""
        obj = cls()
        if len(tup) == 2:
            obj.x = tup[0]
            obj.y = tup[1]
        return obj

    @classmethod
    def from_self(cls, xy):
        """Initialize XY object from other XY object."""
        if not isinstance(xy, XY):
            raise ValueError("XY() object required.")
        obj = xy.copy()
        return obj


def room_of(x, y):
    """Return the room (screen) number of a world position."""
    return (int(y) // MAX_Y) * ROOMS_X + (int(x) // MAX_X)


def room_origin(room):
    """Return the world position (top-left corner) of a room."""
    return XY((room % ROOMS_X) * MAX_X, (room // ROOMS_X) * MAX_Y)


def local_tile(x, y):
    """Return the local (inside-room) tile coordinates of a world position."""
    return ((int(x) % MAX_X) // SPRITE_X, (int(y) % MAX_Y) // SPRITE_Y)


# other global functions

def init_screen_randoms(screen_number):
    srand(256 * screen_number + screen_number)
    random(256)  # additional call for compatibility reasons
    for i in range(SCREEN_X):
        screen_randoms[i] = random(256)
    srand(256 * screen_number + screen_number)

# Borland C 3.1 rand()

MULTIPLIER = 0x015a4e35
INCREMENT = 1
rand_seed = 1


def srand(seed):
    global rand_seed
    rand_seed = seed


def rand():
    """
    int rand(void)
    {
        Seed = MULTIPLIER * Seed + INCREMENT;
        return((int)(Seed >> 16) & 0x7fff);
    }
    """
    global rand_seed
    rand_seed = (MULTIPLIER * rand_seed + INCREMENT)
    return (rand_seed >> 16) & 0x7FFF


def random(num):
    """ #define random(num)(int)(((long)rand()*(num))/(RAND_MAX+1)) """
    return int((rand() * num) / 0x8000)

# -----------------------------------------------------------------------------
# test code below


def main():
    srand(0)
    for i in range(16):
        print(rand())
    init_screen_randoms(0)
    print(screen_randoms)
    init_screen_randoms(1)
    print(screen_randoms)
    init_screen_randoms(2)
    print(screen_randoms)
    init_screen_randoms(18)
    print(screen_randoms)
    init_screen_randoms(34)
    print(screen_randoms)

if __name__ == "__main__":
    main()
