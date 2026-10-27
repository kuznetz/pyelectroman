# Player Weapon Mechanics

This document describes every mechanic of the player's weapon in PyElectroMan:
the five power levels, their ammo, heat, projectile behaviour and the rules that
apply to all of them.

Implementation sources:

| Subject | Location |
|---------|----------|
| Player weapon state, firing, projectile entity | [`emhero.py`](../emhero.py) |
| Weapon sprite sets (per level, left/right) | [`Weapons`](../emother.py:70) |
| Weapon sounds (`wpn_1.wav` … `wpn_5.wav`, `xplosion.wav`) | [`SOUND_FILES`](../emsound.py:45) |
| Weapon reset on level load | [`em.py`](../em.py:329) |
| Weapon reset on respawn | [`PlayerEntity.respawn()`](../emhero.py:867) |
| Quick save / quick load of weapon state | [`_restore_player()`](../emquicksave.py:463) |
| Debug weapon selection keys | [`em.py`](../em.py:193) |

---

## 1. Overview

The player carries a **single upgradable energy weapon**. It has six discrete
states, called *power* or *battery power*:

* `0` — no weapon (cannot fire),
* `1` … `5` — five weapon levels with different projectile types.

Power is stored in [`PlayerEntity.power`](../emhero.py:134). The current level
selects three things at once:

1. which projectile entity is spawned (sprite set, speed, offset, collision box),
2. how many shots a magazine holds ([`PlayerEntity.magazine`](../emhero.py:138)),
3. how much heat a single shot adds ([`PlayerEntity.heat`](../emhero.py:139)).

Additional state per player:

| Field | Meaning |
|-------|---------|
| `power` | weapon level 0…5 |
| `ammo` | shots left in the current magazine |
| `temp` | accumulated heat, `0`…`5` |
| `cooldown` | frames to wait before the heat drops again |
| `fired` | latch that allows only one shot per button press |
| `orientation` | `0` = facing left, `1` = facing right |

---

## 2. Input and firing gate

Firing is handled in [`PlayerEntity.update()`](../emhero.py:990):

* Fire button: <kbd>Space</kbd> on the keyboard ([`KeyboardController`](../emgame.py:74)),
  `X` on the gamepad ([`PadController`](../emgame.py:94)).
* **One shot per press.** `self.fired` is set after a shot and only cleared when
  the button is released, so holding the button does *not* auto-fire.
* A shot is only possible while the player is in one of the states
  `state_stand`, `state_move`, `state_jump`, `state_fall`, `state_land`.
  Firing is blocked during death and during teleport animations.
* `power == 0` means no shot at all.
* Heat gate: a shot is only fired if
  `temp + heat[power] <= 5` ([`fire_weapon()`](../emhero.py:1046)).
  If there is not enough heat head-room, **nothing happens**: no projectile, no
  ammo loss, no sound, no visible feedback.

---

## 3. Ammo / magazine

Magazines are per-level and are **not shared**:

| Power | Level name | Magazine | Casual mode (×3) |
|:-----:|-----------|---------:|-----------------:|
| 0 | no weapon | 0 | 0 |
| 1 | short missile | 20 | 60 |
| 2 | long missile | 15 | 45 |
| 3 | long missile (efficient variant) | 25 | 75 |
| 4 | penetrating missile | 10 | 30 |
| 5 | bow (double height) | 15 | 45 |

Rules ([`max_ammo()`](../emhero.py:550), [`select_weapon()`](../emhero.py:557),
[`inc_power()`](../emhero.py:561)):

* Collecting a **battery** raises the level by one (capped at 5) and **refills the
  magazine to full** — even at the maximum level a battery tops the ammo up.
* Selecting a level always refills that level's magazine
  (`select_weapon()` sets `ammo = max_ammo(power)`).
* Ammo is decremented at the moment of the shot.
* When the last round is fired, the weapon **automatically downgrades one level**
  and the lower level starts with a full magazine
  ([`fire_weapon()`](../emhero.py:1058)). Level 1 falls back to level 0 (no weapon).
