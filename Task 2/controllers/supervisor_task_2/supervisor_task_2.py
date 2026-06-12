from controller import Supervisor # type: ignore
import sys
import json
import math
import random 
import os

from Crypto.PublicKey import RSA
from Crypto.Random import get_random_bytes
from Crypto.Cipher import AES, PKCS1_OAEP
from zipfile import ZipFile

pi = math.pi
MAX_TIME = 150
tolerance = 0.06
FONT_SIZE = 0.08


class Supervisor_Controller:
    def __init__(self, supervisor):
        print("Initializing Test Supervisor!")
        self.supervisor = supervisor
        self.remaining_time = MAX_TIME
        self.waypoints_reached = 0
        self.run_completed = False
        self.waypoints = []
        
        self.continuous_trajectory = []
        self.waypoint_times = []
        self.color_order = []
        self.ground_truth_sequence = []

        self.get_robot_fields()
        self.get_waypoint_fields()
        self.get_team_info()
        self.init_waypoints()
        self.randomize_unique_path_colors()
        self.update_waypoint(self.waypoints.pop(0))
        self.prev_position = None
        self.teleport_violations = 0
        self.max_violations = 1
        # 5 cm per timestep is extremely generous for an e-puck
        self.allowed_jump_distance = 0.05

        self.receiver = self.supervisor.getDevice('receiver')
        if self.receiver:
            self.receiver.enable(int(self.supervisor.getBasicTimeStep()))


    def check_teleportation(self):
        bot_pos = self.translation_field_robot.getSFVec3f()

        curr_x = bot_pos[0]
        curr_y = bot_pos[1]

        # First reading
        if self.prev_position is None:
            self.prev_position = [curr_x, curr_y]
            return False

        dx = curr_x - self.prev_position[0]
        dy = curr_y - self.prev_position[1]

        distance = math.sqrt(dx * dx + dy * dy)

        # Update previous position
        self.prev_position = [curr_x, curr_y]

        if distance > self.allowed_jump_distance:
            print(
                f"[SECURITY] Impossible movement detected! "
                f"Jump distance = {distance:.3f} m"
            )

            self.teleport_violations += 1

            return True

        return False
    
    def randomize_unique_path_colors(self):
        color_pool = [
            {"rgb": [0.101, 0.3725, 0.705], "name": "BLUE"},
            {"rgb": [1.0, 1.0, 1.0],        "name": "WHITE"},
            {"rgb": [0.34, 0.89, 0.53],     "name": "GREEN"},
            {"rgb": [0.64, 0.11, 0.17],     "name": "RED"}
        ]
        
        zone_defs = ['Zone_1', 'Zone_2', 'Zone_3', 'Zone_4']
        selected = random.sample(color_pool, len(zone_defs))
        
        for i, zone_name in enumerate(zone_defs):
            zone_node = self.supervisor.getFromDef(zone_name)
            if zone_node is None:
                print(f"Supervisor Warning: Could not find '{zone_name}'")
                continue
            
            children_field = zone_node.getField('children')
            if children_field is None:
                print(f"Supervisor Warning: No children field in '{zone_name}'")
                continue
            
            shape_node = None
            for j in range(children_field.getCount()):
                child = children_field.getMFNode(j)
                if child is not None and child.getTypeName() == 'Shape':
                    shape_node = child
                    break
            
            if shape_node is None:
                print(f"Supervisor Warning: No Shape child found in '{zone_name}'")
                continue
            
            appearance_field = shape_node.getField('appearance')
            if appearance_field is None:
                print(f"Supervisor Warning: No appearance field in Shape of '{zone_name}'")
                continue
            
            appearance = appearance_field.getSFNode()
            if appearance is None:
                print(f"Supervisor Warning: Null appearance node in '{zone_name}'")
                continue
            
            base_color_field = appearance.getField('baseColor')
            if base_color_field:
                base_color_field.setSFColor(selected[i]["rgb"])
                self.ground_truth_sequence.append(selected[i]["name"])
        
        print(f"MASTER ANSWER KEY GENERATED: {self.ground_truth_sequence}")


    def get_team_info(self):
        try:
            with open('../../teaminfo.json') as team_file:
                self.team_info = json.load(team_file)
                self.team_id = self.team_info['team_id']
        except:
            self.supervisor.simulationSetMode(Supervisor.SIMULATION_MODE_PAUSE)
            raise Exception("teaminfo.json missing") from None


    def get_waypoint_fields(self):
        self.waypoint = self.supervisor.getFromDef("waypoint")
        self.translation_field_waypoint = self.waypoint.getField("translation")


    def get_robot_fields(self):
        self.robot = self.supervisor.getFromDef("my-e-puck")
        self.translation_field_robot = self.robot.getField("translation")

    
    def update_remaining_time(self, time):
        self.remaining_time = MAX_TIME - time
        return self.remaining_time

    
    def check_remaining_time(self):
        return self.remaining_time <= 0

        
    def update_robot_location(self):
        self.robot_location = self.robot.getField("translation").getSFVec3f()
        return self.robot_location

    
    def update_waypoint(self, new_position):
        self.translation_field_waypoint.setSFVec3f(new_position)
        self.waypoint_location = new_position
        return self.waypoint_location


    def check_waypoint_reached(self):
        if (abs(self.robot_location[0] - self.waypoint_location[0]) < tolerance and 
            abs(self.robot_location[1] - self.waypoint_location[1]) < tolerance): 
            self.waypoints_reached += 1
            return True
        return False

        
    def check_collision(self):
        for x in self.robot.getContactPoints():
            if x.point[2] > 0.02:
                return True
        return False

    
    def save_coordinates_file(self, data):
        current_dir = os.path.dirname(os.path.abspath(__file__))
        key_path = os.path.join(current_dir, "public.pem")
        with open("coordinates.bin", "wb") as myfile:
            public_key = RSA.import_key(open(key_path).read())
            temp_aes_key = get_random_bytes(16)
            enc_session_key = PKCS1_OAEP.new(public_key).encrypt(temp_aes_key)
            cipher_aes = AES.new(temp_aes_key, AES.MODE_EAX)
            ciphertext, tag = cipher_aes.encrypt_and_digest(json.dumps(data).encode('utf8'))
            [myfile.write(x) for x in (enc_session_key, cipher_aes.nonce, tag, ciphertext)]


    def save_zip_file(self):
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # ── FIND YOUR ROBOT CONTROLLER ──────────────────────────────────────
        # Update this folder name to match your actual controller folder name.
        # Check what's inside: Draft Sample Task 2/controllers/
        robot_controller_path = os.path.join(
            current_dir, '..', 'line_following_test', 'line_following_test.py'
        )

        if not os.path.exists(robot_controller_path):
            print(f"[ERROR] Robot controller not found at:\n  {robot_controller_path}")
            print("[ERROR] Update 'robot_controller_path' in save_zip_file() to the correct path.")
            print("[WARNING] Skipping zip creation. Simulation will still pause correctly.")
            return  # ← graceful skip, does NOT crash the simulation

        zip_path = os.path.join(current_dir, '..', '..', self.team_id + "_Task5B" + ".zip")
        with ZipFile(zip_path, 'w') as myzip:
            myzip.write('coordinates.bin')
            myzip.write(robot_controller_path, 'e-puck.py')
            myzip.write('../../teaminfo.json', 'team_info.json')
        
        print(f"[INFO] Zip saved at: {zip_path}")


    def update_robot_info(self, LABEL_ID):
        display_message = f"Remaining time: {self.remaining_time:5.1f} s   Waypoints: {self.waypoints_reached}"
        self.supervisor.setLabel(LABEL_ID, display_message, 0.01, 0.01, FONT_SIZE, 0x000000, 0.0, "Verdana")


    def init_waypoints(self):
        self.waypoints += [
            [-0.08, 1.105, 0.03], [0.79, 1.105, 0.03], [1, 0.895, 0.03],
            [1, 0.405, 0.03], 
            [0.81, 0.205, 0.03], [0.3, 0.205, 0.03],[0.1, 0.535, 0.03], 
            [-0.18, 0.855, 0.03], [-1.23, -0.045, 0.03],[-0.48, -0.885, 0.03], [-0.11, -0.885, 0.03], 
            [0.1, -0.705, 0.03],[0.67, -0.115, 0.03], [1.25, -0.645, 0.03], [1.25, -1.135, 0.03]
        ]
        return self.waypoints


    def check_and_update(self):
    # Listen for color messages from robot
        while self.receiver and self.receiver.getQueueLength() > 0:
            msg = self.receiver.getString()
            try:
                decoded_list = json.loads(msg)
                self.color_order = decoded_list
            except json.JSONDecodeError:
                pass
            self.receiver.nextPacket()

        if not self.run_completed:
            current_loc = self.update_robot_location()
            current_time = self.update_remaining_time(self.supervisor.getTime())

            self.continuous_trajectory.append(list(current_loc))
            self.update_robot_info(LABEL_ID=1)

            # ── Check waypoints FIRST ──────────────────────────────────────────
            if self.check_waypoint_reached():
                self.waypoint_times.append(current_time)
                print(f"[INFO] Waypoint {self.waypoints_reached} reached. Time remaining: {current_time:.1f}s")

                if self.waypoints:
                    self.update_waypoint(self.waypoints.pop(0))
                else:
                    # All 15 waypoints done — end immediately
                    print("[INFO] All waypoints reached! Saving and pausing.")
                    self.run_completed = True
                    self._finish()
                    return False  # ← break the main loop right now

            # ── Then check termination conditions ─────────────────────────────
            elif self.check_teleportation():
                self.supervisor.setLabel(5,"SECURITY VIOLATION: Robot position modified!",0,0.3,0.1,0xFF0000,0.0,"Arial")
                print("Run Invalidated.")
                self._finish()
                return False
            
            elif self.check_collision():
                print("[INFO] Collision detected. Saving and pausing.")
                self.run_completed = True
                self._finish()
                return False

            elif self.check_remaining_time():
                print("[INFO] Time limit reached. Saving and pausing.")
                self.run_completed = True
                self._finish()
                return False

        return True


    def _finish(self):
        """Save data, zip, and pause the simulation."""
        final_data = {
            "continuous_trajectory": self.continuous_trajectory,
            "waypoint_times": self.waypoint_times,
            "color_order": self.color_order,
            "ground_truth_sequence": self.ground_truth_sequence,
            "final_time":self.supervisor.getTime()
        }

        # Write plain JSON for verification
        current_dir = os.path.dirname(os.path.abspath(__file__))
        verify_path = os.path.join(current_dir, "verification_data.json")
        with open(verify_path, "w") as json_file:
            json.dump(final_data, json_file, indent=4)
        print(f"[INFO] Plain JSON saved at: {verify_path}")

        # Save encrypted + zip
        try:
            self.save_coordinates_file(final_data)
            self.save_zip_file()
        except Exception as e:
            print(f"[ERROR] During save: {e}")

        # Pause — no label shown
        self.supervisor.simulationSetMode(Supervisor.SIMULATION_MODE_PAUSE)
        print("[INFO] Simulation paused.")


