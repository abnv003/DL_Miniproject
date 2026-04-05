"""
Stub implementation of face_recognition module for environments where dlib compilation fails.
Provides basic functionality to allow the app to run without dlib dependency.
"""

import cv2
import numpy as np

def load_image_file(file_path):
    """Load an image file and return it as a numpy array."""
    image = cv2.imread(file_path)
    if image is None:
        raise FileNotFoundError(f"Could not load image: {file_path}")
    # Convert BGR to RGB for compatibility
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

def face_encodings(image, face_locations=None):
    """
    Generate face encodings using a simplified approach.
    Returns dummy encoding vectors for testing purposes.
    """
    if face_locations is None:
        # If no face locations provided, detect them first
        face_locations = face_locations_cascade(image)
    
    encodings = []
    for face_location in face_locations:
        # Generate a dummy 128D encoding vector (normally 128D from dlib)
        # Using image data to create a somewhat unique encoding
        top, right, bottom, left = face_location
        face_roi = image[top:bottom, left:right]
        
        # Create a hash-like encoding from the face region
        if face_roi.size == 0:
            # If ROI is empty, use random encoding
            encoding = np.random.rand(128)
        else:
            # Use mean and std of face region as basis for encoding
            face_flat = face_roi.flatten().astype(float)
            # Normalize and create 128D vector
            encoding = np.concatenate([
                np.array([np.mean(face_flat), np.std(face_flat)]),
                np.random.rand(126)  # Fill rest with pseudo-random data
            ])
        encodings.append(encoding)
    
    return np.array(encodings)

def face_locations(image, model='hog'):
    """
    Detect face locations in an image using OpenCV Haar Cascade.
    Returns list of face locations as (top, right, bottom, left) tuples.
    """
    return face_locations_cascade(image)

def face_locations_cascade(image):
    """Helper function using Haar Cascade for face detection."""
    # Convert to grayscale if needed
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        gray = image
    
    # Load Haar Cascade classifier
    cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    face_cascade = cv2.CascadeClassifier(cascade_path)
    
    # Detect faces
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.3, minNeighbors=5, minSize=(30, 30))
    
    # Convert to (top, right, bottom, left) format
    face_locations_list = []
    for (x, y, w, h) in faces:
        top = y
        right = x + w
        bottom = y + h
        left = x
        face_locations_list.append((top, right, bottom, left))
    
    return face_locations_list

def compare_faces(known_face_encodings, face_encoding, tolerance=0.6):
    """
    Compare a face encoding against a list of known face encodings.
    Returns list of booleans indicating matches.
    """
    distances = face_distance(known_face_encodings, face_encoding)
    return list(distances <= tolerance)

def face_distance(face_encodings, face_to_compare):
    """
    Calculate face distances (Euclidean distance in encoding space).
    Returns array of distances.
    """
    if len(face_encodings) == 0:
        return np.array([])
    
    # Use Euclidean distance
    distances = np.linalg.norm(face_encodings - face_to_compare, axis=1)
    return distances
