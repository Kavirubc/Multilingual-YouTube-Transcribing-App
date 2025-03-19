document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('youtubeForm');
    const resultDiv = document.getElementById('result');
    const transcriptContent = document.getElementById('transcript-content');
    const downloadBtn = document.getElementById('downloadBtn');
    const spinner = document.getElementById('spinner');
    const errorMessage = document.getElementById('error-message');

    form.addEventListener('submit', async function (e) {
        e.preventDefault();

        const youtubeUrl = document.getElementById('youtubeUrl').value;

        // Reset UI
        resultDiv.style.display = 'none';
        errorMessage.style.display = 'none';
        errorMessage.textContent = '';
        spinner.style.display = 'block';

        try {
            const response = await fetch('/convert', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ youtubeUrl }),
            });

            spinner.style.display = 'none';

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Failed to convert video');
            }

            const data = await response.json();
            transcriptContent.textContent = data.transcript;
            resultDiv.style.display = 'block';

            // Set up download button
            downloadBtn.onclick = function () {
                window.location.href = `/download/${data.fileId}`;
            };
        } catch (error) {
            errorMessage.textContent = `Error: ${error.message}`;
            errorMessage.style.display = 'block';
            spinner.style.display = 'none';
        }
    });
});