supervisor = Supervisor()
my_controller = Supervisor_Controller(supervisor)
timestep = int(supervisor.getBasicTimeStep())


while supervisor.step(timestep) != -1:
    if not my_controller.run_completed:
        my_controller.check_and_update()


# from controller import Supervisor # type: ignore
# import json
# import random 
# import os

# from Crypto.PublicKey import RSA
# from Crypto.Random import get_random_bytes
# from Crypto.Cipher import AES, PKCS1_OAEP
# from zipfile import ZipFile

# MAX_TIME = 180
# tolerance = 0.06
# FONT_SIZE = 0.08

# class Supervisor_Controller:
#     def __init__(self, supervisor):
#         print("Initializing Evaluation Supervisor Controller!")
#         self.supervisor = supervisor
#         self.remaining_time = MAX_TIME
#         self.waypoints_reached = 0
#         self.run_completed = False
#         self.all_waypoints_cleared = False # Flag to know path is done
#         self.waypoints = []

#         # Data collection

#         self.student_submitted_colors = []
#         self.ground_truth_sequence = []  # Holds the correct sequence of zones

#         self.get_robot_fields()
#         self.get_waypoint_fields()
#         self.get_team_info()
#         self.init_waypoints()
#         self.update_waypoint(self.waypoints.pop(0))