* `CASUAL_AMMO_MULT = 3` ([`emhero.py`](../emhero.py:30)) triples every non-zero
  magazine in casual mode.

---

## 4. Heat, temperature and cooldown

Heat is the balancing mechanism between weapon levels
([`power_and_cooldown()`](../emhero.py:653)).

* Maximum temperature: **5**.
* Heat per shot: `heat = [0, 1, 2, 1, 4, 3]` for levels 0…5.
* While any weapon is equipped the temperature never drops below **1**
  (`if self.power > 0 and self.temp == 0: self.temp = 1`).
* Cooling: when `temp > 1`, one point is removed every **5 frames** — a 4-frame
  `cooldown` counter runs first, then one temperature point is removed and the
  cooldown is re-armed with 4.
* A successful shot also re-arms `cooldown = 4`.

Consequences:

| Power | Heat per shot | Shots in a burst from temp 1 | Sustained interval | Sustained rate @20 FPS |
|:-----:|:-------------:|:----------------------------:|:------------------:|:----------------------:|
| 1 | 1 | 4 | 5 frames | 4 shots/s |
| 2 | 2 | 2 | 10 frames | 2 shots/s |
| 3 | 1 | 4 | 5 frames | 4 shots/s |
| 4 | 4 | 1 | 20 frames | 1 shot/s |
| 5 | 3 | 1 (2nd shot after cooling to temp ≤ 2) | 15 frames | ≈1.3 shots/s |

Level 4 is therefore a "single heavy shot" weapon, level 5 fires in slow
deliberate pairs, and levels 1 and 3 can be spammed until the magazine empties.

---

## 5. HUD indicators

[`PlayerEntity.show_hud()`](../emhero.py:669):

* **Left LED bar** = current temperature (`temp`).
* **Right LED** = current power level.
* If `ammo < 3` and a weapon is equipped, the right LED **blinks** between
  `power` and `power - 1` as a low-ammo warning.

---

## 6. Projectile lifecycle (common rules)

Every shot spawns a [`Projectile`](../emhero.py:1063) entity from the table
[`PlayerEntity.projectiles`](../emhero.py:1018):

| Power | `_L` offset | `_R` offset | Step per frame |
|:-----:|-------------|-------------|:--------------:|
| 1 | `(-38, +32)` | `(+38, +32)` | 28 |
| 2 | `(-46, +32)` | `(+46, +32)` | 32 |
| 3 | `(-46, +32)` | `(+46, +32)` | 28 |
| 4 | `(-46, +32)` | `(+46, +32)` | 24 |
| 5 | `(-36, +8)` | `(+36, +8)` | 32 |

Per frame ([`Projectile.update()`](../emhero.py:1084)):

1. Advance the animation frame (one sprite per frame).
2. Move horizontally by `step` pixels (negative = left). There is **no gravity and
   no vertical movement** — every weapon fires strictly horizontally.
3. Check wall collision.
4. Check collisions with all active entities.
5. Vanish silently when the projectile leaves the screen
   (`x > 13 * 48` or `x < -48`) — no explosion, no sound, for every level.

Only entities of the **current screen** are tested, so projectiles never cross
room boundaries; they are removed at the screen edge instead.

---

## 7. Per-weapon mechanics

### Level 0 — no weapon

* Magazine 0, heat 0. Firing does nothing.
* This is the state after level load, after respawn, after activating a
  checkpoint, or when a level-1 magazine runs dry.

### Level 1 — short missile (`short_miss_proc`)

| Property | Value |
|----------|-------|
| Projectile type keys | `1_L`, `1_R` (both use sprite frames 8–15) |
| Animation | 8 frames |
| Magazine / heat | 20 / 1 |
| Spawn offset | ±38 px horizontal, +32 px vertical |
| Speed | 28 px/frame |
| Range | **limited** — the projectile is removed when its animation wraps after one full cycle: 7 movements × 28 = **≈196 px** (≈4 tiles) |
| Penetration | none |
| Wall hit | single visual explosion, silent |
| Sound | `wpn_1.wav` |

