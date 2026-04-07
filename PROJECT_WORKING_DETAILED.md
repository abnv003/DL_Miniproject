# Project Working Document

## 1. What this project is

This project is a Flask-based online exam proctoring system. It combines:

- A web application for students and admins
- A quiz/exam interface in the browser
- Real-time webcam and microphone monitoring from the browser
- Computer vision checks on the backend
- Persistent student data in MySQL
- Exam results and violation logs in local JSON files

The current live application starts from `app.py`. The file `main.py` is only a default sample script and is not part of the application flow.

## 2. High-level architecture

The project has 4 major layers:

### A. Web application layer

Handled by Flask in `app.py`.

Responsibilities:

- Serve HTML pages from `templates/`
- Serve static CSS/JS/images from `static/`
- Handle student login/signup
- Handle admin login and student management
- Start and stop an exam session
- Accept monitoring data from the browser
- Calculate final status and trust score
- Show result dashboards

### B. Browser/client layer

Handled mainly by:

- `static/js/script.js`
- `static/js/questions.js`
- `static/js/exam_monitor.js`

Responsibilities:

- Render quiz questions
- Track the quiz timer
- Start the monitoring session when exam begins
- Capture webcam frames using `getUserMedia`
- Capture microphone levels using Web Audio API
- Send monitoring data to Flask endpoints
- Stop monitoring and redirect to the result page after submission

### C. Detection and utility layer

Handled by `utils.py` and part of `app.py`.

Responsibilities:

- Load ML and CV models
- Detect faces
- Encode and compare student faces
- Detect cell phones in webcam frames
- Track keyboard shortcuts
- Read and write result/violation data

### D. Persistence layer

Split across two storage mechanisms:

- MySQL: stores student accounts
- JSON files: store exam results and violation records

Files used:

- `init_db.sql`
- `result.json`
- `violation.json`

## 3. Main entry point and startup flow

The active entry point is `app.py`.

When `app.py` starts, it does the following:

1. Creates a Flask app.
2. Reads MySQL connection settings from environment variables, with defaults:
   - `MYSQL_HOST=127.0.0.1`
   - `MYSQL_USER=root`
   - `MYSQL_PASSWORD=smith03`
   - `MYSQL_DB=examproctordb`
   - `MYSQL_PORT=3306`
3. Initializes `Flask-MySQLdb`.
4. Loads an OpenCV Haar cascade face detector:
   - `Haarcascades/haarcascade_frontalface_default.xml`
5. Boots the database using `bootstrap_database()`.
6. Ensures the `students` table exists.
7. Ensures one default admin account exists:
   - Email: `admin@example.com`
   - Password: `admin123`
8. Starts the Flask server.

At import time, `utils.py` also performs important initialization:

- Loads `yolov8n.pt` through Ultralytics YOLO
- Loads face profile encodings through `FaceRecognition()`
- Initializes several legacy helper objects and state containers

## 4. Folder and file responsibilities

### Core backend files

- `app.py`
  Main Flask application, routes, monitoring session logic, exam submission logic.

- `utils.py`
  Shared utilities, JSON access, keyboard shortcut detection, face recognition logic, YOLO loading, and older detection code that is mostly no longer wired into the current web flow.

- `face_recognition_stub.py`
  Fallback implementation used when the `face_recognition` package cannot be imported, usually because `dlib` installation failed.

- `init_db.sql`
  Creates the MySQL database and `students` table and inserts a default admin if missing.

### Data files

- `result.json`
  Stores one record per exam attempt.

- `violation.json`
  Stores one record per violation event.

### Model/data assets

- `yolov8n.pt`
  Pretrained YOLOv8 nano model used for object detection.

- `Haarcascades/haarcascade_frontalface_default.xml`
  OpenCV Haar cascade used for face detection.

- `utils/coco.txt`
  Class labels used by YOLO-related logic.

### Frontend files

- `templates/*.html`
  Server-rendered pages for login, exam, results, admin pages.

- `static/js/questions.js`
  Contains the hardcoded quiz question bank.

- `static/js/script.js`
  Quiz engine, timer, submission flow.

- `static/js/exam_monitor.js`
  Webcam/audio monitoring in the browser.

