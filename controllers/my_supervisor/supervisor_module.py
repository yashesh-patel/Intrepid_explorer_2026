# supervisor_module.py
import json
import math
import os
import random
from zipfile import ZipFile

from controller import Supervisor
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes


# -------------------------------------------------------------------
# CONSTANTS
# -------------------------------------------------------------------
BOX_RADIUS = 1

RED_RADIUS = 0.24
YELLOW_RADIUS = 0.48
PURPLE_RADIUS = 0.73

COLLECTION_THRESHOLD = 0.03
HOME_THRESHOLD = 0.12

TOTAL_BOXES = 8
ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]

COLOR_MAP = {
    "RED":    [0.5, 0, 0],
    "YELLOW": [1, 1, 0],
    "PURPLE": [0.5, 0, 0.5],
}

PATH_REQUIREMENTS = {
    "RED":    ["RED"],
    "YELLOW": ["RED", "YELLOW"],
    "PURPLE": ["RED", "YELLOW", "PURPLE"],
}

FONT_SIZE = 0.08


# -------------------------------------------------------------------
# SUPERVISOR MODULE
# -------------------------------------------------------------------
class ArenaSupervisor:

    def __init__(self, supervisor):
        print("Initializing Arena Supervisor!")
        self.supervisor = supervisor
        self.timestep = int(self.supervisor.getBasicTimeStep())
        self.run_completed = False

        # --- RSA key generation (done once at startup) ---
        if not os.path.exists("public.pem"):
            key = RSA.generate(2048)
            with open("private.pem", "wb") as f:
                f.write(key.export_key())
            with open("public.pem", "wb") as f:
                f.write(key.publickey().export_key())

        # --- Dynamic centre detection ---
        myself = self.supervisor.getSelf()
        if myself:
            pos = myself.getField("translation").getSFVec3f()
            self.center_x = pos[0]
            self.center_y = pos[1]
            self.center_z = pos[2] + 0.08
            print(f"Dynamic centre: X={self.center_x:.3f}, Y={self.center_y:.3f}, Z={self.center_z:.3f}")
        else:
            self.center_x = 0.382
            self.center_y = 0.54
            self.center_z = -0.01
            print("WARNING: Could not detect Supervisor position. Using fallback centre.")

        self.match_time = 180

        # --- State machine ---
        self.state = "WAIT_DETECTION"
        self.active_box = None
        self.current_index = 0
        self.last_waypoint_touch = None

        # --- Score counters ---
        self.collected_boxes = 0
        self.red_boxes    = 0
        self.yellow_boxes = 0
        self.purple_boxes = 0

        # --- Match data record ---
        self.match_data = {
            "boxes_collected": 0,
            "robot_positions": [],
            "time":            [],
            "spawned_boxes":   [],
            "box_results":     [],
            "score": {
                "red":    0,
                "yellow": 0,
                "purple": 0,
                "total":  0,
            },
        }

        # --- World setup ---
        self._get_robot()
        self._get_boxes()
        self._get_waypoints()
        self._spawn_boxes()

    # =================================================================
    # MAIN LOOP STEP  (called every timestep from my_supervisor.py)
    # =================================================================
    def check_and_update(self) -> bool:
        """
        Returns True  → keep running
        Returns False → stop the while-loop (my_supervisor will pause sim)
        """
        if self.run_completed:
            return False

        current_time = self.supervisor.getTime()

        # --- Activate the next box when idle ---
        if self.state == "WAIT_DETECTION" and self.active_box is None:
            if self.current_index < TOTAL_BOXES:
                self._activate_next_box()

        # --- Per-step monitors ---
        self._monitor_waypoint()
        self._monitor_home()
        
        # --- Record telemetry ---
        robot_pos = self.robot_translation.getSFVec3f()
        self.match_data["time"].append(round(current_time, 2))
        self.match_data["robot_positions"].append([
            round(robot_pos[0], 3),
            round(robot_pos[1], 3),
        ])

        # --- HUD ---
        self._update_labels()

        # --- End conditions ---
        if current_time >= self.match_time:
            print("TIME OVER")
            self.supervisor.setLabel(7, "TIME OVER", 0.35, 0.45, 0.15, 0xFF0000, 0.0, "Arial")
            self._end_match()
            return False

        if self.current_index >= TOTAL_BOXES and self.active_box is None:
            print("MISSION COMPLETE")
            self.supervisor.setLabel(7, "MISSION COMPLETE", 0.25, 0.45, 0.15, 0x00AA00, 0.0, "Arial")
            self.supervisor.step(1000)   # brief pause so the label is visible
            self._end_match()
            return False

        return True

    # =================================================================
    # SAVE / EXPORT
    # =================================================================
    def _save_results_json(self):
        """Write a plain-text JSON so the data is human-readable."""
        self.match_data["boxes_collected"] = self.collected_boxes
        self.match_data["score"] = {
            "red":    self.red_boxes,
            "yellow": self.yellow_boxes,
            "purple": self.purple_boxes,
            "total":  self.collected_boxes,
        }
        with open("match_results.json", "w") as f:
            json.dump(self.match_data, f, indent=4)
        print("match_results.json saved (human-readable).")

    def _save_encrypted_bin(self):
        """Encrypt match_results.json → match_data.bin using RSA + AES-EAX."""
        recipient_key = RSA.import_key(open("public.pem", "rb").read())
        session_key   = get_random_bytes(16)

        enc_session_key = PKCS1_OAEP.new(recipient_key).encrypt(session_key)

        cipher_aes = AES.new(session_key, AES.MODE_EAX)
        with open("match_results.json", "rb") as f:
            data = f.read()

        ciphertext, tag = cipher_aes.encrypt_and_digest(data)

        with open("match_data.bin", "wb") as f:
            f.write(enc_session_key)
            f.write(cipher_aes.nonce)
            f.write(tag)
            f.write(ciphertext)

        print("match_data.bin saved (encrypted).")

    def _save_zip(self):
        """Bundle the encrypted bin, student controller, and public key."""
        self._save_results_json()   # always write JSON first
        self._save_encrypted_bin()  # then encrypt it

        zip_name = "../../Submission.zip"
        files_to_zip = [
            ("match_data.bin",      "match_data.bin"),
            ("match_results.json",  "match_results.json"),   # readable copy inside zip too
            ("../e-puck/e-puck.py", "e-puck.py"),
            ("public.pem",          "public.pem"),
        ]

        with ZipFile(zip_name, "w") as zipf:
            for src, arc in files_to_zip:
                if os.path.exists(src):
                    zipf.write(src, arc)
                else:
                    print(f"WARNING: {src} not found, skipping from zip.")

        print(f"ZIP created: {zip_name}")

    def _end_match(self):
        """Called once when the match finishes (time-up or all boxes done)."""
        if self.run_completed:
            return
        self.run_completed = True
        self._save_zip()

    # =================================================================
    # WORLD OBJECTS
    # =================================================================
    def _get_robot(self):
        self.robot = self.supervisor.getFromDef("EPUCK")
        self.robot_translation = self.robot.getField("translation")
        self.robot_rotation    = self.robot.getField("rotation")

    def _get_boxes(self):
        self.boxes = []
        print("\n--- Scanning scene for boxes ---")
        for angle in ANGLES:
            def_name = f"BOX_{angle}"
            node = self.supervisor.getFromDef(def_name)
            if node is None:
                print(f"ERROR: DEF '{def_name}' not found.")
                continue
            translation_field = node.getField("translation")
            if translation_field is None:
                print(f"WARNING: '{def_name}' has no translation field.")
                continue
            self.boxes.append({
                "node":   node,
                "field":  translation_field,
                "angle":  angle,
                "color":  None,
                "active": True,
            })
        print(f"Linked {len(self.boxes)} / {TOTAL_BOXES} boxes.\n")

    def _get_waypoints(self):
        self.red_wp    = self.supervisor.getFromDef("RedWaypoint")
        self.yellow_wp = self.supervisor.getFromDef("YellowWaypoint")
        self.purple_wp = self.supervisor.getFromDef("PurpleWaypoint")

        self.red_field    = self.red_wp.getField("translation")
        self.yellow_field = self.yellow_wp.getField("translation")
        self.purple_field = self.purple_wp.getField("translation")

        self._hide_waypoints()

    def _spawn_boxes(self):
        available_colors = ["RED", "YELLOW", "PURPLE"]
        while len(available_colors) < len(self.boxes):
            available_colors.append(random.choice(["RED", "YELLOW", "PURPLE"]))
        random.shuffle(available_colors)

        for i, box in enumerate(self.boxes):
            theta = math.radians(box["angle"])
            x = self.center_x + BOX_RADIUS * math.cos(theta)
            y = self.center_y + BOX_RADIUS * math.sin(theta)

            box["field"].setSFVec3f([x, y, self.center_z])

            color = available_colors[i]
            box["color"]  = color
            box["active"] = True
            self._set_box_color(box["node"], COLOR_MAP[color])

            self.match_data["spawned_boxes"].append({
                "angle":    box["angle"],
                "color":    color,
                "position": [x, y],
            })
            print(f"BOX {box['angle']:>3}° -> {color}")

        self.supervisor.simulationResetPhysics()
        print("Boxes spawned.\n")

    def _set_box_color(self, box_node, rgb):
        shape_node = box_node.getField("children").getMFNode(0)
        appearance = shape_node.getField("appearance").getSFNode()
        appearance.getField("baseColor").setSFColor(rgb)

    # =================================================================
    # WAYPOINT CONTROL
    # =================================================================
    def _hide_waypoints(self):
        for field in (self.red_field, self.yellow_field, self.purple_field):
            field.setSFVec3f([0, -5, -1])

    def _show_waypoints_for_box(self, angle):
        theta  = math.radians(angle)
        wp_z   = self.center_z - 0.05

        self.red_field.setSFVec3f([
            self.center_x + RED_RADIUS    * math.cos(theta),
            self.center_y + RED_RADIUS    * math.sin(theta),
            wp_z,
        ])
        self.yellow_field.setSFVec3f([
            self.center_x + YELLOW_RADIUS * math.cos(theta),
            self.center_y + YELLOW_RADIUS * math.sin(theta),
            wp_z,
        ])
        self.purple_field.setSFVec3f([
            self.center_x + PURPLE_RADIUS * math.cos(theta),
            self.center_y + PURPLE_RADIUS * math.sin(theta),
            wp_z,
        ])

    def _get_active_waypoints(self):
        theta = math.radians(self.active_box["angle"])
        return {
            "RED":    (self.center_x + RED_RADIUS    * math.cos(theta),
                       self.center_y + RED_RADIUS    * math.sin(theta)),
            "YELLOW": (self.center_x + YELLOW_RADIUS * math.cos(theta),
                       self.center_y + YELLOW_RADIUS * math.sin(theta)),
            "PURPLE": (self.center_x + PURPLE_RADIUS * math.cos(theta),
                       self.center_y + PURPLE_RADIUS * math.sin(theta)),
        }

    # =================================================================
    # MATCH FLOW
    # =================================================================
    def _activate_next_box(self):
        if self.current_index >= TOTAL_BOXES:
            return

        base_box         = self.boxes[self.current_index]
        self.active_box  = dict(base_box)

        self.active_box["required_path"]   = PATH_REQUIREMENTS[self.active_box["color"]][:]
        self.active_box["path_index"]      = 0
        self.active_box["consumed"]        = {"RED": False, "YELLOW": False, "PURPLE": False}
        self.active_box["hits"]            = []
        self.active_box["invalid"]         = False
        self.active_box["wrong_touch"]     = None
        self.active_box["completed_path"]  = False
        self.active_box["finalized"]       = False

        self._show_waypoints_for_box(self.active_box["angle"])
        self.state = "GO_TO_WAYPOINT"
        print(f"Active box -> angle {self.active_box['angle']}° | color {self.active_box['color']}")

    def _consume_waypoint(self, color):
        if self.active_box is None or self.active_box["finalized"]:
            return
        if self.active_box["path_index"] >= len(self.active_box["required_path"]):
            return
        if self.active_box["consumed"][color]:
            return

        expected = self.active_box["required_path"][self.active_box["path_index"]]
        if color != expected:
            self.active_box["invalid"]      = True
            self.active_box["wrong_touch"]  = color
            self.state = "RETURN_HOME"
            print(f"INVALID TOUCH: expected {expected}, got {color}")
            return

        self.active_box["consumed"][color] = True
        self.active_box["hits"].append(color)
        self.active_box["path_index"] += 1

        if self.active_box["path_index"] >= len(self.active_box["required_path"]):
            self.active_box["completed_path"] = True
            self.state = "RETURN_HOME"

    def _finalize_box(self, success):
        if self.active_box is None or self.active_box["finalized"]:
            return

        self.active_box["finalized"] = True

        result = {
            "angle":         self.active_box["angle"],
            "color":         self.active_box["color"],
            "required_path": self.active_box["required_path"][:],
            "hits":          self.active_box["hits"][:],
            "valid":         bool(success),
            "wrong_touch":   self.active_box["wrong_touch"],
        }
        self.match_data["box_results"].append(result)

        if success:
            self.collected_boxes += 1
            c = self.active_box["color"]
            if c == "RED":
                self.red_boxes    += 1
            elif c == "YELLOW":
                self.yellow_boxes += 1
            elif c == "PURPLE":
                self.purple_boxes += 1
            print(f"VALID  BOX: {c} at {self.active_box['angle']}°")
        else:
            print(f"FAILED BOX: {self.active_box['color']} at {self.active_box['angle']}°")

        # Push the box off-screen
        pos = self.active_box["field"].getSFVec3f()
        self.active_box["field"].setSFVec3f([pos[0], 10, -1])

        self._hide_waypoints()
        self.current_index     += 1
        self.active_box         = None
        self.state              = "WAIT_DETECTION"
        self.last_waypoint_touch = None

    # =================================================================
    # MONITORS
    # =================================================================
    def _monitor_waypoint(self):
        if (self.active_box is None
                or self.state != "GO_TO_WAYPOINT"
                or self.active_box["invalid"]):
            return

        robot       = self.robot_translation.getSFVec3f()
        wp          = self._get_active_waypoints()
        current_touch = None

        for color in ("RED", "YELLOW", "PURPLE"):
            dx   = robot[0] - wp[color][0]
            dy   = robot[1] - wp[color][1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist < COLLECTION_THRESHOLD:
                current_touch = color
                break

        if current_touch is None:
            self.last_waypoint_touch = None
            return

        if current_touch == self.last_waypoint_touch:
            return                              # debounce: same waypoint still touching

        self.last_waypoint_touch = current_touch

        if self.active_box["path_index"] >= len(self.active_box["required_path"]):
            self.active_box["invalid"]     = True
            self.active_box["wrong_touch"] = current_touch
            self.state = "RETURN_HOME"
            print(f"EXTRA WAYPOINT TOUCH: {current_touch}")
            return

        expected = self.active_box["required_path"][self.active_box["path_index"]]
        if current_touch == expected:
            self._consume_waypoint(current_touch)
        else:
            self.active_box["invalid"]     = True
            self.active_box["wrong_touch"] = current_touch
            self.state = "RETURN_HOME"
            print(f"INVALID TOUCH: got {current_touch}, expected {expected}")

    def _monitor_home(self):
        if self.active_box is None or self.state != "RETURN_HOME":
            return

        pos  = self.robot_translation.getSFVec3f()
        dx   = pos[0] - self.center_x
        dy   = pos[1] - self.center_y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist < HOME_THRESHOLD:
            print("Home reached.")
            success = (
                not self.active_box["invalid"]
                and self.active_box["path_index"] == len(self.active_box["required_path"])
            )
            self._finalize_box(success)

    # =================================================================
    # HUD
    # =================================================================
    def _update_labels(self):
        remaining = max(0.0, self.match_time - self.supervisor.getTime())

        self.supervisor.setLabel(0, f"Time Left : {remaining:.1f}s",             0.01, 0.01, FONT_SIZE, 0x000000, 0.0, "Arial")
        self.supervisor.setLabel(1, f"Collected : {self.collected_boxes}/{TOTAL_BOXES}", 0.01, 0.06, FONT_SIZE, 0x000000, 0.0, "Arial")
        self.supervisor.setLabel(2, f"State     : {self.state}",                  0.01, 0.12, FONT_SIZE, 0x000000, 0.0, "Arial")
        self.supervisor.setLabel(3, f"Red    : {self.red_boxes}",                 0.01, 0.18, FONT_SIZE, 0xFF0000, 0.0, "Arial")
        self.supervisor.setLabel(4, f"Yellow : {self.yellow_boxes}",              0.01, 0.24, FONT_SIZE, 0xCCCC00, 0.0, "Arial")
        self.supervisor.setLabel(5, f"Purple : {self.purple_boxes}",              0.01, 0.30, FONT_SIZE, 0x800080, 0.0, "Arial")

        if self.active_box is not None:
            path_text = " -> ".join(self.active_box["required_path"])
            progress  = f"{self.active_box['path_index']}/{len(self.active_box['required_path'])}"
            self.supervisor.setLabel(
                6,
                f"Active: {self.active_box['color']} | Path: {path_text} | {progress}",
                0.01, 0.36, FONT_SIZE, 0x444444, 0.0, "Arial",
            )
        else:
            self.supervisor.setLabel(6, "Active: None", 0.01, 0.36, FONT_SIZE, 0x444444, 0.0, "Arial")