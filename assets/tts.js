// assets/tts.js

function setupTTS() {
    const storeNode = document.getElementById('description-store');
    const runButton = document.getElementById('run-button');
    let isAudioUnlocked = false;

    // This check is a safeguard, though the interval should ensure these exist.
    if (!storeNode || !runButton) {
        console.error("TTS setup failed: required components not found.");
        return;
    }

    // --- Audio Unlock Function ---
    const unlockAudio = () => {
        if (!isAudioUnlocked) {
            window.speechSynthesis.speak(new SpeechSynthesisUtterance(""));
            isAudioUnlocked = true;
            console.log("Audio context unlocked.");
            runButton.removeEventListener('click', unlockAudio);
        }
    };
    runButton.addEventListener('click', unlockAudio);

    // --- Main Observer Logic ---
    const observer = new MutationObserver(mutations => {
        mutations.forEach(mutation => {
            const newText = mutation.target.textContent;
            if (newText && newText !== "No description yet.") {
                const utterance = new SpeechSynthesisUtterance(newText);
                utterance.rate = 1.1;
                window.speechSynthesis.cancel();
                window.speechSynthesis.speak(utterance);
            }
        });
    });

    observer.observe(storeNode, { childList: true });
    console.log("TTS observer is active.");
}


// --- NEW: Waiter/Polling Logic ---
// Dash loads components dynamically. Instead of window.onload, we'll
// poll the document until the components we need are available.
const componentWaiter = setInterval(() => {
    const storeNode = document.getElementById('description-store');
    const runButton = document.getElementById('run-button');

    // If both components are loaded into the page, we can proceed.
    if (storeNode && runButton) {
        console.log("All components found. Setting up TTS.");
        // Stop polling.
        clearInterval(componentWaiter);
        // Run the main setup function.
        setupTTS();
    }
}, 100); // Check every 100 milliseconds.