#         # Initialize Receiver
#         self.receiver = self.supervisor.getDevice('receiver')
#         if self.receiver:
#             self.receiver.enable(int(self.supervisor.getBasicTimeStep()))
        
#         # Randomize zones and lock in the master answer key
#         self.randomize_unique_path_colors()

#     def randomize_unique_path_colors(self):
#         color_pool = [
#             {"rgb": [0.101, 0.3725, 0.705], "name": "BLUE"},
#             {"rgb": [1.0, 1.0, 1.0],        "name": "WHITE"},
#             {"rgb": [0.34, 0.89, 0.53],     "name": "GREEN"},
#             {"rgb": [0.64, 0.11, 0.17],     "name": "RED"}
#         ]
        
#         zone_defs = ['Zone_1', 'Zone_2', 'Zone_3', 'Zone_4']
#         selected = random.sample(color_pool, len(zone_defs))
        
#         for i, zone_name in enumerate(zone_defs):
#             zone_node = self.supervisor.getFromDef(zone_name)
#             if zone_node is None:
#                 print(f"Supervisor Warning: Could not find '{zone_name}'")
#                 continue
            
#             children_field = zone_node.getField('children')
#             if children_field is None:
#                 print(f"Supervisor Warning: No children field in '{zone_name}'")
#                 continue
            