## 5. Student-side user flow

The student journey is:

1. Open `/`
2. Choose student login
3. Log in or sign up
4. Read exam rules
5. Capture face image
6. Confirm face image
7. Run system check
8. Start the exam
9. Browser monitoring begins
10. Student answers quiz questions
11. Student submits the exam
12. Backend computes marks, trust score, and status
13. Result page is shown

### Important routes in the student flow

- `/`
  Role selection page

- `/student/login`
  Student login page

- `/signup`
  Student registration page

- `/rules`
  Exam rules page

- `/faceInput`
  Face capture page

- `/saveFaceInput`
  Accepts captured profile image from the browser

- `/confirmFaceInput`
  Verifies that a face can be encoded from the saved profile

- `/systemCheck`
  System capability check page

- `/exam`
  Exam page

- `/showResultPass/<result_status>`
  Pass result page

- `/showResultFail/<result_status>`
  Fail result page

## 6. Admin-side flow

Admin capabilities are exposed through these routes:

- `/admin/login`
  Admin login page

- `/adminStudents`
  Lists all student accounts from MySQL

- `/insertStudent`
  Adds a new student

- `/updateStudent`
  Updates student account details

- `/deleteStudent/<stdId>`
  Deletes a student

- `/adminResults`
  Shows all exam results from `result.json`

- `/adminResultDetails/<resultId>`
  Shows one exam result together with linked violations

- `/adminResultDetailsVideo/<videoInfo>`
  Opens a media detail page for stored evidence

## 7. How the exam itself works

The exam is a browser-based multiple-choice quiz.

### Question source

Questions are hardcoded in `static/js/questions.js`.

There are 15 questions in the current file. Each question has:

- `title`
- `choices`
- `answer`

### Quiz runtime

`static/js/script.js` handles the quiz:

- Initializes `secondsLeft = 300`
- Displays one question at a time
- Increments the `correct` count for correct answers
- Deducts 10 seconds for wrong answers
- Ends when:
  - time reaches zero, or
  - all questions are answered

### Exam start and stop protocol

When the student clicks Start:

1. Frontend sends `POST /exam` with `{"input": ""}`
2. Backend interprets empty input as "start exam"
3. `begin_monitor_session()` is called
4. A new `result_id` is reserved from `result.json`
5. Browser monitoring is started through `window.examMonitor.start()`
6. Quiz timer begins

When the student clicks Submit:

1. Frontend sends `POST /exam` with `{"input": correctAnswers}`
2. Backend finalizes the monitoring session
3. All accumulated violation events are written to `violation.json`
4. Shortcut violations are also written
5. Final exam score is calculated
6. Trust score is calculated from all penalties
7. Final result record is written to `result.json`
8. Frontend stops browser monitoring
9. Student is redirected to pass/fail page

## 8. Monitoring pipeline in the current implementation

The current live monitoring pipeline is hybrid:

- Webcam and microphone capture happen in the browser
- Detection logic happens on the server
- Keyboard shortcut detection happens on the server machine through the `keyboard` library

### 8.1 Browser monitoring

Implemented in `static/js/exam_monitor.js`.

#### Webcam sampling

The browser requests:

- video access
- audio access

using `navigator.mediaDevices.getUserMedia(...)`.

Frames are not streamed continuously as video. Instead:

- the current webcam frame is drawn onto a hidden canvas
- converted to JPEG using `canvas.toDataURL("image/jpeg", 0.75)`
- posted to `/monitor/frame`

Sampling interval:

- webcam frame every 2000 ms

#### Audio sampling

The microphone track is analyzed with Web Audio API:

- `AudioContext`
- `MediaStreamSource`
- `AnalyserNode`

The browser computes:

- RMS level
- Peak amplitude

Sampling interval:

- audio sample every 1500 ms

These values are posted to `/monitor/audio`.

### 8.2 Server-side monitoring session

Implemented in `app.py`.

The global `monitor_session` object stores:

- whether monitoring is active
- current result ID
- session start time
- currently active events
- finalized event list

This is important because a violation is not written immediately on first detection. Instead, the app:

