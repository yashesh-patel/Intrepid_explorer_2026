import json
import os
import zipfile
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA

# ------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------
TOTAL_BOXES = 8
MAX_TIME = 180.0

ZIP_FILE_NAME = "Submission.zip"
PRIVATE_KEY_NAME = "private.pem"


# ------------------------------------------------------------------
# EXTRACTION
# ------------------------------------------------------------------
def extract_package(zip_path):
    if not os.path.exists(zip_path):
        raise FileNotFoundError(
            f"Archive package '{zip_path}' not found."
        )

    if not os.path.exists(PRIVATE_KEY_NAME):
        raise FileNotFoundError(
            f"Private key '{PRIVATE_KEY_NAME}' not found."
        )

    print(f"Extracting {zip_path}...")

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(".")

    if not os.path.exists("match_data.bin"):
        raise FileNotFoundError(
            "match_data.bin not found inside submission."
        )


# ------------------------------------------------------------------
# CLEANUP
# ------------------------------------------------------------------
def cleanup_match_data():
    if os.path.exists("match_data.bin"):
        try:
            os.remove("match_data.bin")
            print("Temporary match_data.bin removed.")
        except Exception as e:
            print(f"Cleanup warning: {e}")


# ------------------------------------------------------------------
# DECRYPT
# ------------------------------------------------------------------
def decrypt_match_data():

    with open(PRIVATE_KEY_NAME, "rb") as f:
        private_key = RSA.import_key(f.read())

    with open("match_data.bin", "rb") as f:
        enc_session_key = f.read(256)
        nonce = f.read(16)
        tag = f.read(16)
        ciphertext = f.read()

    session_key = PKCS1_OAEP.new(private_key).decrypt(enc_session_key)

    cipher = AES.new(session_key, AES.MODE_EAX, nonce)

    decrypted_data = cipher.decrypt_and_verify(ciphertext, tag)

    return json.loads(decrypted_data.decode("utf-8"))


# ------------------------------------------------------------------
# GET FINAL TIME
# ------------------------------------------------------------------
def extract_final_time(data):
    """
    Supports:
    {
        "final_time": 73.5
    }

    OR

    {
        "time": [0.03, 0.06, ..., 73.5]
    }
    """

    if "final_time" in data:
        return float(data["final_time"])

    if "time" in data:
        time_data = data["time"]

        if isinstance(time_data, list) and len(time_data) > 0:
            return float(time_data[-1])

        if isinstance(time_data, (int, float)):
            return float(time_data)

    return MAX_TIME


# ------------------------------------------------------------------
# SCORING
# ------------------------------------------------------------------
def calculate_scores(data):

    boxes_collected = data.get("boxes_collected", 0)

    final_time = extract_final_time(data)

    valid_boxes = sum(
        1
        for box in data.get("box_results", [])
        if box.get("valid", False)
    )

    # Box Score (40 max)
    box_score = boxes_collected * 5.0

    # Time Score (60 max)
    time_remaining = max(0.0, MAX_TIME - final_time)
    time_score = (time_remaining / MAX_TIME) * 60.0

    total_score = box_score + time_score

    report = {
        "match_status": data.get("match_status", "SUCCESS"),
        "boxes_collected": boxes_collected,
        "valid_boxes": valid_boxes,
        "final_time": round(final_time, 2),
        "box_score": round(box_score, 2),
        "time_score": round(time_score, 2),
        "total_score": round(total_score, 2)
    }

    return report


# ------------------------------------------------------------------
# REPORT
# ------------------------------------------------------------------
def save_report(report):

    with open("evaluation_report.json", "w") as f:
        json.dump(report, f, indent=4)

    print("\n========== EVALUATION REPORT ==========")
    print(json.dumps(report, indent=4))


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():

    try:

        extract_package(ZIP_FILE_NAME)

        data = decrypt_match_data()

        print("\n========== DECRYPTED DATA ==========")
        print("Keys Found:", list(data.keys()))

        final_time = extract_final_time(data)

        print(f"Detected Final Time: {final_time:.2f}s")

        report = calculate_scores(data)

        save_report(report)

    except Exception as e:
        print(f"\nEvaluation Failed: {e}")

    finally:
        cleanup_match_data()


if __name__ == "__main__":
    main()