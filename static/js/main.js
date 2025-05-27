window.fbAsyncInit = function() {
    FB.init({
        appId      : '10078966155483125',
        cookie     : true,
        xfbml      : true,
        version    : 'v17.0'
    });
};

function checkLoginState() {
    FB.getLoginStatus(function(response) {
        if(response.status === 'connected') {
            const accessToken = response.authResponse.accessToken;
            const userID = response.authResponse.userID;

            // Надсилаємо токен на сервер
            fetch('/login/facebook', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ accessToken: accessToken, userID: userID })
            }).then(r => r.json()).then(data => {
                alert(data.message || data.error);
            });
        } else {
            alert('Будь ласка, увійдіть у Facebook');
        }
    });
}

const history = [];

async function startTest() {
    const serverId = document.getElementById('server-select').value;
    const sizeMb = parseInt(document.getElementById('size-input').value);
    const ttl = parseInt(document.getElementById('ttl-input').value);

    const resultArea = document.getElementById('result-area');
    resultArea.textContent = `Тестуємо на сервері: ${serverId} з файлом розміром ${sizeMb} МБ...\nПочинаємо тест Upload...`;

    const fakeFile = new Blob([new Uint8Array(sizeMb * 1024 * 1024)], { type: 'application/octet-stream' });

    const uploadForm = new FormData();
    uploadForm.append('file', fakeFile, 'upload_test.bin');
    uploadForm.append('size_mb', sizeMb);
    uploadForm.append('server_id', serverId);

    const uploadStart = performance.now();
    const uploadResponse = await fetch('/upload', { method: 'POST', body: uploadForm });
    const uploadEnd = performance.now();

    if (!uploadResponse.ok) {
        resultArea.textContent = 'Помилка при upload тесті.';
        return;
    }

    const uploadData = await uploadResponse.json();
    resultArea.textContent += `\nUpload: ${uploadData.speed} Mbps, час: ${(uploadEnd - uploadStart)/1000} с\nПочинаємо тест Download...`;

    const downloadStart = performance.now();
    const downloadResponse = await fetch(`/download?size_mb=${sizeMb}&server_id=${serverId}`);
    const downloadEnd = performance.now();

    if (!downloadResponse.ok) {
        resultArea.textContent += '\nПомилка при download тесті.';
        return;
    }

    await downloadResponse.blob();

    const downloadDuration = (downloadEnd - downloadStart) / 1000;
    const downloadSpeed = (sizeMb * 8) / downloadDuration;

    resultArea.textContent += `\nDownload: ${downloadSpeed.toFixed(2)} Mbps, час: ${downloadDuration.toFixed(2)} с\n\nЗберігаємо результат...`;

    const saveResponse = await fetch('/save_result', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            server_id: serverId,
            upload: uploadData.speed,
            download: downloadSpeed,
            upload_time: (uploadEnd - uploadStart)/1000,
            download_time: downloadDuration,
            ttl: ttl
        })
    });

    if (!saveResponse.ok) {
        resultArea.textContent += '\nПомилка при збереженні результату.';
        return;
    }

    const saveData = await saveResponse.json();
    resultArea.textContent += `\nРезультат збережено. Переглянути: ${saveData.link}`;

    history.push({
        date: new Date().toLocaleString(),
        server: serverId,
        upload: uploadData.speed,
        download: downloadSpeed.toFixed(2),
        link: saveData.link
    });
    updateHistory();

    const statsResponse = await fetch('/stats');
    if (statsResponse.ok) {
        const stats = await statsResponse.json();
        const statsArea = document.getElementById('stats-area');
        statsArea.textContent = `Всього тестів: ${stats.total_tests}
Результатів доступно зараз: ${stats.available_now}
Результати, які перестануть бути доступними протягом години: ${stats.expiring_in_hour}
Результати, які перестануть бути доступними протягом доби: ${stats.expiring_in_day}

За останню годину:
Середня швидкість Upload: ${stats.avg_upload_hour} Mbps
Максимальна швидкість Upload: ${stats.max_upload_hour} Mbps
Середня швидкість Download: ${stats.avg_download_hour} Mbps
Максимальна швидкість Download: ${stats.max_download_hour} Mbps

За останню добу:
Середня швидкість Upload: ${stats.avg_upload_day} Mbps
Максимальна швидкість Upload: ${stats.max_upload_day} Mbps
Середня швидкість Download: ${stats.avg_download_day} Mbps
Максимальна швидкість Download: ${stats.max_download_day} Mbps`;
    }
}

async function startTestRandom() {
    const sizeMb = parseInt(document.getElementById('size-input').value);
    const ttl = parseInt(document.getElementById('ttl-input').value);

    const serverSelect = document.getElementById('server-select');
    const options = Array.from(serverSelect.options);
    const randomOption = options[Math.floor(Math.random() * options.length)];
    const randomServerId = randomOption.value;

    serverSelect.value = randomServerId;
    await startTest();
}

function updateHistory() {
    const historyArea = document.getElementById('history-area');
    historyArea.innerHTML = '';
    for (const item of history) {
        const div = document.createElement('div');
        div.innerHTML = `Дата: ${item.date} | Сервер: ${item.server} | Upload: ${item.upload} Mbps | Download: ${item.download} Mbps | <a href="${item.link}" target="_blank">Переглянути результат</a>`;
        historyArea.appendChild(div);
    }
}

// Google token → надсилається на бекенд
function handleGoogleCredentialResponse(response) {
    fetch('/login/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: response.credential })
    })
    .then(res => res.json())
    .then(data => {
        if (data.message) {
            alert(data.message);
            window.location.reload();
        } else {
            alert(data.error || 'Помилка входу через Google');
        }
    });
}

// Функція для Google Login
function googleLogin() {
    google.accounts.id.initialize({
        client_id: '161637199681-cj1eqhcbbdur3rbmikk92uk7b0rlrc5p.apps.googleusercontent.com',
        callback: handleGoogleResponse
    });
    google.accounts.id.prompt();
}

function facebookLogin() {
    FB.login(function (response) {
        if (response.authResponse) {
            const accessToken = response.authResponse.accessToken;

            // Надіслати токен на бекенд для авторизації
            fetch('/login/facebook', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ token: accessToken })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // 🔄 Оновити сторінку після успішного логіну
                    location.reload();
                } else {
                    alert('Помилка авторизації через Facebook');
                }
            })
            .catch(err => {
                console.error('Помилка при відправці токена на сервер:', err);
                alert('Серверна помилка при авторизації через Facebook');
            });
        } else {
            alert('Facebook авторизація не вдалася або була скасована');
        }
    }, { scope: 'public_profile,email' });
}


function logout() {
    fetch('/logout', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.redirect) {
            window.location.href = data.redirect;
        }
    })
    .catch(error => {
        console.error('Помилка при виході:', error);
        alert('Сталася помилка при спробі вийти');
    });
}
