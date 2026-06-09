from controller import Robot
import cv2
import numpy as np

# =========================================================
# ROBOT SETUP
# =========================================================
robot = Robot()
TIMESTEP = int(robot.getBasicTimeStep())

# =========================================================
# MOTORS
# =========================================================
leftMotor = robot.getDevice("left wheel motor")
rightMotor = robot.getDevice("right wheel motor")

leftMotor.setPosition(float('inf'))
rightMotor.setPosition(float('inf'))

leftMotor.setVelocity(0.0)
rightMotor.setVelocity(0.0)

# =========================================================
# CAMERA
# =========================================================
camera = robot.getDevice("camera")
camera.enable(TIMESTEP)
WIDTH = camera.getWidth()
HEIGHT = camera.getHeight()

# =========================================================
# ROTATION SETTINGS
# =========================================================
FULL_ROTATION_STEPS = 980
STEP_45 = FULL_ROTATION_STEPS // 32
ROTATE_SPEED = 1.2
FORWARD_SPEED = 4.8

# =========================================================
# WAYPOINT RADII
# =========================================================
RED_RADIUS = 0.2
YELLOW_RADIUS = 0.36
PURPLE_RADIUS = 0.56

# =========================================================
# CALIBRATION
# =========================================================
REFERENCE_RADIUS = 0.10
REFERENCE_STEPS = 49
STEPS_PER_METER = REFERENCE_STEPS / REFERENCE_RADIUS

def get_steps(color):
    if color == "RED":
        radius = RED_RADIUS
    elif color == "YELLOW":
        radius = YELLOW_RADIUS
    else:
        radius = PURPLE_RADIUS
    return int(radius * STEPS_PER_METER)

# =========================================================
# ANGLES
# =========================================================
ANGLES = [0, 45, 90, 135, 180, 225, 270, 315]

# =========================================================
# HSV RANGES
# =========================================================
RED_LOWER1 = np.array([0, 190, 170])
RED_UPPER1 = np.array([0, 255, 255])

YELLOW_LOWER = np.array([30, 200, 150])
YELLOW_UPPER = np.array([100, 255, 255])

PURPLE_LOWER = np.array([140, 150, 0])
PURPLE_UPPER = np.array([170, 255, 255])

# =========================================================
# STATES
# =========================================================
DETECT = 0
GO_FORWARD = 1
GO_BACK = 2
ROTATE = 3
DONE = 4

state = DETECT
last_state = None
last_angle_index = -1

# =========================================================
# VARIABLES
# =========================================================
angle_index = 0
rotate_counter = 0
move_counter = 0
detected_color = None

# =========================================================
# COUNTS
# =========================================================
red_count = 0
yellow_count = 0
purple_count = 0

# =========================================================
# WINDOW INITIALIZATION
# =========================================================
cv2.namedWindow("BOX DETECTION", cv2.WINDOW_NORMAL)
cv2.resizeWindow("BOX DETECTION", 1400, 1000)

# =========================================================
# STOP FUNCTION
# =========================================================
def stop():
    leftMotor.setVelocity(0.0)
    rightMotor.setVelocity(0.0)

# =========================================================
# DETECT COLOR
# =========================================================
def detect_color():
    global detected_color

    raw = camera.getImage()
    image = np.frombuffer(raw, np.uint8).reshape((HEIGHT, WIDTH, 4))
    frame = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Masks
    red_mask = cv2.inRange(hsv, RED_LOWER1, RED_UPPER1)
    yellow_mask = cv2.inRange(hsv, YELLOW_LOWER, YELLOW_UPPER)
    purple_mask = cv2.inRange(hsv, PURPLE_LOWER, PURPLE_UPPER)

    masks = [
        ("RED", red_mask, (0, 0, 255)),
        ("YELLOW", yellow_mask, (0, 255, 0)),
        ("PURPLE", purple_mask, (255, 0, 0))
    ]

    # Debug HSV Text
    center_hsv = hsv[HEIGHT // 2, WIDTH // 2]
    cv2.putText(
        frame,
        f"H:{center_hsv[0]} S:{center_hsv[1]} V:{center_hsv[2]}",
        (10, HEIGHT - 20),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2
    )

    found = False
    best_area = 0
    center_min = WIDTH // 2 - 60
    center_max = WIDTH // 2 + 60

    for color_name, mask, draw_color in masks:
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 500:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            cx = x + w // 2

            if cx < center_min or cx > center_max:
                continue

            if area > best_area:
                best_area = area
                detected_color = color_name
                found = True

                cv2.drawContours(frame, [cnt], -1, draw_color, 2)
                cv2.rectangle(frame, (x, y), (x + w, y + h), draw_color, 2)
                cv2.putText(
                    frame,
                    f"{color_name} A={int(area)}",
                    (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    draw_color,
                    2
                )

    # Render detection state to frame before displaying window
    if found:
        cv2.putText(frame, f"DETECTED: {detected_color}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)
    else:
        cv2.putText(frame, "DETECTED: NONE", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)

    cv2.imshow("BOX DETECTION", frame)
    cv2.waitKey(1)
    return found

# =========================================================
# MAIN LOOP
# =========================================================
while robot.step(TIMESTEP) != -1:

    if angle_index >= len(ANGLES):
        state = DONE

    # --- Clean Console Logger (Triggers only on state transitions) ---
    if state != last_state or (state == DETECT and angle_index != last_angle_index):
        print("================================")
        if state == DETECT:
            print(f"DETECTING @ {ANGLES[angle_index]}°")
        elif state == GO_FORWARD:
            print(f"GOING TO {detected_color}")
        elif state == GO_BACK:
            print("RETURNING HOME")
        elif state == ROTATE:
            target_angle = ANGLES[angle_index] if angle_index < len(ANGLES) else "END"
            print(f"ROTATING TO {target_angle}°")
        
        last_state = state
        if state == DETECT:
            last_angle_index = angle_index

    # =====================================================
    # STATE MACHINE EXECUTION
    # =====================================================
    if state == DETECT:
        found = detect_color()
        stop()

        if found:
            print(f"FOUND: {detected_color}")
            move_counter = 0
            state = GO_FORWARD

    elif state == GO_FORWARD:
        leftMotor.setVelocity(FORWARD_SPEED)
        rightMotor.setVelocity(FORWARD_SPEED)
        move_counter += 1

        target_steps = get_steps(detected_color)

        if move_counter >= target_steps:
            stop()

            if detected_color == "RED":
                red_count += 1
            elif detected_color == "YELLOW":
                yellow_count += 1
            elif detected_color == "PURPLE":
                purple_count += 1

            print(f"{detected_color} WAYPOINT REACHED")
            move_counter = 0
            state = GO_BACK

    elif state == GO_BACK:
        leftMotor.setVelocity(-FORWARD_SPEED)
        rightMotor.setVelocity(-FORWARD_SPEED)
        move_counter += 1

        target_steps = get_steps(detected_color)

        if move_counter >= target_steps:
            stop()
            rotate_counter = 0
            angle_index += 1
            state = ROTATE

    elif state == ROTATE:
        leftMotor.setVelocity(-ROTATE_SPEED)
        rightMotor.setVelocity(ROTATE_SPEED)
        rotate_counter += 1

        if rotate_counter >= STEP_45:
            stop()
            rotate_counter = 0
            state = DETECT

    elif state == DONE:
        stop()
        print("================================")
        print("MISSION COMPLETE")
        print("================================")
        print(f"RED    : {red_count}")
        print(f"YELLOW : {yellow_count}")
        print(f"PURPLE : {purple_count}")
        break