The animation wrap is detected in [`Projectile.update()`](../emhero.py:1092);
this is the only level with a hard range limit. Effectively a short-range,
cheap-to-fire (heat 1) close-quarters weapon with the largest magazine.

### Level 2 — long missile (`long_miss_proc`)

| Property | Value |
|----------|-------|
| Projectile type keys | `2_R` sprites 16–19, `2_L` sprites 20–23 |
| Animation | 4 frames |
| Magazine / heat | 15 / **2** |
| Spawn offset | ±46 px horizontal, +32 px vertical |
| Speed | **32 px/frame** (fastest with level 5) |
| Range | unlimited (until wall / enemy / screen edge) |
| Penetration | none — removed on the first enemy hit |
| Wall hit | single visual explosion, silent |
| Sound | `wpn_2.wav` |

The fast, straight-flying long-range missile, but it costs 2 heat per shot, so it
is the most "expensive to spam" of the mid levels.

### Level 3 — long missile variant (`long_miss_proc`)

| Property | Value |
|----------|-------|
| Projectile type keys | `3_R` sprites 24–26, `3_L` sprites 28–30 |
| Animation | 3 frames |
| Magazine / heat | **25** / **1** |
| Spawn offset | ±46 px horizontal, +32 px vertical |
| Speed | 28 px/frame |
| Range | unlimited |
| Penetration | none |
| Wall hit | single visual explosion, silent |
| Sound | `wpn_3.wav` |

Same family as level 2 but with a bigger magazine, cheaper heat and slightly
slower flight — the best sustained-fire level in the game.

### Level 4 — penetrating missile (`long_miss_proc` + `AUX_2`)

| Property | Value |
|----------|-------|
| Projectile type keys | `4_R` sprites 32–33, `4_L` sprites 34–35 |
| Animation | 2 frames |
| Magazine / heat | 10 / **4** |
| Spawn offset | ±46 px horizontal, +32 px vertical |
| Speed | **24 px/frame** (slowest) |
| Range | unlimited |
| Penetration | **yes, through enemies** — the projectile is *not* removed on enemy hits and keeps hitting every overlapped enemy each frame |
| Wall hit | single visual explosion, silent |
| Sound | `wpn_4.wav` |

Penetration is implemented in
[`Projectile.check_all_collisions()`](../emhero.py:1225):

```python
if hit_enemy_this_frame:
    if self.power_level == 4:
        return False   # continue through enemies
    else:
        return True    # remove on hit
```

Important: **destructible objects still stop a level-4 shot** — the projectile is
always removed after hitting a shootable object, regardless of level.

### Level 5 — bow (`bow_proc`)

| Property | Value |
|----------|-------|
| Projectile type keys | `5_R` sprites 36–37, `5_L` sprites 38–39 |
| Animation | 2 frames, drawn as a **double-height** graphic (two sprites stacked) |
| Magazine / heat | 15 / 3 |
| Spawn offset | ±36 px horizontal, **+8 px** vertical (fired higher than other levels) |
| Speed | 32 px/frame |
| Range | unlimited |
| Penetration | none |
| Collision box | extended vertically to `SPRITE_Y * 2 - 12` = **84 px**, covering both sprite halves |
| Wall hit | **triple explosion** (`bow_end_proc`) |
| Sound | `wpn_5.wav` |

Details:

* Display: [`Projectile.display()`](../emhero.py:1385) blits the current frame and
  the next frame one tile below it.
* Extended hit box: [`collides_with()`](../emhero.py:1249) and
  [`check_wall_collision()`](../emhero.py:1152) both enlarge the projectile box,
  so the bow covers two tile rows.