1. Marks an event as active when detection starts
2. Tracks duration over time
3. Finalizes the event when detection ends
4. Writes it only if the duration exceeds a minimum threshold

This avoids logging every short false positive.

## 9. Active detection logic in the current app

The live app currently uses 5 active event types defined in `EVENT_CONFIG` inside `app.py`.

### 9.1 Face Absence Detected

Meaning:

- No face is visible in the frame

Detection method:

- OpenCV Haar cascade face detector

Minimum duration:

- 2.0 seconds

Penalty:

- 2.0 marks per second

### 9.2 Multiple Faces Detected

Meaning:

- More than one face is visible

Detection method:

- OpenCV Haar cascade face detector

Minimum duration:

- 2.0 seconds

Penalty:

- 2.0 marks per second

### 9.3 Looking Away From Screen

Meaning:

- Exactly one face exists, but face position suggests the student is not centered on screen

Detection method:

- The app estimates this heuristically from the face bounding box:
  - normalized X position
  - normalized Y position
  - relative face size in the frame

This is not true gaze estimation and not a deep head-pose model. It is a bounding-box based heuristic.

Minimum duration:

- 3.0 seconds

Penalty:

- 1.0 mark per second

### 9.4 Mobile Phone Detected

Meaning:

- A cell phone object is detected in the webcam frame

Detection method:

- YOLOv8 object detection
- Only the `cell phone` class is considered in the active web flow

Minimum duration:

- 1.0 second

Penalty:

- 3.0 marks per second

### 9.5 Background Voice / Noise Detected

Meaning:

- Audio level crosses a suspicious threshold

Detection method:

- Threshold-based audio detection from browser-provided RMS and peak values
- Current thresholds:
  - `rms >= 0.045`, or
  - `peak >= 0.18`

Minimum duration:

- 2.0 seconds

Penalty:

- 1.5 marks per second

## 10. Models and CV/ML components used

This project contains both actively used models and older legacy models still present in the repository.

### Actively used in the current browser-to-Flask flow

#### A. OpenCV Haar Cascade

File:

- `Haarcascades/haarcascade_frontalface_default.xml`

Used for:

- face presence detection
- multiple face detection
- face cropping during profile capture

Why it is used:

- lightweight
- fast
- simple CPU-based face detection

Limitations:

- less accurate than modern deep face detectors
- sensitive to pose, lighting, and occlusion

#### B. YOLOv8n

File:

- `yolov8n.pt`

Loaded in:

- `utils.py`

Library:

- `ultralytics`

Used for:

- object detection in webcam frames
- specifically `cell phone` detection in the current live app

Potentially supported by the model:

- COCO object classes, because the project includes `utils/coco.txt`

Important implementation note:

- In the active `app.py` flow, only `cell phone` triggers a violation.
- In older utility code, other device classes such as `remote` and `laptop` are also checked.

#### C. `face_recognition` library

Library stack:

- `face_recognition`
- `dlib` underneath in normal setups

Used for:

- encoding registered profile faces
- matching captured/observed faces against known student profiles

Main class:

- `FaceRecognition` in `utils.py`

Current use in live flow:

- Face encoding is definitely used during profile confirmation (`/confirmFaceInput`).
- Full continuous face-identity verification during the exam exists in `utils.py`, but it is not wired into the current browser monitoring endpoints.

#### D. `face_recognition_stub.py`

Fallback used when `face_recognition` import fails.

Purpose:

- lets the app run in environments where `dlib` cannot be compiled/installed

Behavior:

- uses OpenCV Haar cascade for face location
- creates dummy 128-dimensional face vectors

Implication:

- the app can keep running, but real identity verification quality is much weaker in stub mode

### Present in the repository but mostly legacy/unwired in the current web flow

#### E. MediaPipe Face Mesh / Face Detection

Library:

- `mediapipe`

Used in `utils.py` for:

- head movement estimation
- multi-face detection in older paths

Legacy capabilities:

- `headMovmentDetection()`
- `MTOP_Detection()`

Current status:

- these functions exist, but the current web exam monitoring endpoints do not call them
- the active app now uses simpler frame-based checks in `app.py`

#### F. PyAudio recorder pipeline

Used in `utils.py` for:

