import math
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, render_template, request, jsonify, session,redirect,url_for,Response,flash
import os
import base64
from flask_mysqldb import MySQL
import MySQLdb
from MySQLdb import OperationalError
from MySQLdb._exceptions import IntegrityError
import json
import io
import numpy as np
from enum import Enum
import warnings
import threading
import datetime
import utils
import random
import time
import cv2
import keyboard

#variables
studentInfo=None
camera=None
profileName=None
detection_tasks_started = False
last_face_frame = None
last_face_frame_lock = threading.Lock()
monitor_lock = threading.Lock()
monitor_session = {
    "active": False,
    "result_id": None,
    "started_at": None,
    "active_events": {},
    "events": []
}

#Flak's Application Confguration
warnings.filterwarnings("ignore")
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = 'xyz'
# app.config["MONGO_URI"] = "mongodb://localhost:27017/"
os.path.dirname("../templates")

#Flak's Database Configuration
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST', '127.0.0.1')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER', 'root')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD', 'addysql@13')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB', 'examproctordb')
app.config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT', '3306'))
mysql = MySQL(app)
db_error_message = None

executor = ThreadPoolExecutor(max_workers=4)  # Adjust the number of workers as needed
face_detector = cv2.CascadeClassifier('Haarcascades/haarcascade_frontalface_default.xml')

EVENT_CONFIG = {
    "Face Absence Detected": {"min_duration": 2.0, "mark_per_second": 2.0, "prefix": "face_absence"},
    "Multiple Faces Detected": {"min_duration": 2.0, "mark_per_second": 2.0, "prefix": "multiple_faces"},
    "Looking Away From Screen": {"min_duration": 3.0, "mark_per_second": 1.0, "prefix": "looking_away"},
    "Mobile Phone Detected": {"min_duration": 1.0, "mark_per_second": 3.0, "prefix": "mobile_phone"},
    "Background Voice / Noise Detected": {"min_duration": 2.0, "mark_per_second": 1.5, "prefix": "background_voice"},
}


