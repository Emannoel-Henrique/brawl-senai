"""Four-player keyboard and hot-plugged SDL/Xbox input.

Call process(events, dt) once per display frame, then frames(count) once per
simulation step. Jump/skill presses remain queued until consumed by frames().
Mapped SDL controllers take precedence over raw joystick input for each device.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any
import pygame

try:
    from pygame._sdl2 import controller as _sdl_controller
except ImportError:
    _sdl_controller = None


@dataclass
class InputFrame:
    move: float = 0.0
    aim_x: float = 0.0
    aim_y: float = 0.0
    jump: bool = False
    shoot: bool = False
    melee: bool = False
    skill: bool = False
    interact: bool = False
    down: bool = False


def radial_deadzone(x: float, y: float, deadzone: float = .20) -> tuple[float, float]:
    """Remove stick drift and scale the remaining travel continuously to 1."""
    x, y = float(x), float(y)
    if not math.isfinite(x) or not math.isfinite(y):
        return 0.0, 0.0
    length = math.hypot(x, y)
    if length <= deadzone:
        return 0.0, 0.0
    strength = min(1.0, (length - deadzone) / (1.0 - deadzone))
    return x / length * strength, y / length * strength


# left, right, jump, shoot, skill, melee, down. The down key drops through
# ledges, so the strike moved next to the attack keys.
KEYBOARD = (
    (pygame.K_a, pygame.K_d, pygame.K_w, pygame.K_f, pygame.K_g, pygame.K_r, pygame.K_s),
    (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_COMMA, pygame.K_PERIOD, pygame.K_SLASH, pygame.K_DOWN),
    (pygame.K_j, pygame.K_l, pygame.K_i, pygame.K_u, pygame.K_o, pygame.K_y, pygame.K_k),
    (pygame.K_KP4, pygame.K_KP6, pygame.K_KP8, pygame.K_KP5, pygame.K_KP0, pygame.K_KP3, pygame.K_KP2),
)
# Same physical key on ABNT2 (";") and US ("/") keyboards, plus right Ctrl.
EXTRA_MELEE_KEYS = ((), (pygame.K_SEMICOLON, pygame.K_RCTRL), (), ())
KEYBOARD_LABELS = ("TECLADO A/D", "TECLADO SETAS", "TECLADO J/L", "TECLADO NUM")
INTERACT_KEYS = (pygame.K_e, pygame.K_RSHIFT, pygame.K_h, pygame.K_KP1)
INTERACT_LABELS = ("E", "SHIFT DIR", "H", "NUM 1")
AIM_UP_KEYS = (pygame.K_q, pygame.K_PAGEUP, pygame.K_t, pygame.K_KP9)
AIM_UP_LABELS = ("Q", "PAGE UP", "T", "NUM 9")


@dataclass(frozen=True)
class MenuAction:
    command: str
    slot: int
    source: tuple[str, int]


@dataclass
class _Device:
    instance_id: int
    slot: int
    handle: Any
    joystick: Any
    mapped: bool
    name: str
    previous: dict[str, bool] = field(default_factory=dict)
    event_down: set[str] = field(default_factory=set)
    direction: str | None = None
    repeat_time: float = 0.0
    state: InputFrame = field(default_factory=InputFrame)


_DEFAULT = object()


class InputManager:
    """Up to four stable pad slots; free human seats share keyboard layouts.

    Optional backend arguments are for deterministic tests without hardware.
    Device removal never moves the other players into different slots.
    """

    def __init__(self, *, joystick_backend=None, controller_backend=_DEFAULT):
        self.joysticks = joystick_backend or pygame.joystick
        self.controllers = _sdl_controller if controller_backend is _DEFAULT else controller_backend
        self.devices: dict[int, _Device] = {}
        self.slots: list[_Device | None] = [None] * 4
        self.held: set[int] = set()
        self._jump = [False] * 4
        self._skill = [False] * 4
        self._interact = [False] * 4
        self._disconnects: list[int] = []
        self.errors: list[str] = []
        self._focused = True
        self.player_count = 4
        self.bots = [0]*4
        self.menu_actions: list[MenuAction] = []
        self.personal_actions: list[MenuAction] = []
        try:
            self.joysticks.init()
        except Exception as exc:
            self.errors.append(f"Joystick indisponivel: {exc}")
        if self.controllers is not None:
            try:
                self.controllers.init()
            except Exception as exc:
                self.errors.append(f"SDL controller indisponivel: {exc}")
                self.controllers = None
        self._discover()

    @property
    def connected_count(self) -> int:
        return len(self.devices)

    def configure(self, count=4, bots=()):
        self.player_count = max(1, min(4, count))
        self.bots = list(bots[:4])+[0]*max(0, 4-len(bots))

    def keyboard_slots(self):
        """The first free human seat gets WASD, even if that seat is P4."""
        return [slot for slot in range(self.player_count)
                if self.slots[slot] is None and not self.bots[slot]]

    def keyboard_layout(self, slot):
        free = self.keyboard_slots()
        return free.index(slot) if slot in free else None

    def source_for_slot(self, slot=0):
        device = self.slots[slot]
        return ('pad', device.instance_id) if device else ('keyboard', 0)

    def source_connected(self, source):
        return source[0] == 'keyboard' or source[1] in self.devices

    def keyboard_slot(self):
        return next(iter(self.keyboard_slots()), -1)

    def interact_label(self, slot):
        layout = self.keyboard_layout(slot)
        return 'LB' if self.slots[slot] else INTERACT_LABELS[layout] if layout is not None else 'E'

    def aim_label(self, slot):
        layout = self.keyboard_layout(slot)
        return 'ANALÓGICO DIR.' if self.slots[slot] else AIM_UP_LABELS[layout] if layout is not None else 'Q'

    def _discover(self):
        try:
            count = self.joysticks.get_count()
        except Exception:
            return
        for index in range(count):
            self._open(index)

    def _open(self, index: int):
        if all(self.slots):
            return
        joystick = None
        handle = None
        try:
            joystick = self.joysticks.Joystick(int(index))
            joystick.init()
            iid = joystick.get_instance_id()
            if iid in self.devices:
                return
            mapped = False
            if self.controllers is not None:
                try:
                    if self.controllers.is_controller(index):
                        handle = self.controllers.Controller(index)
                        mapped = True
                except Exception:
                    handle = None
            handle = handle or joystick
            slot = self.slots.index(None)
            name = joystick.get_name() or "CONTROLE"
            device = _Device(iid, slot, handle, joystick, mapped, str(name))
            self.devices[iid] = device
            self.slots[slot] = device
            self.held.clear()
            self.clear_edges()
        except Exception as exc:
            self.errors.append(f"Nao foi possivel conectar controle: {exc}")
            if handle is not None and handle is not joystick:
                self._safe_close(handle)
            if joystick is not None:
                self._safe_close(joystick)

    @staticmethod
    def _safe_close(handle):
        try:
            handle.quit()
        except Exception:
            pass

    def _remove(self, iid: int):
        device = self.devices.pop(iid, None)
        if device is None:
            return
        self.slots[device.slot] = None
        self.held.clear()
        self.clear_edges()
        self._disconnects.append(device.slot)
        if device.handle is not device.joystick:
            self._safe_close(device.handle)
        self._safe_close(device.joystick)

    @staticmethod
    def _append(menu: list[str], command: str):
        if command not in menu:
            menu.append(command)

    def _emit(self, menu, command, slot, source, personal=True):
        action = MenuAction(command, slot, source)
        if action not in self.menu_actions:
            self.menu_actions.append(action)
        if personal and action not in self.personal_actions:
            self.personal_actions.append(action)
        self._append(menu, command)

    def _pad_emit(self, menu, command, device):
        self._emit(menu, command, device.slot, ('pad', device.instance_id))

    def _press(self, device: _Device, action: str, menu: list[str]):
        if action == "jump":
            self._jump[device.slot] = True
        elif action == "skill":
            self._skill[device.slot] = True
        elif action == "interact":
            self._interact[device.slot] = True
        command = {"jump": "confirm", "melee": "back", "pause": "pause"}.get(action)
        if command:
            self._pad_emit(menu, command, device)

    @staticmethod
    def _button_action(button: int, mapped: bool) -> str | None:
        if mapped:
            mapping = {
                pygame.CONTROLLER_BUTTON_A: "jump", pygame.CONTROLLER_BUTTON_B: "melee",
                pygame.CONTROLLER_BUTTON_X: "shoot", pygame.CONTROLLER_BUTTON_Y: "skill",
                pygame.CONTROLLER_BUTTON_RIGHTSHOULDER: "skill", pygame.CONTROLLER_BUTTON_START: "pause",
                pygame.CONTROLLER_BUTTON_LEFTSHOULDER: "interact",
                pygame.CONTROLLER_BUTTON_BACK: "back",
                pygame.CONTROLLER_BUTTON_DPAD_UP: "up", pygame.CONTROLLER_BUTTON_DPAD_DOWN: "down",
                pygame.CONTROLLER_BUTTON_DPAD_LEFT: "left", pygame.CONTROLLER_BUTTON_DPAD_RIGHT: "right",
            }
        else:
            # SDL's raw Xbox layout. Unknown pads still have keyboard backup.
            mapping = {0: "jump", 1: "melee", 2: "shoot", 3: "skill", 4: "interact", 5: "skill", 6: "back", 7: "pause"}
        return mapping.get(button)

    def process(self, events, dt: float) -> list[str]:
        menu: list[str] = []
        self.menu_actions = []
        self.personal_actions = []
        for event in events:
            etype = event.type
            if etype in (pygame.JOYDEVICEADDED, pygame.CONTROLLERDEVICEADDED):
                self._open(getattr(event, "device_index", getattr(event, "which", -1)))
            elif etype in (pygame.JOYDEVICEREMOVED, pygame.CONTROLLERDEVICEREMOVED):
                self._remove(getattr(event, "instance_id", getattr(event, "which", -1)))
            elif etype == pygame.WINDOWFOCUSLOST:
                self._focused = False
                self.held.clear()
                self.clear_edges()
            elif etype == pygame.WINDOWFOCUSGAINED:
                self._focused = True
            elif etype == pygame.KEYDOWN:
                if event.key in self.held or getattr(event, "repeat", False):
                    continue
                self.held.add(event.key)
                for layout, slot in enumerate(self.keyboard_slots()):
                    keys = KEYBOARD[layout]
                    if event.key == keys[2]:
                        self._jump[slot] = True
                    elif event.key == keys[4]:
                        self._skill[slot] = True
                    if event.key == INTERACT_KEYS[layout]:
                        self._interact[slot] = True
                    command = {keys[0]:'left', keys[1]:'right', keys[2]:'up', keys[6]:'down',
                               keys[3]:'confirm', INTERACT_KEYS[layout]:'confirm'}.get(event.key)
                    if command:
                        self.personal_actions.append(MenuAction(command, slot, ('keyboard', layout)))
                key_menu = {
                    pygame.K_UP: "up", pygame.K_DOWN: "down",
                    pygame.K_LEFT: "left", pygame.K_RIGHT: "right",
                    pygame.K_RETURN: "confirm", pygame.K_KP_ENTER: "confirm", pygame.K_SPACE: "confirm",
                    pygame.K_BACKSPACE: "back", pygame.K_ESCAPE: "pause", pygame.K_p: "pause",
                }
                if event.key in key_menu:
                    command = key_menu[event.key]
                    # Arrows are the menu navigation of the primary keyboard;
                    # in the draft they still belong to the arrow-key player.
                    self._emit(menu, command, self.keyboard_slot(), ('keyboard', 0), personal=False)
                    if event.key not in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
                        self.personal_actions.append(MenuAction(command, self.keyboard_slot(), ('keyboard', 0)))
            elif etype == pygame.KEYUP:
                self.held.discard(event.key)
            elif etype in (pygame.JOYBUTTONDOWN, pygame.CONTROLLERBUTTONDOWN):
                iid = getattr(event, "instance_id", getattr(event, "joy", getattr(event, "which", -1)))
                device = self.devices.get(iid)
                mapped_event = etype == pygame.CONTROLLERBUTTONDOWN
                if device is None or device.mapped != mapped_event:
                    continue
                action = self._button_action(event.button, device.mapped)
                if action:
                    device.event_down.add(action)
                    self._press(device, action, menu)
                    if action in ("up", "down", "left", "right", "back"):
                        self._pad_emit(menu, action, device)
        for device in list(self.devices.values()):
            try:
                self._poll(device, max(0.0, min(float(dt), .25)), menu)
            except Exception:
                # A cable can disappear between the removal event and polling.
                self._remove(device.instance_id)
        if not self._focused:
            self.clear_edges()
            self.menu_actions = []; self.personal_actions = []
            return []
        return menu

    @staticmethod
    def _axis(device: _Device, index: int) -> float:
        if device.mapped:
            raw = device.handle.get_axis(index)
            return max(-1.0, min(1.0, raw / 32767.0))
        if index >= device.handle.get_numaxes():
            return 0.0
        return max(-1.0, min(1.0, float(device.handle.get_axis(index))))

    @staticmethod
    def _button(device: _Device, index: int) -> bool:
        if not device.mapped and index >= device.handle.get_numbuttons():
            return False
        return bool(device.handle.get_button(index))

    def _poll(self, device: _Device, dt: float, menu: list[str]):
        b = lambda index: self._button(device, index)
        if device.mapped:
            if hasattr(device.handle, "attached") and not device.handle.attached():
                self._remove(device.instance_id)
                return
            lx, ly = radial_deadzone(self._axis(device, pygame.CONTROLLER_AXIS_LEFTX), self._axis(device, pygame.CONTROLLER_AXIS_LEFTY))
            rx, ry = radial_deadzone(self._axis(device, pygame.CONTROLLER_AXIS_RIGHTX), self._axis(device, pygame.CONTROLLER_AXIS_RIGHTY))
            dx = int(b(pygame.CONTROLLER_BUTTON_DPAD_RIGHT)) - int(b(pygame.CONTROLLER_BUTTON_DPAD_LEFT))
            dy = int(b(pygame.CONTROLLER_BUTTON_DPAD_DOWN)) - int(b(pygame.CONTROLLER_BUTTON_DPAD_UP))
            actions = {"jump": b(pygame.CONTROLLER_BUTTON_A), "melee": b(pygame.CONTROLLER_BUTTON_B),
                       "shoot": b(pygame.CONTROLLER_BUTTON_X) or self._axis(device, pygame.CONTROLLER_AXIS_TRIGGERRIGHT) > .28,
                       "skill": b(pygame.CONTROLLER_BUTTON_Y) or b(pygame.CONTROLLER_BUTTON_RIGHTSHOULDER),
                       "pause": b(pygame.CONTROLLER_BUTTON_START), "back": b(pygame.CONTROLLER_BUTTON_BACK),
                       "interact": b(pygame.CONTROLLER_BUTTON_LEFTSHOULDER)}
        else:
            lx, ly = radial_deadzone(self._axis(device, 0), self._axis(device, 1))
            # Common SDL raw Xbox layout: left XY, right XY, LT, RT.
            rx, ry = radial_deadzone(self._axis(device, 2), self._axis(device, 3))
            hat = device.handle.get_hat(0) if device.handle.get_numhats() else (0, 0)
            dx, dy = hat[0], -hat[1]
            trigger = self._axis(device, 5) > .25 if device.handle.get_numaxes() > 5 else False
            actions = {"jump": b(0), "melee": b(1), "shoot": b(2) or trigger,
                       "skill": b(3) or b(5), "pause": b(7), "back": b(6), "interact": b(4)}
        for action, pressed in actions.items():
            if pressed and not device.previous.get(action, False) and action not in device.event_down:
                self._press(device, action, menu)
                if action == "back":
                    self._pad_emit(menu, "back", device)
        device.previous = actions
        device.event_down.clear()
        mx, my = (dx or lx), (dy or ly)
        direction = None
        if abs(mx) > .58 or abs(my) > .58:
            direction = ("right" if mx > 0 else "left") if abs(mx) > abs(my) else ("down" if my > 0 else "up")
        if direction != device.direction:
            device.direction = direction
            device.repeat_time = .33
            if direction:
                self._pad_emit(menu, direction, device)
        elif direction:
            device.repeat_time -= dt
            if device.repeat_time <= 0:
                self._pad_emit(menu, direction, device)
                device.repeat_time = .13
        device.state = InputFrame(move=float(dx or lx), aim_x=rx, aim_y=ry,
                                  shoot=actions["shoot"], melee=actions["melee"], down=my > .6)

    def frames(self, count: int) -> list[InputFrame]:
        result = []
        for slot in range(max(0, min(4, count))):
            layout = self.keyboard_layout(slot)
            keys = KEYBOARD[layout] if layout is not None else None
            held = lambda index: keys is not None and keys[index] in self.held
            move = float(int(held(1)) - int(held(0)))
            device = self.slots[slot]
            pad = device.state if device else InputFrame()
            axis = move if move else pad.move
            aim_x, aim_y = (pad.aim_x, pad.aim_y) if abs(pad.aim_x) + abs(pad.aim_y) > .001 else (0.0, 0.0)
            if layout is not None and AIM_UP_KEYS[layout] in self.held:
                aim_x, aim_y = move, -1.
            melee = held(5) or (layout is not None and any(key in self.held for key in EXTRA_MELEE_KEYS[layout]))
            result.append(InputFrame(axis, aim_x, aim_y, self._jump[slot],
                                     held(3) or pad.shoot,
                                     melee or pad.melee, self._skill[slot],
                                     self._interact[slot], held(6) or pad.down)
                          if self._focused else InputFrame())
            self._jump[slot] = self._skill[slot] = self._interact[slot] = False
        return result

    def clear_edges(self):
        """Discard menu-confirm presses when beginning/resuming a match."""
        self._jump[:] = [False] * 4
        self._skill[:] = [False] * 4
        self._interact[:] = [False] * 4

    def labels(self, count: int = 4) -> list[str]:
        return [f"CONTROLE {i + 1} / {self.slots[i].name[:24]}" if self.slots[i] else
                KEYBOARD_LABELS[self.keyboard_layout(i)] if self.keyboard_layout(i) is not None else 'SEM JOGADOR'
                for i in range(max(0, min(4, count)))]

    def rumble(self, slot: int, intensity: float = .5, duration: float = .15) -> bool:
        if not 0 <= slot < len(self.slots) or self.slots[slot] is None:
            return False
        try:
            strength = max(0.0, min(1.0, float(intensity)))
            return bool(self.slots[slot].handle.rumble(strength, strength * .65, max(1, int(duration * 1000))))
        except Exception:
            return False

    def consume_disconnects(self) -> list[int]:
        result, self._disconnects = self._disconnects, []
        return result

    def close(self):
        for device in list(self.devices.values()):
            self._remove(device.instance_id)
        self.held.clear()
        self.clear_edges()