- old continuous noise recording and WAV evidence generation

Current status:

- class `Recorder` still exists
- instance `a = Recorder()` is created at import time
- but the current browser monitoring flow does not use this recorder
- active audio detection now comes from browser RMS/peak values instead

#### G. Screen/window monitoring via PyAutoGUI and PyGetWindow

Used in `utils.py` for:

- checking whether the exam window lost focus
- capturing screenshots

Current status:

- helper code still exists
- not called by the current browser monitoring endpoints

#### H. Legacy face verification during exam

Used in `utils.py`:

- `FaceRecognition.run_recognition()`
- `faceDetectionRecording(...)`

Current status:

- logic exists for continuous identity verification and recording video evidence
- current web app does not invoke that continuous recognition loop

## 11. How face registration works

The profile capture flow is:

1. Student captures an image on the face input page
2. Browser sends the image to `/saveFaceInput`
3. Backend decodes the base64 image
4. Backend crops it using `crop_face_portrait()`
5. Backend saves it with a generated name:
   - `<StudentName>_<ResultId>Profile.jpg`
6. File is moved into `static/Profiles`
7. `/confirmFaceInput` calls `utils.fr.encode_faces()`
8. The app checks whether that saved filename appears in `known_face_names`

If the face encoder cannot extract a face from the profile image:

- the student is redirected back to retake the photo

Important note:

- This step validates that the registration photo contains a detectable face.
- It does not fully enforce continuous identity verification during the live exam in the current implementation.

## 12. How violations are created

The app does not create a violation for every single sample. It groups continuous suspicious behavior into one event.

### Event lifecycle

For each event type:

1. Detection becomes true
2. Event start time is stored in `monitor_session["active_events"]`
3. Each new frame can update the last evidence frame
4. Detection later becomes false
5. Duration is measured
6. If duration is above the configured minimum:
   - a violation entry is created
   - an evidence image may be saved
   - penalty marks are computed

### Evidence saving

`save_violation_snapshot(...)` saves a JPEG image to:

- `static/ViolationImages/`

Filename pattern:

- `<event_prefix>_<timestamp>.jpg`

Examples:

- `face_absence_20260405_084345.jpg`
- `mobile_phone_20260405_001915.jpg`

Audio events do not currently save an image.

## 13. Keyboard shortcut detection

When the exam page is opened, `app.py` calls:

- `keyboard.hook(utils.shortcut_handler)`

`utils.shortcut_handler` watches for combinations such as:

- `Ctrl+C`
- `Ctrl+V`
- `Ctrl+A`
- `Ctrl+X`
- `Alt+Tab`
- `Alt+Shift+Tab`
- `Win+Tab`
- `Ctrl+Esc`
- `Ctrl+Alt+Del`
- `Print Screen`
- `Ctrl+T`
- `Ctrl+W`
- `Ctrl+Z`
- function keys like `F1`, `F2`, `F3`

These are accumulated in `utils.shorcuts`.

At exam submission time, a single summary violation is written:

- name includes the unique shortcut list
- time field stores the count as text
- mark is `1.5 * len(utils.shorcuts)`

Important implementation note:

- The count is based on every captured press, even if the display string shows only distinct shortcut names.

## 14. Result calculation logic

At submission time, the backend computes:

### Exam score

Frontend sends:

- number of correct answers

Backend computes:

- `totalMark = floor(correctAnswers * 6.6667)`

Because the quiz has 15 questions, this scales the raw correct count approximately to 100.

### Trust score

`utils.get_TrustScore(result_id)` sums all `Mark` values in `violation.json` for that result ID.

Then the app stores:

- `TrustScore = max(100 - totalPenalty, 0)`

So:

- higher penalty means lower trust score
- `100` means no violations
- `0` means heavy violation total

### Final status rules

1. If total penalty is `>= 30`
   - status becomes `Fail(Cheating)`
2. Else if exam score `< 50`
   - status becomes `Fail`
3. Else
   - status becomes `Pass`

This means cheating failure has priority over academic score failure.

## 15. Data storage format

### 15.1 MySQL data

MySQL stores student accounts in table `students`.

Columns:

- `ID`
- `Name`
- `Email`
- `Password`
- `Role`

