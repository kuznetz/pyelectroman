"""Display module"""

import emglobals as gl
from emglobals import XY
import pygame
import logging
import time


# Logical (design) resolution used by all drawing code
LOGICAL_SIZE = (1280, 960)

#noinspection PyArgumentEqualDefault
def init_display():
    pygame.init()
    info = pygame.display.Info()
    desktop_size = (info.current_w, info.current_h)
    if desktop_size[0] <= 0 or desktop_size[1] <= 0:
        desktop_size = LOGICAL_SIZE
    try:
        screen = pygame.display.set_mode(desktop_size, pygame.FULLSCREEN)
    except pygame.error as e:
        # Fallback to a windowed mode if the display rejects fullscreen
        logging.warning("Fullscreen mode failed (%s), using windowed mode", e)
        desktop_size = LOGICAL_SIZE
        screen = pygame.display.set_mode(LOGICAL_SIZE)
    gl.display_surface = screen
    pygame.display.set_caption("Electro Man - Python Version")
    # Render coefficient: physical pixels per logical (1280x960) pixel.
    # Based on the actual surface size (it may differ from the desktop one).
    # Every draw call multiplies its coordinates/sprites/fonts by it.
    screen_w, screen_h = screen.get_size()
    gl.RENDER_SCALE = min(screen_w / LOGICAL_SIZE[0],
                          screen_h / LOGICAL_SIZE[1])
    # Render target: the design window multiplied by the coefficient,
    # centered on the fullscreen surface (proportions preserved).
    screen.fill((0, 0, 0))
    try:
        win_w = min(screen_w, max(1, int(round(LOGICAL_SIZE[0] * gl.RENDER_SCALE))))
        win_h = min(screen_h, max(1, int(round(LOGICAL_SIZE[1] * gl.RENDER_SCALE))))
        win_rect = pygame.Rect((screen_w - win_w) // 2,
                               (screen_h - win_h) // 2,
                               win_w, win_h)
        gl.window = screen.subsurface(win_rect)
    except (pygame.error, ValueError) as e:
        # Extremely defensive fallback: draw on the whole screen at 1:1
        logging.warning("Window subsurface failed (%s), using 1:1 screen", e)
        gl.RENDER_SCALE = 1.0
        gl.window = screen
    # System fonts are created at the physical size, so text stays crisp
    for name, size in (("xsmall", 16), ("small", 20),
                       ("normal", 24), ("large", 32)):
        gl.font[name] = pygame.font.SysFont(
            "tahoma", max(1, int(round(size * gl.RENDER_SCALE))))
    # Playfield subsurface: offsets and sizes multiplied by the coefficient
    s = gl.RENDER_SCALE
    subsrect = pygame.Rect(int(round(gl.OFFSET_X * 2 * s)),
                           int(round(gl.OFFSET_Y * 2 * s)),
                           int(round(gl.MAX_X * 2 * s)),
                           int(round(gl.MAX_Y * 2 * s)))
    gl.display = gl.window.subsurface(subsrect)


def quit_display():
    pygame.quit()


def clear_screen():
    gl.window.fill(pygame.Color(0, 0, 0))


def scale_sprite(image):
    """Scale a 1x game sprite to the physical render size."""
    return pygame.transform.scale(
        image, gl.render_size(image.get_width(), image.get_height()))


def present():
    """Present the already physically-scaled frame."""
    pygame.display.flip()


def show():
    info_lines.show()
    present()


def message(position, txt, font=None, antialias=True,
            color=pygame.Color(255, 255, 255)):
    """
    Display message on the screen. Uses entire surface.

    position - XY(x, y) in window (2x design) coordinates
    txt - string (can contain newlines)
    font - pygame.Font (already created at the physical size)
    antialias - True or False
    color - pygame.Color

    Return position of next line as XY(x, y).
    """
    font = gl.font["small"] if font is None else font
    scale = gl.RENDER_SCALE if gl.RENDER_SCALE else 1.0
    lines = txt.split('\n')
    cpos = XY.from_self(position)
    for line in lines:
        line_surface = font.render(line, antialias, color)
        gl.window.blit(line_surface, gl.window_pos(cpos.x, cpos.y))
        # advance stays in logical units (font height is physical)
        cpos.y += int(font.get_height() / scale * 1.05)
    return cpos


def debug_message(position, txt, font=None, antialias=True,
                  color=pygame.Color(255, 255, 255)):
    """
    Display a debug message on the screen.

    Does nothing unless the game was started with the --debug flag.

    Return position of next line as XY(x, y).
    """
    if not gl.debug_mode:
        return XY.from_self(position)
    return message(position, txt, font, antialias, color)

