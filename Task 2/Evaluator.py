import json
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA

MAX_TIME = 180.0

TOTAL_CORRIDORS = 3
TOTAL_WAYPOINTS = 15


def decrypt_match_data():

    with open("private.pem", "rb") as f:
        private_key = RSA.import_key(f.read())

    with open("controllers/supervisor_task_2/coordinates.bin", "rb") as f:

        enc_session_key = f.read(256)
        nonce = f.read(16)
        tag = f.read(16)
        ciphertext = f.read()

    session_key = PKCS1_OAEP.new(private_key).decrypt(enc_session_key)

    cipher = AES.new(session_key, AES.MODE_EAX,nonce )

    data = cipher.decrypt_and_verify(ciphertext,tag )

    return json.loads(data.decode("utf-8") )


def calculate_scores(data):
    ground_truth = data.get("ground_truth_sequence", [])
    student_colors = data.get("student_raw_colors", data.get("color_order", []))
    waypoint_times = data.get("waypoint_times", [])
    final_time = data.get("final_time", MAX_TIME)

    # Safety
    total_waypoints = len(waypoint_times)

    # 1. Path / color sequence score (50 points)
    if student_colors == ground_truth:
        path_score = 40.0
        match_status = "CORRECT_PATH"
    else:
        # simple penalty: fraction of correctly matched positions
        matches = sum(1 for gt, st in zip(ground_truth, student_colors) if gt == st)
        path_score = 40.0 * (matches / max(1, len(ground_truth)))
        match_status = "WRONG_PATH"

    # 2. Waypoint score (30 points)
    #    full marks if all expected waypoints are reached
    #    (here we assume TOTAL_WAYPOINTS is our target)
    waypoints_collected = total_waypoints
    waypoint_score = (waypoints_collected / TOTAL_WAYPOINTS) * 30.0

    # 3. Time score (20 points) – same as before
    time_score = max( 0.0, (MAX_TIME - final_time) / MAX_TIME * 30.0 )

    total_score = path_score + waypoint_score + time_score

    return {
        "match_status": match_status,
        "ground_truth_sequence": ground_truth,
        "student_colors": student_colors,
        "waypoints_collected": waypoints_collected,
        "final_time": final_time,
        "path_score": round(path_score, 2),
        "waypoint_score": round(waypoint_score, 2),
        "time_score": round(time_score, 2),
        "total_score": round(total_score, 2)
    }


def save_report(report):

    with open( "evaluation_report.json",  "w" ) as f:

        json.dump( report,f,indent=4 )

    print( "\n===== EVALUATION REPORT =====" )

    print( json.dumps(report, indent=4 ) )


def main():

    try:

        data = decrypt_match_data()

        report = calculate_scores( data  )

        save_report(report)

    except Exception as e:

        print(f"Evaluation Failed: {e}")


if __name__ == "__main__":
    main()