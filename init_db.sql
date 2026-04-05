CREATE DATABASE IF NOT EXISTS examproctordb
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE examproctordb;

CREATE TABLE IF NOT EXISTS students (
    ID INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(255) NOT NULL,
    Email VARCHAR(255) NOT NULL UNIQUE,
    Password VARCHAR(255) NOT NULL,
    Role VARCHAR(50) NOT NULL DEFAULT 'STUDENT'
);

INSERT INTO students (Name, Email, Password, Role)
SELECT 'Admin', 'admin@example.com', 'admin123', 'ADMIN'
WHERE NOT EXISTS (
    SELECT 1 FROM students WHERE Role = 'ADMIN'
);