* Wall hit: [`bow_end_explosion()`](../emhero.py:1365) spawns three explosions
  staggered vertically ahead of the impact point:
  `(x ∓ 2, y)`, `(x ± 16, y + 24)`, `(x ∓ 2, y + 48)` (scaled coordinates).
  Like the other wall impacts, this triple explosion is **silent** — only the
  projectile spawn sound is played.
* Leaving the screen is still a silent removal: the triple explosion belongs only
  to the *wall-hit* path, not to the screen-exit path.

### Quick reference

| Power | Name | Frames | Speed (px/f) | Offset | Ammo | Heat | Penetrates enemies | Range | Wall hit |
|:-----:|------|-------:|-------------:|--------|-----:|-----:|:------------------:|-------|----------|
| 0 | none | — | — | — | 0 | 0 | — | — | — |
| 1 | short missile | 8 | 28 | ±38, +32 | 20 | 1 | no | ≈196 px | 1 explosion |
| 2 | long missile | 4 | 32 | ±46, +32 | 15 | 2 | no | unlimited | 1 explosion |
| 3 | long missile (efficient) | 3 | 28 | ±46, +32 | 25 | 1 | no | unlimited | 1 explosion |
| 4 | penetrating missile | 2 | 24 | ±46, +32 | 10 | 4 | **yes** | unlimited | 1 explosion |
| 5 | bow | 2 (×2 tall) | 32 | ±36, +8 | 15 | 3 | no | unlimited | **3 explosions** |

Sprite frame ranges come from [`Weapons`](../emother.py:70); assets live in
`data/weapons/weapons.ebs` and `weapons_00.png` … `weapons_39.png`
(frames 27 and 31 are unused).

---

## 8. Impact rules

### Enemies

Handled by [`Projectile.hit_enemy()`](../emhero.py:1266):

* **Every weapon level kills an enemy instantly.** `enemy.take_damage(level)` is
  called, but both [`EnemyPlatform.take_damage()`](../emgame.py:1374) and
  [`EnemyFlying.take_damage()`](../emgame.py:1615) ignore the argument and call
  `die()`. The differences between levels are range, penetration, coverage, heat
  and ammo — not damage.
* On a hit: an explosion is spawned at the projectile position and the `blast`
  sound (`xplosion.wav`) is played.
* The collision loop inspects **all** active entities in the same frame, so a
  single projectile can mark several overlapping enemies as hit; only level 4
  survives the frame and keeps flying.

### Shootable objects

Handled by [`Projectile.hit_object()`](../emhero.py:1280):

* An object is hittable only if the `shootable` flag of its **current animation
  frame** is set (batteries are touchable but not shootable).
* The object is always removed and always **stops the projectile**, even at
  level 4.
* Explosion is centred on the object's bounding box centre, plus the `blast`
  sound.
* If the frame also carries the `destroyable` flag, a **broken sprite** is placed
  at the object's grid position and persisted into the level data (sprite index
  `sprite_index + len(sprites)`), so the debris survives room changes. Otherwise
  only the explosion is left behind.

### Walls

Handled by [`Projectile.check_wall_collision()`](../emhero.py:1137):

* A wall blocks the shot only if it has a solid side **facing the projectile's
  direction** (`L` side for a right-moving shot, `R` side for a left-moving one),
  reproducing the original `cave_test()` behaviour.
* Levels 1–4: a single visual explosion at the impact point, no sound.
* Level 5: the triple explosion described above, no sound.

### Screen boundary

Any projectile that leaves the current room is removed without explosion or
sound, on every level.

---

## 9. State resets and persistence