#             shape_node = None
#             for j in range(children_field.getCount()):
#                 child = children_field.getMFNode(j)
#                 if child is not None and child.getTypeName() == 'Shape':
#                     shape_node = child
#                     break
            
#             if shape_node is None:
#                 print(f"Supervisor Warning: No Shape child found in '{zone_name}'")
#                 continue
            
#             appearance_field = shape_node.getField('appearance')
#             if appearance_field is None:
#                 print(f"Supervisor Warning: No appearance field in Shape of '{zone_name}'")
#                 continue
            
#             appearance = appearance_field.getSFNode()
#             if appearance is None:
#                 print(f"Supervisor Warning: Null appearance node in '{zone_name}'")
#                 continue
            
#             base_color_field = appearance.getField('baseColor')
#             if base_color_field:
#                 base_color_field.setSFColor(selected[i]["rgb"])
#                 self.ground_truth_sequence.append(selected[i]["name"])
        
#         print(f"MASTER ANSWER KEY GENERATED: {self.ground_truth_sequence}")

#     # --- e-Yantra Required Methods ---
#     def get_team_info(self):
#         try:
#             with open('../../teaminfo.json') as team_file:
#                 self.team_info = json.load(team_file)
#                 self.team_id = self.team_info['team_id']
#         except:
#             self.supervisor.simulationSetMode(Supervisor.SIMULATION_MODE_PAUSE)
#             raise Exception("teaminfo.json missing") from None

#     def get_waypoint_fields(self):
#         self.waypoint = self.supervisor.getFromDef("waypoint")
#         self.translation_field_waypoint = self.waypoint.getField("translation")

#     def get_robot_fields(self):
#         self.robot = self.supervisor.getFromDef("my-e-puck")
#         # self.translation_field_robot = self.robot.getField("translation")
    
#     def update_remaining_time(self, time):
#         self.remaining_time = MAX_TIME - time
#         return self.remaining_time
    
#     def check_remaining_time(self):
#         return self.remaining_time <= 0
        
#     def update_robot_location(self):
#         self.robot_location = self.robot.getField("translation").getSFVec3f()
#         return self.robot_location
    
#     def update_waypoint(self, new_position):
#         self.translation_field_waypoint.setSFVec3f(new_position)
#         self.waypoint_location = new_position
#         return self.waypoint_location 

#     def check_waypoint_reached(self):
#         if (abs(self.robot_location[0] - self.waypoint_location[0]) < tolerance and 
#             abs(self.robot_location[1] - self.waypoint_location[1]) < tolerance): 
#             self.waypoints_reached += 1
#             return True
#         return False
        
#     def check_collision(self):
#         for x in self.robot.getContactPoints():
#             if x.point[2] > 0.02: return True
#         return False
    
#     def save_coordinates_file(self, data):
#         current_dir = os.path.dirname(os.path.abspath(__file__))
#         key_path = os.path.join(current_dir, "public.pem")
#         with open("coordinates.bin", "wb") as myfile: 
#             public_key = RSA.import_key(open(key_path).read()) 
#             temp_aes_key = get_random_bytes(16) 
#             enc_session_key = PKCS1_OAEP.new(public_key).encrypt(temp_aes_key) 
#             cipher_aes = AES.new(temp_aes_key, AES.MODE_EAX) 
#             ciphertext, tag = cipher_aes.encrypt_and_digest(json.dumps(data).encode('utf8')) 
#             [myfile.write(x) for x in (enc_session_key, cipher_aes.nonce, tag, ciphertext)] 