Roles used:

- `STUDENT`
- `ADMIN`

### 15.2 `result.json`

Each object represents one exam attempt.

Fields:

- `Id`: numeric result ID
- `Name`: student name
- `TotalMark`: scaled exam score
- `TrustScore`: 0 to 100 after subtracting penalties
- `Status`: `Pass`, `Fail`, or `Fail(Cheating)`
- `Date`: exam date
- `StId`: student ID from MySQL
- `Link`: saved profile image name

### 15.3 `violation.json`

Each object represents one logged violation event.

Fields:

- `Name`: violation name
- `Time`: start timestamp or summary count text
- `Duration`: duration string
- `Mark`: penalty value
- `Link`: evidence filename if present
- `RId`: result ID to which the violation belongs

## 16. Health check and operational helpers

The route:

- `/health/db`

checks whether MySQL is reachable.

Success response returns:

- host
- port
- database

This is useful for deployment debugging.

## 17. Important implementation realities and caveats

### A. The repository contains both current and older architectures

The live web app mostly relies on:

- browser-side capture
- server-side lightweight frame analysis in `app.py`

But `utils.py` still contains a much larger older pipeline for:

- head movement recording
- voice recording with PyAudio
- screen capture monitoring
- more detailed video evidence generation

Most of that older pipeline is not currently connected to the active browser routes.

### B. Face identity verification is only partially active

The project does register and encode a profile face.

However, in the current active exam monitoring flow, the server mainly checks:

- face present/not present
- one face vs multiple faces
- face roughly centered or not

It does not continuously run full identity matching against the registered profile through the `/monitor/frame` endpoint.

### C. Audio detection is threshold-based, not speech-recognition based

Despite the project description mentioning speech/noise detection, the current active web flow does not perform speech-to-text or speaker identification.

It only checks whether microphone amplitude appears suspicious.

### D. Results are split across database and JSON

Student accounts are in MySQL, but exam attempts and violations are in JSON files.

This works for a small local project, but it creates limitations:

- concurrent writes are risky
- multi-user production deployment is harder
- reporting is split across storage systems

### E. Several globals make the app effectively single-process/single-instance oriented

Examples:

- `studentInfo`
- `profileName`
- `monitor_session`
- `utils.shorcuts`

This means the current design is best suited for local/demo usage rather than many simultaneous users on a production server.

### F. Passwords are stored in plain text

The current code does not hash passwords before storing them in MySQL.

That is a security issue and should be changed before any real deployment.

## 18. End-to-end runtime summary

A concise full-flow summary:

1. Flask starts and connects to MySQL.
2. YOLO model and face-recognition utilities are loaded.
3. Student logs in.
4. Student captures a profile face image.
5. The image is stored in `static/Profiles`.
6. The app verifies that a face can be encoded from that image.
7. Student starts the quiz.
8. Backend opens a monitoring session and reserves a result ID.
9. Browser periodically sends webcam frames and audio levels.
10. Backend checks for:
    - no face
    - multiple faces
    - looking away
    - mobile phone
    - suspicious background audio
11. Keyboard shortcut presses are collected separately.
12. Student completes the quiz and submits answers.
13. Backend finalizes active events and writes them to `violation.json`.
14. Backend computes total exam mark and penalty sum.
15. Backend derives trust score and pass/fail/cheating status.
16. Final exam result is written to `result.json`.
17. Admin can later inspect results and linked evidence.

## 19. Technology stack summary

- Python
- Flask
- Flask-MySQLdb
- MySQL
- OpenCV
- Ultralytics YOLOv8
- face_recognition / dlib
- MediaPipe
- NumPy
- keyboard
- PyAutoGUI
- PyGetWindow
- PyAudio
- HTML/CSS/JavaScript
- WebRTC-style media access through `getUserMedia`
- Web Audio API

## 20. If you want to understand the code quickly, read in this order

1. `app.py`
2. `static/js/script.js`
3. `static/js/exam_monitor.js`
4. `utils.py`
5. `questions.js`
6. `init_db.sql`
7. `result.json` and `violation.json`

That reading order gives the clearest picture of the live system first, then the older helper pipeline.
