"""Xbox-compatible gamepad support shared by gameplay and menus.

Only pygame's joystick API is used, all connected pads are treated as a
single virtual controller. The module keeps one process-wide manager
(:func:`get_gamepad`) so that gameplay and menus see the same devices and
hot-plugging.
"""

import logging
import pygame


# SDL axis/button indices of an Xbox-compatible pad
PAD_DEADZONE = 0.5
PAD_AXIS_LEFT_X = 0
PAD_AXIS_LEFT_Y = 1
PAD_BUTTON_A = 0
PAD_BUTTON_B = 1
PAD_BUTTON_X = 2
PAD_BUTTON_BACK = 6
PAD_BUTTON_START = 7


class PadState:
    """Combined state of all connected pads."""

    __slots__ = ("left", "right", "up", "down",
                 "a", "b", "x", "start", "back")

    def __init__(self):
        self.left = False
        self.right = False
        self.up = False
        self.down = False
        self.a = False
        self.b = False
        self.x = False
        self.start = False
        self.back = False

    def clear(self):
        """Release all buttons and center the stick."""
        self.left = False
        self.right = False
        self.up = False
        self.down = False
        self.a = False
        self.b = False
        self.x = False
        self.start = False
        self.back = False

    def copy(self):
        """Return an independent copy of the state."""
        state = PadState()
        state.left = self.left
        state.right = self.right
        state.up = self.up
        state.down = self.down
        state.a = self.a
        state.b = self.b
        state.x = self.x
        state.start = self.start
        state.back = self.back
        return state


class Gamepad:
    """Manages all connected gamepads."""

    def __init__(self):
        # instance_id -> pygame.joystick.Joystick
        self.joysticks = {}
        self.state = PadState()
        self.scan()

    def scan(self):
        """Detect (or re-detect) all connected gamepads."""
        if not pygame.joystick.get_init():
            pygame.joystick.init()
        self.joysticks = {}
        for index in range(pygame.joystick.get_count()):
            try:
                joystick = pygame.joystick.Joystick(index)
                joystick.init()
            except pygame.error as err:
                logging.warning("Cannot initialize gamepad %d: %s", index, err)
                continue
            self.joysticks[joystick.get_instance_id()] = joystick
            logging.info("Gamepad connected: %s", joystick.get_name())

    def handle_event(self, event):
        """Track gamepad hot-plugging."""
        if event.type in (pygame.JOYDEVICEADDED,
                          pygame.JOYDEVICEREMOVED):
            self.scan()

    def poll(self):
        """Read all pads and return a fresh :class:`PadState`."""
        state = PadState()
        self.state = state
        if not pygame.joystick.get_init():
            return state
        # a pad may have been (un)plugged while some loop swallowed the
        # JOYDEVICEADDED/JOYDEVICEREMOVED events - rescan if needed
        if pygame.joystick.get_count() != len(self.joysticks):
            self.scan()
        for joystick in list(self.joysticks.values()):
            try:
                self._read(joystick, state)
            except pygame.error:
                logging.warning("Gamepad lost: %s", joystick.get_name())
                self.scan()
                break
        return state

    @staticmethod
    def _read(joystick, state):
        """Merge a single device state into *state*."""
        num_axes = joystick.get_numaxes()
        if num_axes > PAD_AXIS_LEFT_X:
            axis_x = joystick.get_axis(PAD_AXIS_LEFT_X)
            if axis_x <= -PAD_DEADZONE:
                state.left = True
            elif axis_x >= PAD_DEADZONE:
                state.right = True
        if num_axes > PAD_AXIS_LEFT_Y:
            # SDL: stick down is +1, stick up is -1
            axis_y = joystick.get_axis(PAD_AXIS_LEFT_Y)
            if axis_y <= -PAD_DEADZONE:
                state.up = True
            elif axis_y >= PAD_DEADZONE:
                state.down = True
        if joystick.get_numhats() > 0:
            hat_x, hat_y = joystick.get_hat(0)
            if hat_x < 0:
                state.left = True
            elif hat_x > 0:
                state.right = True
            # SDL: hat down is -1, hat up is +1
            if hat_y < 0:
                state.down = True
            elif hat_y > 0:
                state.up = True
        num_buttons = joystick.get_numbuttons()
        if num_buttons > PAD_BUTTON_A:
            state.a = joystick.get_button(PAD_BUTTON_A)
        if num_buttons > PAD_BUTTON_B:
            state.b = joystick.get_button(PAD_BUTTON_B)
        if num_buttons > PAD_BUTTON_X:
            state.x = joystick.get_button(PAD_BUTTON_X)
        if num_buttons > PAD_BUTTON_BACK:
            state.back = joystick.get_button(PAD_BUTTON_BACK)
        if num_buttons > PAD_BUTTON_START:
            state.start = joystick.get_button(PAD_BUTTON_START)


class MenuPad:
    """
    Edge-triggered gamepad input for menu screens (poll once per frame).

    Directions are triggered on a fresh press and then auto-repeat, while
    buttons only fire on the press edge - so menus never scroll or toggle
    endlessly because a button or the stick is still held down.
    """

    REPEAT_DELAY = 12  # frames (20 FPS) before a held direction repeats
    REPEAT_RATE = 4    # frames between repeats

    DIRECTIONS = ("up", "down", "left", "right")

    def __init__(self, gamepad=None):
        self.gamepad = gamepad or get_gamepad()
        # treat whatever is pressed right now as already handled
        self.prev = self.gamepad.state.copy()
        self.dir_frames = {direction: 0 for direction in self.DIRECTIONS}

    def reset(self):
        """Forget the current state, e.g. after returning to the menu."""
        self.prev = self.gamepad.state.copy()
        for direction in self.DIRECTIONS:
            self.dir_frames[direction] = 0

    def poll(self):
        """
        Return menu actions for this frame as a dict of booleans:
        "up", "down", "left", "right", "confirm", "back", "fire".
        """
        state = self.gamepad.poll()
        actions = {direction: False for direction in self.DIRECTIONS}
        actions["confirm"] = False
        actions["back"] = False
        actions["fire"] = False
        for direction in self.DIRECTIONS:
            if not getattr(state, direction):
                self.dir_frames[direction] = 0
                continue
            frames = self.dir_frames[direction]
            if (frames == 0 or
                    (frames >= self.REPEAT_DELAY and
                     (frames - self.REPEAT_DELAY) % self.REPEAT_RATE == 0)):
                actions[direction] = True
            self.dir_frames[direction] = frames + 1
        actions["confirm"] = ((state.a and not self.prev.a) or
                              (state.start and not self.prev.start))
        actions["back"] = state.b and not self.prev.b
        actions["fire"] = state.x and not self.prev.x
        self.prev = state.copy()
        return actions


_gamepad = None


def get_gamepad():
    """Return the process-wide gamepad manager."""
    global _gamepad
    if _gamepad is None:
        _gamepad = Gamepad()
    return _gamepad