#     def save_zip_file(self):
#         current_dir = os.path.dirname(os.path.abspath(__file__))
#         robot_controller_path = os.path.join(current_dir, '..', 'line_following_test', 'line_following_test.py')
#         with ZipFile("../../" + self.team_id + "_Task2" + ".zip", 'w') as myzip: 
#             myzip.write('coordinates.bin') 
#             myzip.write(robot_controller_path, 'e-puck.py') 
#             myzip.write('../../teaminfo.json', 'team_info.json') 

#     def update_robot_info(self, LABEL_ID):
#         display_message = f"Remaining time: {self.remaining_time:5.1f} s   Waypoints: {self.waypoints_reached}"
#         self.supervisor.setLabel(LABEL_ID, display_message, 0.01, 0.01, FONT_SIZE, 0x000000, 0.0, "Verdana")

#     def init_waypoints(self):
#         self.waypoints += [
#             [-1.09, 0.905, 0.03], [-0.6, 0.905, 0.03], [0.0, 0.905, 0.03],
#             [0.199, 0.715, 0.03], [0.199, 0.505, 0.03], [0.199, 0.285, 0.03],
#             [0.0, 0.005, 0.03], [-0.5, 0.005, 0.03], [-0.7, 0.285, 0.03],
#             [-0.71, 0.495, 0.03], [-1.12, 0.665, 0.03], [-2.02, -0.265, 0.03],
#             [-0.9, -1.095, 0.03], [-0.09, -0.325, 0.03], [0.45, -1.215, 0.03]
#         ]
#         return self.waypoints 

#     def check_and_update(self):
#         # Check for student submissions
#         while self.receiver and self.receiver.getQueueLength() > 0:

#             msg = self.receiver.getString()
        
#             try:
        
#                 received_list = json.loads(msg)
        
#                 if isinstance(received_list, list):

#                     if self.all_waypoints_cleared:
                
#                         self.student_submitted_colors = received_list
                
#                         print(
#                             "\n[EVALUATOR] Student Submission:"
#                         )
                
#                         print(
#                             self.student_submitted_colors
#                         )
                
#                         self.run_completed = True
        
#             except Exception as e:
        
#                 print(
#                     f"Receiver Error: {e}"
#                 )
        
#             self.receiver.nextPacket()

#         if not self.run_completed:
        
#             self.update_remaining_time(
#             self.supervisor.getTime()
#         )
    
#             self.update_robot_location()
        
#             self.update_robot_info(LABEL_ID=1)
            
#             # Fail conditions
#             if self.check_collision() or self.check_remaining_time():
            
#                 self.student_submitted_colors = []

#                 self.run_completed = True
                
#             if self.check_waypoint_reached():
               
#                 if self.waypoints: 
#                     self.update_waypoint(self.waypoints.pop(0))
#                 else:
#                     if not self.all_waypoints_cleared:
                
#                         print(
#                             "[EVALUATOR] Final Waypoint Reached"
#                         )
                
#                         self.all_waypoints_cleared = True
                
#         else:

#             # Package up the report card
#             final_data_package = {

#                 "ground_truth_sequence":
#                     self.ground_truth_sequence,
            
#                 "route_order":
#                     self.student_submitted_colors,
            
#                 "corridors_verified":
#                     self.student_submitted_colors,
            
#                 "waypoints_collected":
#                     self.waypoints_reached,
            
#                 "final_time":
#                     self.supervisor.getTime(),
            
#                 "route_correct":
#                     (
#                         self.student_submitted_colors
#                         == self.ground_truth_sequence
#                     )
#             }
#             # Save the clean text file for manual grading verification
#             current_dir = os.path.dirname(os.path.abspath(__file__))
#             with open(os.path.join(current_dir, "debug_data.json"), "w") as debug_file:
#                 json.dump(final_data_package, debug_file, indent=4) 
                
#             print(f"[EVALUATOR] Verification finished. Zipping submission package.")
            
#             self.save_coordinates_file(final_data_package)
#             self.save_zip_file()
            
#             self.supervisor.simulationSetMode(
#                 Supervisor.SIMULATION_MODE_PAUSE
#                 )
                
#             return False
            
#         return True

# # Runner Block
# supervisor = Supervisor()
# my_controller = Supervisor_Controller(supervisor)
# timestep = int(supervisor.getBasicTimeStep())
# while supervisor.step(timestep) != -1:
#     if not my_controller.check_and_update():
#         break