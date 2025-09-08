window.onload = () => {
    const consoleOutput = document.getElementById('console-output');

    if (consoleOutput) {
        const observer = new MutationObserver(() => {
            consoleOutput.scrollTop = consoleOutput.scrollHeight;
        });

        observer.observe(consoleOutput, {
            childList: true,
            subtree: true,
        });
    }
};