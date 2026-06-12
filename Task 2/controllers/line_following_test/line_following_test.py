
    
    
    
    
    
    
from controller import Robot, DistanceSensor, Motor
import cv2
import numpy as np
import json

#-------------------------------------------------------
# Initialize variables

TIME_STEP = 64
# Define these outside your while loop (near top of script)
MAX_SPEED = 6.28
Kp = 0.024 # Proportional tuning parameter (Start small!)
base_speed = 1* MAX_SPEED # Forward cruise speed

# create the Robot instance.
robot = Robot()
    
# get the time step of the current world.
timestep = int(robot.getBasicTimeStep())   # [ms]

#-------------------------------------------------------
# Initialize devices

# ground sensors
gs = []
gsNames = ['gs0', 'gs1', 'gs2'] # Left Middle Right
for i in range(3):
    gs.append(robot.getDevice(gsNames[i]))
    gs[i].enable(timestep)
    
# Camera
camera = robot.getDevice("camera")
camera.enable(timestep)

# Emitter(keep as it is)
emitter = robot.getDevice("emitter")

# receiver = robot.getDevice("receiver")
# receiver.enable(timestep)

visited_routes = []
previous_route = "UNKNOWN"
mission_sent = False
# submit_permission = False
visited_route_order = []

# motors    
leftMotor = robot.getDevice('left wheel motor')
rightMotor = robot.getDevice('right wheel motor')
leftMotor.setPosition(float('inf'))
rightMotor.setPosition(float('inf'))
leftMotor.setVelocity(0.0)
rightMotor.setVelocity(0.0)

RED_LOWER   = np.array([171, 127, 61])
RED_UPPER   = np.array([179, 218, 255])

GREEN_LOWER = np.array([77, 82, 235])
GREEN_UPPER = np.array([78, 144, 255])

BLUE_LOWER  = np.array([102, 148, 227])
BLUE_UPPER  = np.array([103, 169, 255])

WHITE_LOWER = np.array([0, 0, 180])
WHITE_UPPER = np.array([179, 50, 255])

def detect_route_color():

    raw = camera.getImage()

    if raw is None:
        return "UNKNOWN"

    image = np.frombuffer(
        raw,
        np.uint8
    ).reshape(
        (camera.getHeight(),
         camera.getWidth(),
         4)
    )

    frame = cv2.cvtColor(
        image,
        cv2.COLOR_BGRA2BGR
    )

    hsv = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2HSV
    )

    # color mask
    red_mask = cv2.inRange(
    hsv,
    RED_LOWER,
    RED_UPPER
    )
    
    green_mask = cv2.inRange(
        hsv,
        GREEN_LOWER,
        GREEN_UPPER
    )
    
    blue_mask = cv2.inRange(
        hsv,
        BLUE_LOWER,
        BLUE_UPPER
    )
    
    white_mask = cv2.inRange(
        hsv,
        WHITE_LOWER,
        WHITE_UPPER
    )

    red_pixels = cv2.countNonZero(red_mask)
    green_pixels = cv2.countNonZero(green_mask)
    blue_pixels = cv2.countNonZero(blue_mask)
    white_pixels = cv2.countNonZero(white_mask)

    threshold = 80000
    
    # cv2.imshow(
        # "Corridor Detection",
        # frame 
    # )
    
    cv2.waitKey(1)

    if red_pixels > threshold and \
       red_pixels > green_pixels and \
       red_pixels > blue_pixels:
        return "RED"

    elif green_pixels > threshold and \
         green_pixels > red_pixels and \
         green_pixels > blue_pixels:
        return "GREEN"

    elif blue_pixels > threshold and \
         blue_pixels > red_pixels and \
         blue_pixels > green_pixels:
        return "BLUE"
        
    elif white_pixels > threshold and \
         white_pixels > red_pixels and \
         white_pixels > green_pixels and \
         white_pixels > blue_pixels:
        return "WHITE"

    return "UNKNOWN"

#-------------------------------------------------------
# Main loop:
# - perform simulation steps until Webots is stopping the controller
while robot.step(timestep) != -1:
    # Update sensor readings

    gsValues = []
    for i in range(3):
        gsValues.append(gs[i].getValue())
    # value = gsValues.getValue()
    # print(gsValues)

    current_route = detect_route_color()

    if current_route != previous_route:
    
        if current_route in ["RED","GREEN","BLUE", "WHITE"]:
        
            if current_route not in visited_routes:
    
                print(
                    f"Entering into {current_route} Corridor"
                )

                visited_routes.append(current_route)
            
            
                # sample event call(keep format)
                
    
        previous_route = current_route

    if (
        "RED" in visited_routes and
        "GREEN" in visited_routes and
        "BLUE" in visited_routes and
        "WHITE" in visited_routes
    ):
    
        # print(visited_routes)
        
        # sample event call(keep format)
        emitter.send(
            json.dumps(visited_routes).encode("utf-8"))
        # mission_sent = True
        
        # leftMotor.setVelocity(0.0)
        # rightMotor.setVelocity(0.0)
    
        # print("MISSION COMPLETE")
        # break

    # If left sensor sees white (high) and right sees black (low), error is positive -> turn right.
    error = - gsValues[2] + gsValues[0] 
    
    # 2. Calculate Proportional Term
    P = Kp * error
    
    # 3. Apply to Motor Speeds
    # Subtracting P from left and adding to right steers the robot toward the line
    leftSpeed = base_speed + P
    rightSpeed = base_speed - P
    
    # 4. Clamp Speeds (Crucial for Webots)
    # Prevents speeds from exceeding physical limits and throwing Webots warnings
    leftSpeed = max(min(leftSpeed, MAX_SPEED), -MAX_SPEED)
    rightSpeed = max(min(rightSpeed, MAX_SPEED), -MAX_SPEED)
    
    leftMotor.setVelocity(leftSpeed)
    rightMotor.setVelocity(rightSpeed)