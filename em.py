"""Main game module"""

import emglobals as gl
from emglobals import XY
import emdata as da
import emgame as ga
import emdisplay as di
import emhero as pl
import emother as ot
import emmenu as mn
import emsound as snd
import pygame
import logging
import time


class Gameplay:
    """
    Main gameplay functionality class.
    Singleton by design.
    """
    # Entity classes removed once they leave the activity zone
    CLEANUP_TYPES = ()

    def __init__(self):
        gl.data_folder = "data"
        gl.level = da.Level()
        self.controller = ga.Controller()
        # initialize a few global objects
        # thus loading associated sprite sets
        gl.camera = gl.Camera()
        gl.screen_manager = ga.World()
        gl.player = pl.PlayerEntity(self.controller)
        self.CLEANUP_TYPES = (ga.EnemyProjectile, pl.Projectile,
                              ga.Explosion, ga.ExplosionWithBroke)
        gl.enemies = ot.Enemies()
        gl.weapons = ot.Weapons()
        gl.info = ot.Info()
        di.indicators = di.Indicators()
        gl.checkpoint = ga.ActiveCheckpoint()
        gl.checkpoint_entity = None
        gl.disabled_checkpoints.clear()
        gl.sound_manager = snd.SoundManager()
        # initialize rest
        self.loop = True
        self.screens_map = None
        self.key_handlers = {pygame.K_ESCAPE: self.on_k_escape,
                             pygame.K_TAB: self.on_k_tab,
                             pygame.K_LEFT: self.on_k_left,
                             pygame.K_RIGHT: self.on_k_right,
                             pygame.K_UP: self.on_k_up,
                             pygame.K_DOWN: self.on_k_down,
                             pygame.K_1: self.on_k_1,
                             pygame.K_2: self.on_k_2,
                             pygame.K_3: self.on_k_3,
                             pygame.K_4: self.on_k_4,
                             pygame.K_5: self.on_k_5,
                             pygame.K_6: self.on_k_6,
                             pygame.K_7: self.on_k_7,
                             pygame.K_8: self.on_k_8,
                             pygame.K_9: self.on_k_9,
                             pygame.K_0: self.on_k_0,
                             pygame.K_d: self.on_k_d,
                             pygame.K_f: self.on_k_f,
                             pygame.K_r: self.on_k_r,
                             pygame.K_F5: self.on_k_f5,
                             pygame.K_F7: self.on_k_f7,
                             pygame.K_F8: self.on_k_f8,
                             pygame.K_F9: self.on_k_f9}
        # Debug shortcuts: handled only when the game runs with --debug
        self.debug_keys = frozenset({
            pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN,
            pygame.K_TAB, pygame.K_F8,
            pygame.K_0, pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4,
            pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9,
            pygame.K_d, pygame.K_f})
        self.deferred = None
        self.quit_ask = False
        self.restart_ask = False

    @property
    def init_map(self):
        """Initialize level map"""
        # pylint: disable-msg=E1121
        screens_map = pygame.Surface((32, 32))
        pixels = pygame.PixelArray(screens_map)
        # pylint: enable-msg=E1121
        FULL = 0x33AA33
        EMPTY = 0x333333
        screens = gl.screen_manager.get_screens()
        for scr in range(256):
            if screens[scr]:
                pixels[(scr % 16) * 2 + 0][(scr // 16) * 2 + 0] = FULL
                pixels[(scr % 16) * 2 + 1][(scr // 16) * 2 + 0] = FULL
                pixels[(scr % 16) * 2 + 0][(scr // 16) * 2 + 1] = FULL
                pixels[(scr % 16) * 2 + 1][(scr // 16) * 2 + 1] = FULL
            else:
                pixels[(scr % 16) * 2 + 0][(scr // 16) * 2 + 0] = EMPTY
                pixels[(scr % 16) * 2 + 1][(scr // 16) * 2 + 0] = EMPTY
                pixels[(scr % 16) * 2 + 0][(scr // 16) * 2 + 1] = EMPTY
                pixels[(scr % 16) * 2 + 1][(scr // 16) * 2 + 1] = EMPTY
        del pixels
        return screens_map

    def show_map(self, pos):
        """Display level map (for debug only)"""
        player_pos = gl.player.get_position() if gl.player else XY(0, 0)
        scr = gl.room_of(player_pos.x, player_pos.y)
        CURRENT = 0xFFFFFF
        # pylint: disable-msg=E1121
        screens_map_copy = pygame.Surface((32, 32))
        screens_map_copy.blit(self.screens_map, (0, 0))
        pixels = pygame.PixelArray(screens_map_copy)
        # pylint: enable-msg=E1121
        pixels[(scr % 16) * 2 + 0][(scr // 16) * 2 + 0] = CURRENT
        pixels[(scr % 16) * 2 + 1][(scr // 16) * 2 + 0] = CURRENT
        pixels[(scr % 16) * 2 + 0][(scr // 16) * 2 + 1] = CURRENT
        pixels[(scr % 16) * 2 + 1][(scr // 16) * 2 + 1] = CURRENT
        del pixels
        # Scale map by the render coefficient
        map_size = max(1, int(round(64 * gl.RENDER_SCALE)))
        scaled_map = pygame.transform.scale(screens_map_copy,
                                            (map_size, map_size))
        gl.window.blit(scaled_map, gl.window_pos(pos[0], pos[1]))

    def show_info(self):
        """Display status line"""
        di.status_line.show()

    def display_screen(self, screen=None):
        """
        Display the visible part of the seamless world.

        ``screen`` is accepted for compatibility and ignored: rooms are
        picked from the camera viewport instead.
        """
        world = gl.screen_manager
        world.update_active()  # make sure newly created objects get displayed
        if gl.camera is not None:
            view = gl.camera.viewport()
        else:
            view = pygame.Rect(0, 0, gl.MAX_X, gl.MAX_Y)
        # Two tiles of margin so objects on a seam never "pop"
        margin = gl.SPRITE_X * 2
        drawn = view.inflate(margin * 2, margin * 2)
        rooms = world.visible_rooms(drawn)
        for room in rooms:
            for entity in room.background:
                entity.display()
        for room in rooms:
            for entity in room.collisions:
                entity.display()
                if gl.show_collisions:
                    entity.display_collisions()
        self.deferred = []
        for entity in world.entities_in_rect(drawn):
            deferred = entity.display()
            if deferred:
                self.deferred.append(deferred)

    def display_deferred(self):
        for deferred in self.deferred:
            deferred()

    def display_hero(self):
        """Display player's character"""
        gl.player.display()

    def display_indicators(self):
        """Display weapon indicators (and other icons)"""
        di.indicators.display()

    def move_player(self, offset):
        position = gl.player.get_position() + offset
        gl.player.set_position(position)

    def teleport_to_room_offset(self, offset):
        """Debug: teleport the hero into a neighbouring room."""
        world = gl.screen_manager
        pos = gl.player.get_position()
        room = (gl.room_of(pos.x, pos.y) + offset) % gl.ROOMS_TOTAL
        if not world.screens or not world.screens[room]:
            di.info_lines.add("No room %d" % room)
            return
        target = gl.room_origin(room) + XY(gl.MAX_X // 2,
                                           gl.MAX_Y - gl.SPRITE_Y * 2)
        gl.player.stand(target)
        gl.player.to_ground = gl.player.check_ground()
        gl.player.switch_state(gl.player.state_stand)
        world.snap_camera()
        di.info_lines.add("Room %d" % room)

    def on_k_left(self):
        if pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.teleport_to_room_offset(-1)
        elif pygame.key.get_mods() & pygame.KMOD_SHIFT:
            self.move_player((-gl.SPRITE_X, 0))

    def on_k_right(self):
        if pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.teleport_to_room_offset(1)
        elif pygame.key.get_mods() & pygame.KMOD_SHIFT:
            self.move_player((gl.SPRITE_X, 0))

    def on_k_up(self):
        if pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.teleport_to_room_offset(-gl.ROOMS_X)
        elif pygame.key.get_mods() & pygame.KMOD_SHIFT:
            self.move_player((0, -gl.SPRITE_Y))

    def on_k_down(self):
        if pygame.key.get_mods() & pygame.KMOD_CTRL:
            self.teleport_to_room_offset(gl.ROOMS_X)
        elif pygame.key.get_mods() & pygame.KMOD_SHIFT:
            self.move_player((0, gl.SPRITE_Y))

    def on_k_tab(self):
        gl.show_collisions = False if gl.show_collisions else True

    def on_k_f8(self):
        """Toggle the scrolling camera (debug: off = page-like picture)."""
        if gl.camera is not None:
            gl.camera.enabled = not gl.camera.enabled
            di.info_lines.add("Camera: %s" % ("ON" if gl.camera.enabled
                                             else "OFF"))

    def on_k_1(self):
        di.info_lines.add("level 1")
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            gl.player.select_weapon(1)
        else:
            gl.current_level = 0
            self.load_level()

    def on_k_2(self):
        di.info_lines.add("level 2")
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            gl.player.select_weapon(2)
        else:
            gl.current_level = 1
            self.load_level()

    def on_k_3(self):
        di.info_lines.add("level 3")
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            gl.player.select_weapon(3)
        else:
            gl.current_level = 2
            self.load_level()

    def on_k_4(self):
        di.info_lines.add("level 4")
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            gl.player.select_weapon(4)
        else:
            gl.current_level = 3
            self.load_level()

    def on_k_5(self):
        di.info_lines.add("level 5")
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            gl.player.select_weapon(5)
        else:
            gl.current_level = 4
            self.load_level()

    def on_k_6(self):
        di.info_lines.add("level 6")
        gl.current_level = 5
        self.load_level()

    def on_k_7(self):
        di.info_lines.add("level 7")
        gl.current_level = 6
        self.load_level()

    def on_k_8(self):
        di.info_lines.add("level 8")
        gl.current_level = 7
        self.load_level()

    def on_k_9(self):
        """Debug: Jump to test level"""
        di.info_lines.add("Test level")
        gl.current_level = 8  # test level index
        self.load_level()

    def on_k_0(self):
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            gl.player.select_weapon(0)

    def on_k_escape(self):
        # Ask for confirmation before quitting the level (EB.C:1117-1129).
        # Deferred to the end of the frame so the prompt is drawn over a
        # fully rendered game screen.
        self.quit_ask = True

    def on_k_r(self):
        # Ask for confirmation before restarting the level (KEY_RESTART =
        # R or Alt+F3, EB.H:68; EB.C:1103-1115). Deferred like quit_ask.
        self.restart_ask = True

    def on_k_d(self):
        """Debug: trigger player death (Shift+D)"""
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            gl.player.new_state(gl.player.state_death)
            di.info_lines.add("Debug: Death triggered")

    def on_k_f(self):
        """Debug: give all 3 disks (Shift+F)"""
        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
            gl.disks = 3
            di.info_lines.add("Debug: 3 disks added")

    def quick_save(self):
        """
        Quick save the current game state to quick.sav.

        Returns True on success. Used by F5 and by the "save game (y or n)"
        prompt shown when leaving a level (Esc / gamepad START).
        """
        import emquicksave as qs
        if qs.save_quick():
            di.info_lines.add("Quick save: %s" % qs.QUICK_SAVE_FILE)
            return True
        di.info_lines.add("Quick save failed")
        return False

    def on_k_f5(self):
        """Quick save the current game state to quick.sav (F5)."""
        self.quick_save()

    def on_k_f7(self):
        """Toggle sound effects on/off (F7 - matches original game)"""
        if gl.sound_manager:
            enabled = gl.sound_manager.toggle()
            di.info_lines.add("Sound: %s" % ("ON" if enabled else "OFF"))

    def on_k_f9(self):
        """Quick load the game state from quick.sav (F9)."""
        import emquicksave as qs
        if qs.load_quick():
            self.screens_map = self.init_map
            if gl.screen_manager is not None:
                gl.screen_manager.snap_camera()
            di.info_lines.add("Quick load: %s" % qs.QUICK_SAVE_FILE)
        else:
            di.info_lines.add("Quick load failed")

    def load_level(self):
        # Fresh level/attempt: no checkpoint of this level has been retired
        gl.disabled_checkpoints.clear()
        gl.checkpoint_entity = None
        # Loading the level lets it adopt its own entrance checkpoint (the
        # sprite with param = 1, EB.C level data) when the active checkpoint
        # belongs to another level - see Level.process() in emdata.py.
        gl.level.load(gl.level_names[gl.current_level])
        gl.screen_manager.load_level(gl.level)
        self.screens_map = self.init_map
        start_position = gl.checkpoint.get_position()
        gl.disks = 0 # no disks collected after level load (EB.C:1461)
        gl.disk_positions = [] # clear collected disk positions (EB.C:1462-1464)
        gl.killing_floor = False # reset killing floor flag on level load
        # Reset weapon power on level load (EB.C:1389)
        gl.player.power = 0
        gl.player.ammo = 0
        gl.player.temp = 0
        if start_position:
            start_position += XY(gl.SPRITE_X // 2, gl.SPRITE_Y)
            gl.player.stand(start_position)
            # Snap the camera: level entry never scrolls in
            gl.screen_manager.snap_camera()
            # Enter the level exactly like respawn() after death: a clean
            # standing state with the distance to the ground recalculated
            gl.player.death_timer = 0
            gl.player.invuln_timer = 0
            gl.player.touched = []
            gl.player.to_ground = gl.player.check_ground()
            gl.player.switch_state(gl.player.state_stand)
            # Level-entry sample (hero_enter_level_proc EB_HERO.C:681)
            import emsound as snd
            snd.play_sound('area')

    def restart_level(self):
        """
        Restart the current level from scratch.
        Matches EB.C:1087 (next_level_num = level_num; game_break =
        restart_level), which loops back into electro_body -> new_level():
        a full fresh reload - start position, disks, weapon all reset.
        """
        # level number -1 forces the level entrance to become the checkpoint
        gl.checkpoint.update(-1, None)
        mn.show_loading_animation()
        self.load_level()
        # The player may be mid-jump or mid-death when restarting;
        # return to a clean standing state (same pattern as respawn()).
        gl.player.death_timer = 0
        gl.player.touched = []
        gl.player.to_ground = gl.player.check_ground()
        gl.player.switch_state(gl.player.state_stand)
        gl.screen_manager.snap_camera()
        di.info_lines.add("Level restarted")

    def loop_begin(self):
        di.clear_screen()

    def loop_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                gl.loop_main_loop = False
            elif event.type == pygame.KEYDOWN:
                # Handle Alt-X to exit (matches original game)
                if event.key == pygame.K_x and pygame.key.get_mods() & pygame.KMOD_ALT:
                    gl.loop_main_loop = False
                # Handle key press events (single trigger, not continuous)
                elif event.key in self.key_handlers:
                    # Debug shortcuts (level jumps, screen navigation,
                    # teleports, weapon selection, collision display,
                    # death/disks cheats) work only with --debug
                    if event.key in self.debug_keys and not gl.debug_mode:
                        continue
                    self.key_handlers[event.key]()
            elif event.type in (pygame.JOYDEVICEADDED,
                                pygame.JOYDEVICEREMOVED):
                # track gamepad hot-plugging
                self.controller.handle_event(event)
        self.controller.update()
        if self.controller.exit:
            # gamepad START quits the level, same as Esc (with confirmation)
            self.on_k_escape()

    def cleanup_inactive(self, activity):
        """
        Remove projectiles and effects that left the activity zone.

        They are not updated anymore (they are outside the activity rect),
        so without this sweep they would hang in the world forever.
        """
        world = gl.screen_manager
        search = activity.inflate(gl.MAX_X, gl.MAX_Y)
        for entity in world.entities_in_rect(search):
            if not isinstance(entity, self.CLEANUP_TYPES):
                continue
            if not entity.world_rect().colliderect(activity):
                logging.debug("cleanup: %s left the activity zone",
                              entity.name())
                world.remove(entity)

    def loop_run(self):
        world = gl.screen_manager
        # objects spawned last frame become live now
        world.update_active()
        activity = world.activity_rect()
        # Only entities inside the activity zone are updated
        for entity in world.entities_in_rect(activity):
            entity.update()
        # the hero is always updated
        gl.player.update()
        # pick up objects spawned during this frame's updates
        world.update_active()
        self.cleanup_inactive(activity)
        # the camera follows the hero (and updates the current room)
        world.update_camera()

    def loop_end(self):
        self.display_screen()
        self.display_hero()
        self.display_deferred()
        self.display_indicators()
        # Move minimap to upper right corner (scaled 2x: 1280 - 64 - 16, 16)
        self.show_map((1280 - 64 - 16, 16))
        self.show_info()

    def show(self):
        """Display the screen."""
        # Timing counters are debug information: shown only with --debug
        di.debug_message(XY(1000, 8),"logic: {0:>4.1f}\nrender: {1:>4.1f}".format(
            round(gl.logic_time * 1000, 1), round(gl.render_time * 1000, 1)))
        di.show()

    def start(self):
        mn.show_loading_animation()
        self.load_level()

    def resume(self):
        """
        Enter gameplay with a state already restored by a quick load.

        Unlike start(), the level is not reloaded from the checkpoint:
        load_quick() has already reinstated the level, the screen and the
        player, so only the per-session helpers are refreshed here.
        """
        gl.screen_manager.snap_camera()
        self.screens_map = self.init_map
        gl.exit_level_flag = False
        gl.killing_floor = False
        di.info_lines.add("Game loaded")

    def run(self):
        gl.loop_main_loop = True
        self.quit_ask = False
        self.restart_ask = False
        clock = pygame.time.Clock()
        while gl.loop_main_loop:
            # logic processing starts here
            logic_start = time.perf_counter()
            self.loop_begin()
            self.loop_events()
            self.loop_run()

            # Check for level exit (EB.C:263-276)
            if gl.exit_level_flag:
                gl.exit_level_flag = False
                # Load next level based on exit code
                if gl.next_level_code < len(gl.level_names):
                    # "Well done" screen between levels (EB.C:2025-2026)
                    if mn.show_level_completed(gl.current_level + 1) == "quit":
                        gl.loop_main_loop = False
                    else:
                        gl.current_level = gl.next_level_code
                        # level -1 forces the new level's own entrance
                        # checkpoint to be adopted on load (like a new game)
                        gl.checkpoint.update(-1, None)
                        mn.show_loading_animation()
                        self.load_level()
                        di.info_lines.add("Level %d: %s" % (gl.current_level + 1, gl.level_names[gl.current_level]))
                else:
                    # Game completed
                    di.info_lines.add("Congratulations! Game completed!")
                    gl.game_completed = True
                    gl.loop_main_loop = False

            gl.logic_time = time.perf_counter() - logic_start
            # logic processing ended
            # rendering starts here
            render_start = time.perf_counter()
            self.loop_end()
            gl.render_time = time.perf_counter() - render_start
            # rendering ended
            # In-game confirmation prompts (EB.C:1103-1129) - drawn over the
            # rendered frame, block until Y or N
            if self.quit_ask:
                self.quit_ask = False
                self.restart_ask = False
                # Leaving the level (Esc / gamepad START): offer to keep the
                # progress. Both answers leave the level, Y additionally
                # writes quick.sav which the menu's CONTINUE restores.
                if mn.ask_confirmation("save game*(y or n)"):
                    self.quick_save()
                gl.loop_main_loop = False
            elif self.restart_ask:
                self.restart_ask = False
                if mn.ask_confirmation("restart*level?*(y or n)"):
                    self.restart_level()
            self.show() # show the screen
            gl.counter += 1
            clock.tick(20)  # keep constant frame rate (20fps)

    def stop(self):
        pass

    def reset_state(self):
        """Reset game state for a new game."""
        gl.current_level = 0
        gl.disks = 0
        gl.disk_positions = []
        gl.exit_level_flag = False
        gl.next_level_code = 0
        gl.killing_floor = False
        gl.game_completed = False
        # Level -1 means "no checkpoint of this level yet": the entrance
        # checkpoint stored in the level data becomes the respawn point
        # (same rule restart_level() uses).
        gl.disabled_checkpoints.clear()
        gl.checkpoint_entity = None
        gl.checkpoint.update(-1, None)
        # Reset player state
        if gl.player:
            gl.player.power = 0
            gl.player.ammo = 0
            gl.player.temp = 0


class Game:
    """
    Main game class.
    Singleton by design.
    """
    def __init__(self):
        if gl.log_filename:
            # Log to file when filename is set (INFO level to reduce verbosity)
            logging.basicConfig(filename=gl.log_filename,
                                filemode="w", format=(
                                '%(levelname)s: %(funcName)s(): %(message)s'),
                                level=logging.INFO)
        else:
            # Log to console when no filename
            logging.basicConfig(level=logging.DEBUG)

    def init(self):
        di.init_display()
        di.info_lines.add("pyelectroman started")
        time.perf_counter()

    def quit(self):
        di.quit_display()

def parse_args(argv):
    """
    Apply command line flags.

    --debug  enables on-screen debug information (info lines above the
             game scene, status line below it and the timing counters).
    """
    if "--debug" in argv:
        gl.debug_mode = True


def fast_main():
    game = Game()
    game.init()
    gameplay = Gameplay()

    # Main menu loop
    running = True
    while running:
        # Title page with music (EB.C:2020) - fire advances to the menu
        if mn.show_title_screen() == "quit":
            running = False
            continue

        # Show main menu
        menu_result = mn.show_main_menu()

        if menu_result == "quit":
            running = False
            continue

        resumed = False
        if menu_result == "continue":
            # CONTINUE restores the quick save (quick.sav) written by F5 or
            # by the "save game (y or n)" prompt when leaving a level
            if mn.load_quick_game():
                resumed = True
            else:
                di.info_lines.add("Failed to load quick save")
                continue

        elif menu_result == "new_game":
            # Reset to fresh game state
            gameplay.reset_state()
            di.info_lines.add("New game started")

        # Start and run gameplay
        if resumed:
            gameplay.resume()
        else:
            gameplay.start()
        gameplay.run()
        gameplay.stop()

        # Check if game was completed or player quit
        if gl.game_completed:
            # Congratulations screen with music (EB.C:2029), then back to title
            if mn.show_congratulations() == "quit":
                running = False
            di.info_lines.add("Thanks for playing!")
            gl.game_completed = False
        # Otherwise, player pressed ESC - return to menu

    game.quit()


def profile_main():
    # This is the main function for profiling
    # We've renamed our original main() above to real_main()
    import cProfile, pstats
    from io import StringIO
    prof = cProfile.Profile()
    prof = prof.runctx("real_main()", globals(), locals())
    stream = StringIO()
    stats = pstats.Stats(prof, stream=stream)
    stats.sort_stats("calls")
    stats.print_stats(80)  # how many to print
    # The rest is optional.
    #stats.print_callees()
    #stats.print_callers()
    logging.info("Profile data:\n%s", stream.getvalue())


main = fast_main

if __name__ == "__main__":
    import sys
    parse_args(sys.argv[1:])
    main()