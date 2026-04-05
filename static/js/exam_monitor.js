(function () {
    const video = document.getElementById("monitorVideo");
    const canvas = document.getElementById("monitorCanvas");
    const statusText = document.getElementById("monitorStatus");
    const faceText = document.getElementById("monitorFace");
    const peopleText = document.getElementById("monitorPeople");
    const poseText = document.getElementById("monitorPose");
    const phoneText = document.getElementById("monitorPhone");
    const audioText = document.getElementById("monitorAudio");

    let stream = null;
    let intervalId = null;
    let audioIntervalId = null;
    let running = false;
    let audioContext = null;
    let analyser = null;
    let audioData = null;

    function setStatus(message) {
        if (statusText) {
            statusText.textContent = message;
        }
    }

    function updateIndicators(analysis) {
        if (!analysis) {
            return;
        }
        faceText.textContent = analysis.face_absent ? "Face: not detected" : "Face: detected";
        peopleText.textContent = analysis.multiple_faces ? "People: multiple faces detected" : `People: ${analysis.face_count} visible`;
        poseText.textContent = analysis.looking_away ? "Attention: looking away" : "Attention: focused";
        phoneText.textContent = analysis.phone_detected ? "Phone: detected" : "Phone: clear";
    }

    function updateAudioIndicator(analysis) {
        if (!analysis || !audioText) {
            return;
        }
        audioText.textContent = analysis.suspicious_audio ? "Audio: background voice/noise detected" : "Audio: clear";
    }

    async function ensureCamera() {
        if (stream) {
            return true;
        }
        try {
            stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 960 },
                    height: { ideal: 540 },
                    facingMode: "user"
                },
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            video.srcObject = stream;
            await video.play();
            const audioTracks = stream.getAudioTracks();
            if (audioTracks.length > 0) {
                audioContext = new (window.AudioContext || window.webkitAudioContext)();
                const source = audioContext.createMediaStreamSource(new MediaStream(audioTracks));
                analyser = audioContext.createAnalyser();
                analyser.fftSize = 2048;
                audioData = new Float32Array(analyser.fftSize);
                source.connect(analyser);
            }
            setStatus("Camera active. Monitoring will sample frames during the quiz.");
            return true;
        } catch (error) {
            setStatus("Camera or microphone access failed. Allow permission to enable monitoring.");
            return false;
        }
    }

    async function sendFrame() {
        if (!stream || video.videoWidth === 0 || video.videoHeight === 0) {
            return;
        }
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const context = canvas.getContext("2d");
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const image = canvas.toDataURL("image/jpeg", 0.75);

        try {
            const response = await fetch("/monitor/frame", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ image })
            });
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.message || "Monitoring frame failed.");
            }
            updateIndicators(result.analysis);
        } catch (error) {
            setStatus(error.message || "Monitoring frame failed.");
        }
    }

    function sampleAudio() {
        if (!analyser || !audioData) {
            return null;
        }
        analyser.getFloatTimeDomainData(audioData);
        let sumSquares = 0;
        let peak = 0;
        for (let i = 0; i < audioData.length; i += 1) {
            const value = audioData[i];
            sumSquares += value * value;
            peak = Math.max(peak, Math.abs(value));
        }
        return {
            rms: Math.sqrt(sumSquares / audioData.length),
            peak
        };
    }

    async function sendAudioLevel() {
        const audioSample = sampleAudio();
        if (!audioSample) {
            return;
        }
        try {
            const response = await fetch("/monitor/audio", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(audioSample)
            });
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.message || "Monitoring audio failed.");
            }
            updateAudioIndicator(result.analysis);
        } catch (error) {
            setStatus(error.message || "Monitoring audio failed.");
        }
    }

    async function start() {
        if (running) {
            return;
        }
        const cameraReady = await ensureCamera();
        if (!cameraReady) {
            return;
        }
        running = true;
        setStatus("Monitoring in progress.");
        await sendFrame();
        await sendAudioLevel();
        intervalId = window.setInterval(sendFrame, 2000);
        audioIntervalId = window.setInterval(sendAudioLevel, 1500);
    }

    function stop() {
        running = false;
        if (intervalId) {
            window.clearInterval(intervalId);
            intervalId = null;
        }
        if (audioIntervalId) {
            window.clearInterval(audioIntervalId);
            audioIntervalId = null;
        }
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
        if (video) {
            video.srcObject = null;
        }
        if (audioContext) {
            audioContext.close();
            audioContext = null;
        }
        analyser = null;
        audioData = null;
        setStatus("Monitoring stopped.");
    }

    window.examMonitor = {
        start,
        stop
    };
})();