| Event | Effect on the weapon |
|-------|----------------------|
| Level load ([`em.py`](../em.py:329)) | `power = 0`, `ammo = 0`, `temp = 0` |
| Respawn after death ([`respawn()`](../emhero.py:888)) | level reset to pristine state, `power = 0`, `ammo = 0`, `temp = 0` |
| Activating a checkpoint ([`activate_checkpoint()`](../emhero.py:614)) | `power = 0`, `temp = 0`, magazine of level 0 (= none) |
| Battery pickup ([`inc_power()`](../emhero.py:561)) | `power = min(power + 1, 5)`, magazine refilled to full |
| Magazine emptied ([`fire_weapon()`](../emhero.py:1058)) | one level down, magazine of the lower level refilled |
| Quick save ([`_restore_player()`](../emquicksave.py:463)) | `power`, `temp`, `ammo`, `cooldown`, `fired` are stored and restored verbatim |

### Casual mode differences

* Magazine capacity ×3 ([`CASUAL_AMMO_MULT`](../emhero.py:30)).
* Taking a hit ([`take_hit()`](../emhero.py:622)) costs **one battery level**
  instead of a life; the lower level's magazine is refilled and `temp` is clamped
  to 1. With `power == 0` the hero still dies.
* After such a hit the hero blinks for `CASUAL_INVULN_FRAMES = 20` frames and is
  invulnerable during that time.

---

## 10. Sounds

[`emsound.py`](../emsound.py:45):

| Event | Sample |
|-------|--------|
| Firing level 1…5 | `wpn_1.wav` … `wpn_5.wav` |
| Projectile hits an enemy | `xplosion.wav` (`blast`) |
| Projectile destroys a shootable object | `xplosion.wav` (`blast`) |
| Projectile hits a wall | — (silent) |
| Projectile leaves the screen | — (silent) |
| Battery collected | `battery.wav` |

---

## 11. Debug helpers

Available only with the `--debug` command line flag
(see [Debug Shortcuts](../DEBUG_SHORTCUTS.md)):

| Key | Action |
|-----|--------|
| <kbd>Shift</kbd>+<kbd>1</kbd> … <kbd>Shift</kbd>+<kbd>5</kbd> | Select weapon level 1…5 with a full magazine |
| <kbd>Shift</kbd>+<kbd>0</kbd> | Select level 0 (no weapon) |
| <kbd>9</kbd> | Load the weapon test arena (level index 8, generated by [`create_test_level.py`](../create_test_level.py)) |

The arena contains one-sided walls, several shootable/breakable objects and a
checkpoint, and is intended for verifying projectile speed, penetration, the
bow's double-height hit box and the triple explosion.

---

## 12. Implementation map

| Mechanic | Code |
|----------|------|
| Weapon fields, magazine and heat tables | [`PlayerEntity.__init__()`](../emhero.py:134) |
| Magazine capacity (casual ×3) | [`max_ammo()`](../emhero.py:550) |
| Level selection and refill | [`select_weapon()`](../emhero.py:557) |
| Battery pickup | [`inc_power()`](../emhero.py:561) |
| Heat / cooldown update | [`power_and_cooldown()`](../emhero.py:653) |
| HUD indicators | [`show_hud()`](../emhero.py:669) |
| Fire input and one-shot latch | [`PlayerEntity.update()`](../emhero.py:990) |
| Projectile spawn offsets and speeds | [`projectiles`](../emhero.py:1018) |
| Shot gate, heat check, ammo, downgrade | [`fire_weapon()`](../emhero.py:1031) |
| Projectile entity and per-frame logic | [`Projectile`](../emhero.py:1063) |
| Level-1 range limit | [`Projectile.update()`](../emhero.py:1092) |
| Wall collision | [`check_wall_collision()`](../emhero.py:1137) |
| Multi-entity collision and level-4 penetration | [`check_all_collisions()`](../emhero.py:1167) |
| Enemy hit | [`hit_enemy()`](../emhero.py:1266) |
| Shootable object hit / broken sprite | [`hit_object()`](../emhero.py:1280) |
| Bow triple explosion | [`bow_end_explosion()`](../emhero.py:1365) |
| Bow double-height drawing | [`Projectile.display()`](../emhero.py:1385) |
| Weapon sprite sets | [`Weapons`](../emother.py:70) |