def bootstrap_database():
    global db_error_message
    create_db_connection = None
    create_db_cursor = None
    app_connection = None
    app_cursor = None
    try:
        create_db_connection = MySQLdb.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            passwd=app.config['MYSQL_PASSWORD'],
            port=app.config['MYSQL_PORT'],
            charset='utf8mb4'
        )
        create_db_cursor = create_db_connection.cursor()
        create_db_cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{app.config['MYSQL_DB']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        create_db_connection.commit()

        app_connection = MySQLdb.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            passwd=app.config['MYSQL_PASSWORD'],
            db=app.config['MYSQL_DB'],
            port=app.config['MYSQL_PORT'],
            charset='utf8mb4'
        )
        app_cursor = app_connection.cursor()
        app_cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                ID INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                Name VARCHAR(255) NOT NULL,
                Email VARCHAR(255) NOT NULL UNIQUE,
                Password VARCHAR(255) NOT NULL,
                Role VARCHAR(50) NOT NULL DEFAULT 'STUDENT'
            )
            """
        )
        app_cursor.execute("SELECT ID FROM students WHERE Email = %s", ('admin@example.com',))
        admin_row = app_cursor.fetchone()
        if admin_row is None:
            app_cursor.execute(
                """
                INSERT INTO students (Name, Email, Password, Role)
                VALUES (%s, %s, %s, %s)
                """,
                ('Admin', 'admin@example.com', 'admin123', 'ADMIN')
            )
        else:
            app_cursor.execute(
                """
                UPDATE students
                SET Name=%s, Password=%s, Role=%s
                WHERE Email=%s
                """,
                ('Admin', 'admin123', 'ADMIN', 'admin@example.com')
            )
        app_connection.commit()
        db_error_message = None
    except OperationalError as exc:
        db_error_message = (
            "Database connection failed. Set MYSQL_HOST, MYSQL_PORT, MYSQL_USER, "
            "MYSQL_PASSWORD, and MYSQL_DB for a running MySQL server. "
            f"Current target: {app.config['MYSQL_USER']}@{app.config['MYSQL_HOST']}:{app.config['MYSQL_PORT']}/{app.config['MYSQL_DB']}. "
            f"MySQL error: {exc}"
        )
    finally:
        if create_db_cursor is not None:
            try:
                create_db_cursor.close()
            except Exception:
                pass
        if create_db_connection is not None:
            try:
                create_db_connection.close()
            except Exception:
                pass
        if app_cursor is not None:
            try:
                app_cursor.close()
            except Exception:
                pass


with app.app_context():
    bootstrap_database()


def open_camera(camera_index=0):
    for backend in (cv2.CAP_DSHOW, cv2.CAP_ANY):
        try:
            capture = cv2.VideoCapture(camera_index, backend) if backend != cv2.CAP_ANY else cv2.VideoCapture(camera_index)
            if capture is not None and capture.isOpened():
                return capture
            if capture is not None:
                capture.release()
        except Exception:
            pass
    return None


def get_db_connection():
    return MySQLdb.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        passwd=app.config['MYSQL_PASSWORD'],
        db=app.config['MYSQL_DB'],
        port=app.config['MYSQL_PORT'],
        charset='utf8mb4'
    )


def normalize_email(value):
    if value is None:
        return ''
    return value.strip().lower()


def render_status_frame(message):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(frame, message, (30, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    ret, buffer = cv2.imencode('.jpg', frame)
    if not ret:
        return b""
    return buffer.tobytes()


def decode_data_url_to_frame(image_data):
    if not image_data or ',' not in image_data:
        return None
    try:
        encoded_image = image_data.split(',', 1)[1]
        image_bytes = base64.b64decode(encoded_image)
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        return cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    except Exception:
        return None


def get_violation_image_path(filename):
    return os.path.join(app.static_folder, 'ViolationImages', filename)


def save_violation_snapshot(frame, event_name, event_started_at):
    if frame is None:
        return ''
    os.makedirs(os.path.join(app.static_folder, 'ViolationImages'), exist_ok=True)
    safe_name = EVENT_CONFIG[event_name]["prefix"]
    timestamp = event_started_at.strftime('%Y%m%d_%H%M%S')
    filename = f"{safe_name}_{timestamp}.jpg"
    cv2.imwrite(get_violation_image_path(filename), frame)
    return filename


def reset_monitor_session(result_id=None):
    monitor_session["active"] = bool(result_id)
    monitor_session["result_id"] = result_id
    monitor_session["started_at"] = time.time() if result_id else None
    monitor_session["active_events"] = {}
    monitor_session["events"] = []


def begin_monitor_session():
    with monitor_lock:
        result_id = utils.get_resultId()
        reset_monitor_session(result_id)
        return result_id


def append_monitor_event(event_name, started_at, ended_at, frame=None):
    if monitor_session["result_id"] is None:
        return
    duration_seconds = max(1, math.ceil(ended_at - started_at))
    config = EVENT_CONFIG[event_name]
    image_link = save_violation_snapshot(frame, event_name, datetime.datetime.fromtimestamp(started_at))
    monitor_session["events"].append({
        "Name": event_name,
        "Time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at)),
        "Duration": f"{duration_seconds} seconds",
        "Mark": round(config["mark_per_second"] * duration_seconds, 2),
        "Link": image_link,
        "RId": monitor_session["result_id"]
    })


def update_monitor_event(event_name, is_active, now_ts, frame=None):
    active_events = monitor_session["active_events"]
    if is_active:
        if event_name not in active_events:
            active_events[event_name] = {
                "start": now_ts,
                "last_frame": None if frame is None else frame.copy()
            }
        elif frame is not None:
            active_events[event_name]["last_frame"] = frame.copy()
        return

    if event_name not in active_events:
        return

    started = active_events[event_name]["start"]
    duration = now_ts - started
    saved_frame = active_events[event_name]["last_frame"]
    del active_events[event_name]
    if duration >= EVENT_CONFIG[event_name]["min_duration"]:
        append_monitor_event(event_name, started, now_ts, saved_frame)


def finalize_monitor_session():
    with monitor_lock:
        if not monitor_session["active"]:
            return None, []
        now_ts = time.time()
        for event_name in list(monitor_session["active_events"].keys()):
            update_monitor_event(event_name, False, now_ts)
        result_id = monitor_session["result_id"]
        events = list(monitor_session["events"])
        reset_monitor_session(None)
        return result_id, events


def analyze_monitor_frame(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_detector.detectMultiScale(gray, 1.2, 6)
    face_count = len(faces)
    face_absent = face_count == 0
    multiple_faces = face_count > 1
    looking_away = False

    if face_count == 1:
        x, y, w, h = faces[0]
        frame_h, frame_w = frame.shape[:2]
        face_center_x = x + (w / 2.0)
        face_center_y = y + (h / 2.0)
        normalized_x = face_center_x / frame_w
        normalized_y = face_center_y / frame_h
        face_ratio = (w * h) / float(frame_w * frame_h)
        looking_away = normalized_x < 0.30 or normalized_x > 0.70 or normalized_y < 0.25 or normalized_y > 0.72 or face_ratio < 0.06

    phone_detected = False
    try:
        detection_results = utils.model.predict(source=[frame], conf=0.35, save=False, verbose=False)
        for result in detection_results:
            boxes = result.boxes.cpu().numpy()
            for box in boxes:
                detected_obj = result.names[int(box.cls[0])]
                if detected_obj == 'cell phone':
                    phone_detected = True
                    break
            if phone_detected:
                break
    except Exception:
        phone_detected = False

    return {
        "face_count": face_count,
        "face_absent": face_absent,
        "multiple_faces": multiple_faces,
        "looking_away": looking_away,
        "phone_detected": phone_detected
    }


def crop_face_portrait(frame):
    if frame is None:
        return None

    working = cv2.flip(frame, 1)
    gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    faces = face_detector.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=6)

    if len(faces) == 0:
        return working

    x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
    frame_h, frame_w = working.shape[:2]

    target_ratio = 4.0 / 5.0
    crop_w = min(frame_w, int(w * 2.2))
    crop_h = min(frame_h, int(h * 2.8))

    if crop_w / crop_h > target_ratio:
        crop_h = min(frame_h, int(crop_w / target_ratio))
    else:
        crop_w = min(frame_w, int(crop_h * target_ratio))

    center_x = x + (w // 2)
    center_y = y + int(h * 0.52)

    left = max(0, center_x - crop_w // 2)
    top = max(0, center_y - crop_h // 2)
    right = min(frame_w, left + crop_w)
    bottom = min(frame_h, top + crop_h)

    if right - left < crop_w:
        left = max(0, right - crop_w)
    if bottom - top < crop_h:
        top = max(0, bottom - crop_h)

    cropped = working[top:bottom, left:right]
    if cropped.size == 0:
        return working

    return cv2.resize(cropped, (640, 800), interpolation=cv2.INTER_AREA)


#Function to show face detection's Rectangle in Face Input Page
def capture_by_frames():
    global last_face_frame
    stream = open_camera()
    detector = cv2.CascadeClassifier('Haarcascades/haarcascade_frontalface_default.xml')
    try:
        while True:
            if stream is None or not stream.isOpened():
                frame_bytes = render_status_frame("Camera not available")
            else:
                success, frame = stream.read()
                if not success or frame is None:
                    frame_bytes = render_status_frame("Waiting for camera frame")
                else:
                    with last_face_frame_lock:
                        last_face_frame = frame.copy()
                    faces = detector.detectMultiScale(frame, 1.2, 6)
                    for (x, y, w, h) in faces:
                        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 3)
                    ret, buffer = cv2.imencode('.jpg', frame)
                    frame_bytes = buffer.tobytes() if ret else render_status_frame("Failed to encode camera frame")
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    finally:
        if stream is not None:
            stream.release()


#Login Related
@app.route('/')
def main():
    if db_error_message:
        return db_error_message, 500
    return render_template('role_select.html')


@app.route('/student/login')
def student_login():
    if db_error_message:
        return db_error_message, 500
    return render_template('student_login.html')


@app.route('/admin/login')
def admin_login():
    if db_error_message:
        return db_error_message, 500
    return render_template('admin_login.html')

@app.route('/login', methods=['POST'])
def login():
    global studentInfo
    if db_error_message:
        flash(db_error_message, category='error')
        return redirect(url_for('main'))
    if request.method == 'POST':
        username = normalize_email(request.form['username'])
        password = request.form['password'].strip()
        expected_role = request.form.get('expected_role', '').upper()
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM students WHERE Email=%s", (username,))
            data = cur.fetchone()
        finally:
            cur.close()
            conn.close()
        if data is None:
            flash('This email is not registered. Please sign up first.', category='error')
            if expected_role == 'ADMIN':
                return redirect(url_for('admin_login'))
            if expected_role == 'STUDENT':
                return redirect(url_for('student_login'))
            return redirect(url_for('main'))
        else:
            id, name, email, stored_password, role = data
            if stored_password != password:
                flash('Incorrect password. Please try again.', category='error')
                if expected_role == 'ADMIN':
                    return redirect(url_for('admin_login'))
                if expected_role == 'STUDENT':
                    return redirect(url_for('student_login'))
                return redirect(url_for('main'))
            if expected_role and role != expected_role:
                flash(f'This account belongs to the {role.lower()} portal.', category='error')
                if expected_role == 'ADMIN':
                    return redirect(url_for('admin_login'))
                return redirect(url_for('student_login'))
            studentInfo={ "Id": id, "Name": name, "Email": email, "Password": stored_password}
            if role == 'STUDENT':
                utils.Student_Name = name
                return redirect(url_for('rules'))
            else:
                return redirect(url_for('adminStudents'))


@app.route('/signup')
def signup():
    if db_error_message:
        return db_error_message, 500
    return render_template('signup.html')


@app.route('/signup', methods=['POST'])
def signup_post():
    if db_error_message:
        return db_error_message, 500
    name = request.form['name'].strip()
    email = normalize_email(request.form['email'])
    password = request.form['password'].strip()

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO students (Name, Email, Password, Role) VALUES (%s, %s, %s, %s)",
            (name, email, password, 'STUDENT')
        )
        conn.commit()
        flash('Account created. You can log in now.', category='success')
        return redirect(url_for('main'))
    except IntegrityError:
        conn.rollback()
        flash('That email is already registered.', category='error')
        return redirect(url_for('signup'))
    finally:
        cur.close()
        conn.close()

@app.route('/logout')
def logout():
    return redirect(url_for('main'))

#Student Related
@app.route('/rules')
def rules():
    return render_template('ExamRules.html')

@app.route('/faceInput')
def faceInput():
    return render_template('ExamFaceInput.html')

@app.route('/saveFaceInput', methods=['POST'])
def saveFaceInput():
    global profileName
    if utils.cap is not None and utils.cap.isOpened():
        utils.cap.release()
    payload = request.get_json(silent=True) or {}
    frame = decode_data_url_to_frame(payload.get('image', ''))
    if frame is None:
        return jsonify({"ok": False, "message": "No captured image was provided."}), 400
    frame = crop_face_portrait(frame)
    if frame is None:
        return jsonify({"ok": False, "message": "Captured image could not be processed."}), 400
    profileName=f"{studentInfo['Name']}_{utils.get_resultId():03}" + "Profile.jpg"
    cv2.imwrite(profileName,frame)
    utils.move_file_to_output_folder(profileName,'Profiles')
    return jsonify({"ok": True, "next": url_for('confirmFaceInput')})


@app.route('/monitor/frame', methods=['POST'])
def monitor_frame():
    payload = request.get_json(silent=True) or {}
    frame = decode_data_url_to_frame(payload.get('image', ''))
    if frame is None:
        return jsonify({"ok": False, "message": "Captured frame could not be decoded."}), 400

    with monitor_lock:
        if not monitor_session["active"]:
            return jsonify({"ok": False, "message": "Monitoring session is not active."}), 400
        analysis = analyze_monitor_frame(frame)
        now_ts = time.time()
        update_monitor_event("Face Absence Detected", analysis["face_absent"], now_ts, frame)
        update_monitor_event("Multiple Faces Detected", analysis["multiple_faces"], now_ts, frame)
        update_monitor_event("Looking Away From Screen", analysis["looking_away"], now_ts, frame)
        update_monitor_event("Mobile Phone Detected", analysis["phone_detected"], now_ts, frame)

    return jsonify({"ok": True, "analysis": analysis})


@app.route('/monitor/audio', methods=['POST'])
def monitor_audio():
    payload = request.get_json(silent=True) or {}
    rms = float(payload.get('rms', 0))
    peak = float(payload.get('peak', 0))
    if rms < 0 or peak < 0:
        return jsonify({"ok": False, "message": "Invalid audio payload."}), 400

    suspicious_audio = rms >= 0.045 or peak >= 0.18

    with monitor_lock:
        if not monitor_session["active"]:
            return jsonify({"ok": False, "message": "Monitoring session is not active."}), 400
        now_ts = time.time()
        update_monitor_event("Background Voice / Noise Detected", suspicious_audio, now_ts)

    return jsonify({"ok": True, "analysis": {"rms": rms, "peak": peak, "suspicious_audio": suspicious_audio}})

@app.route('/confirmFaceInput')
def confirmFaceInput():
    profile = profileName
    utils.fr.encode_faces()
    if profile not in utils.fr.known_face_names:
        flash('No face was detected in the captured image. Please retake your photo with your face clearly visible.', category='error')
        return redirect(url_for('faceInput'))
    return render_template('ExamConfirmFaceInput.html', profile = profile)

@app.route('/systemCheck')
def systemCheck():
    return render_template('ExamSystemCheck.html')

@app.route('/systemCheck', methods=["POST"])
def systemCheckRoute():
    if request.method == 'POST':
        examData = request.json
        output = 'exam'
        if 'Not available' in examData['input'].split(';'): output = 'systemCheckError'
    return jsonify({"output": output})

@app.route('/systemCheckError')
def systemCheckError():
    return render_template('ExamSystemCheckError.html')

@app.route('/exam')
def exam():
    keyboard.hook(utils.shortcut_handler)
    return render_template('Exam.html')

@app.route('/exam', methods=["POST"])
def examAction():
    link = ''
    if request.method == 'POST':
        examData = request.json
        if(examData['input']!=''):
            result_id, monitor_events = finalize_monitor_session()
            if result_id is None:
                result_id = utils.get_resultId()
            utils.write_json({
                "Name": ('Prohibited Shorcuts (' + ','.join(list(dict.fromkeys(utils.shorcuts))) + ') are detected.'),
                "Time": (str(len(utils.shorcuts)) + " Counts"),
                "Duration": '',
                "Mark": (1.5 * len(utils.shorcuts)),
                "Link": '',
                "RId": result_id
            })
            for event in monitor_events:
                utils.write_json(event)
            utils.shorcuts=[]
            trustScore= utils.get_TrustScore(result_id)
            totalMark=  math.floor(float(examData['input'])* 6.6667)
            if trustScore >=30:
                status="Fail(Cheating)"
                link = 'showResultFail'
            else:
                if totalMark < 50:
                    status="Fail"
                    link = 'showResultFail'
                else:
                    status="Pass"
                    link = 'showResultPass'
            utils.write_json({
                "Id": result_id,
                "Name": studentInfo['Name'],
                "TotalMark": totalMark,
                "TrustScore": max(100-trustScore, 0),
                "Status": status,
                "Date": time.strftime("%Y-%m-%d", time.localtime(time.time())),
                "StId": studentInfo['Id'],
                "Link" : profileName
            },"result.json")
            resultStatus= studentInfo['Name']+';'+str(totalMark)+';'+status+';'+time.strftime("%Y-%m-%d", time.localtime(time.time()))
        else:
            result_id = begin_monitor_session()
            resultStatus=''
            return jsonify({"output": resultStatus, "link": link, "result_id": result_id})
    return jsonify({"output": resultStatus, "link": link})

@app.route('/showResultPass/<result_status>')
def showResultPass(result_status):
    return render_template('ExamResultPass.html',result_status=result_status)

@app.route('/showResultFail/<result_status>')
def showResultFail(result_status):
    return render_template('ExamResultFail.html',result_status=result_status)

#Admin Related
@app.route('/adminResults')
def adminResults():
    results = utils.getResults()
    return render_template('Results.html', results=results)

@app.route('/adminResultDetails/<resultId>')
def adminResultDetails(resultId):
    result_Details = utils.getResultDetails(resultId)
    return render_template('ResultDetails.html', resultDetials=result_Details)

@app.route('/adminResultDetailsVideo/<videoInfo>')
def adminResultDetailsVideo(videoInfo):
    return render_template('ResultDetailsVideo.html', videoInfo= videoInfo)

@app.route('/adminStudents')
def adminStudents():
    if db_error_message:
        return db_error_message, 500
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM students where Role='STUDENT'")
        data = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return render_template('Students.html', students=data)

@app.route('/insertStudent', methods=['POST'])
def insertStudent():
    if db_error_message:
        return db_error_message, 500
    if request.method == "POST":
        name = request.form['username'].strip()
        email = normalize_email(request.form['email'])
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO students (Name, Email, Password, Role) VALUES (%s, %s, %s, %s)", (name, email, password,'STUDENT'))
            conn.commit()
        finally:
            cur.close()
            conn.close()
        return redirect(url_for('adminStudents'))

@app.route('/deleteStudent/<string:stdId>', methods=['GET'])
def deleteStudent(stdId):
    if db_error_message:
        return db_error_message, 500
    flash("Record Has Been Deleted Successfully")
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM students WHERE ID=%s", (stdId,))
        conn.commit()
    finally:
        cur.close()
        conn.close()
    return redirect(url_for('adminStudents'))

@app.route('/updateStudent', methods=['POST', 'GET'])
def updateStudent():
    if db_error_message:
        return db_error_message, 500
    if request.method == 'POST':
        id_data = request.form['id']
        name = request.form['name'].strip()
        email = normalize_email(request.form['email'])
        password = request.form['password']
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                   UPDATE students
                   SET Name=%s, Email=%s, Password=%s
                   WHERE ID=%s
                """, (name, email, password, id_data))
            conn.commit()
        finally:
            cur.close()
            conn.close()
        return redirect(url_for('adminStudents'))


@app.route('/health/db')
def health_db():
    if db_error_message:
        return jsonify({"ok": False, "message": db_error_message}), 500
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            cur.close()
            conn.close()
        return jsonify({
            "ok": True,
            "host": app.config['MYSQL_HOST'],
            "port": app.config['MYSQL_PORT'],
            "database": app.config['MYSQL_DB']
        })
    except OperationalError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 500

if __name__ == '__main__':
    app.run(debug=True)