class InfoLines:
    """
    Several information lines.
    Autoscrolling up.
    Limited visibility time.
    Shown only in debug mode (--debug).
    """
    def __init__(self, position, max_lines, max_time):
        self.lines = []
        self.max_time = max_time
        self.max_lines = max_lines
        self.position = position
        self.font = gl.font["xsmall"]
        self.update = 0

    def add(self, text):
        if not gl.debug_mode:
            return
        if len(self.lines) == self.max_lines:
            self.lines.pop(0)
        self.lines.append(text)
        self.update = time.perf_counter()

    def show(self):
        if not gl.debug_mode:
            self.lines.clear()
            return
        pos = self.position.copy()
        for line in self.lines:
            pos = message(pos, line)
        if (time.perf_counter() - self.update > self.max_time) and self.lines:
            self.lines.pop(0)
            self.update = time.perf_counter()

info_lines = InfoLines(XY(180 * 2, 8), 3, 5) #default info lines buffer (scaled 2x)

class DiskInfo:
    def __init__(self, position):
        sprite = gl.info.get_sprite(3) # disk segments
        self.disk = sprite.image.subsurface(pygame.Rect(0, 0, 18, 16))
        self.position = position
        self.disks = 0

    def set_value(self, disks):
        self.disks = min(disks, 3)  # cap at 3 disks max

    def display(self):
        # Blink when 3 disks collected (EB.C:784)
        # if ((disk_num < 3) || (main_cntr & 0x04))
        if self.disks and (self.disks < 3 or (gl.counter & 0x04)):
            position = XY.from_self(self.position)
            scaled_disk = scale_sprite(self.disk)
            for d in range(self.disks):
                gl.display.blit(scaled_disk,
                                gl.render_pos(position.x, position.y))
                position.x += 22

class LEDBar:
    """
    LED bar display
    """
    def __init__(self, position, mapping):
        self.value = 0
        sprite = gl.info.get_sprite(4) # LED indication segments
        self.leds = [sprite.image.subsurface(pygame.Rect(0, 0, 16, 16)),
                     sprite.image.subsurface(pygame.Rect(16, 0, 16, 16)),
                     sprite.image.subsurface(pygame.Rect(32, 0, 16, 16)),
                     sprite.image.subsurface(pygame.Rect(0, 16, 16, 16)),
                     sprite.image.subsurface(pygame.Rect(16, 16, 16, 16))]
        self.position = position
        self.mapping = mapping

    def set_value(self, value):
        self.value = value % 7

    def display(self):
        #self.value = int(time.perf_counter()) % 7
        position = XY.from_self(self.position)
        for led in range(6):
            scaled_led = scale_sprite(self.leds[self.mapping[self.value][led]])
            gl.display.blit(scaled_led,
                            gl.render_pos(position.x, position.y))
            position.x += 16
        scaled_led = scale_sprite(self.leds[4])
        gl.display.blit(scaled_led, gl.render_pos(position.x, position.y))

class Indicators:
    def __init__(self):
        self.left = LEDBar(XY(16, 352),
                           [[2, 3, 3, 3, 3, 3],
                            [0, 3, 3, 3, 3, 3],
                            [0, 0, 3, 3, 3, 3],
                            [0, 0, 1, 3, 3, 3],
                            [0, 0, 1, 2, 3, 3],
                            [0, 0, 1, 2, 2, 3],
                            [0, 0, 1, 2, 2, 2]])
        self.right = LEDBar(XY(512, 352),
                           [[2, 3, 3, 3, 3, 3],
                            [2, 1, 3, 3, 3, 3],
                            [2, 1, 0, 3, 3, 3],
                            [2, 1, 0, 0, 3, 3],
                            [2, 1, 0, 0, 0, 3],
                            [2, 1, 0, 0, 0, 0],
                            [2, 1, 0, 0, 0, 0]]
        )
        self.disks = DiskInfo(XY(144, 352))

    def display(self):
        self.left.display()
        self.right.display()
        self.disks.display()

class StatusLine:
    """
    Handle status line display.
    Singleton by design.
    """
    def __init__(self):
        self.message = ""
        self.font = gl.font["xsmall"]
        self.position = XY(8 * 2, 465 * 2)  # Scale 2x for larger window

    def add(self, text):
        self.message += text

    def show(self):
        """Display the status line (debug mode only)."""
        if not gl.debug_mode:
            self.message = ""
            return
        message(self.position, self.message, self.font)
        self.message = ""

status_line = StatusLine()
indicators = None

# -----------------------------------------------------------------------------
# test code below


def main():
    logging.basicConfig(level=logging.DEBUG,
                        format='%(levelname)s: %(funcName)s(): %(message)s')
    init_display()
    loop = True
    while loop:
        clear_screen()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                loop = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    loop = False
        nextp = message(XY(0, 0), "message1\nmessage2")
        message(nextp, "message3\nmessage4")
        show()
    quit_display()


if __name__ == "__main__":
    main()
