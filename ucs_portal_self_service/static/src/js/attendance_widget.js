// ESS Portal - Live Clock & Elapsed Timer
// Uses server check_in Unix timestamp so client computes real elapsed from Date.now()

document.addEventListener("DOMContentLoaded", function () {
    var dataEl  = document.getElementById('ess_js_data');
    var clockEl = document.getElementById('ess_live_clock');
    var dateEl  = document.getElementById('ess_today_label');

    if (!clockEl || !dataEl) return;

    var isCheckedIn   = dataEl.getAttribute('data-checked-in') === '1';
    var checkInUnix   = parseInt(dataEl.getAttribute('data-checkin-unix') || '0', 10); // UTC seconds

    var DAYS   = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    function pad(n) {
        return n >= 10 ? String(n) : '0' + String(n);
    }

    function secsToHMS(totalSecs) {
        var s = Math.max(0, totalSecs);
        var h = Math.floor(s / 3600);
        var m = Math.floor((s % 3600) / 60);
        var sec = s % 60;
        return pad(h) + ':' + pad(m) + ':' + pad(sec);
    }

    function updateDateLabel() {
        if (!dateEl) return;
        var now = new Date();
        dateEl.textContent = DAYS[now.getDay()] + ', ' + now.getDate() + ' ' + MONTHS[now.getMonth()] + ' ' + now.getFullYear();
    }

    updateDateLabel();
    setInterval(updateDateLabel, 30000);

    if (isCheckedIn && checkInUnix > 0) {
        // --- CHECKED IN: show elapsed time ticking up ---
        function tickElapsed() {
            var nowUnix = Math.floor(Date.now() / 1000); // client UTC seconds
            var elapsed = nowUnix - checkInUnix;
            if (elapsed < 0) elapsed = 0;
            clockEl.textContent = secsToHMS(elapsed);

            // Also update today hours display live
            var hoursEl = document.getElementById('ess_hours_display');
            if (hoursEl) {
                var h = Math.floor(elapsed / 3600);
                var m = Math.floor((elapsed % 3600) / 60);
                var s = elapsed % 60;
                hoursEl.innerHTML = pad(h) + ':' + pad(m) + ':' + pad(s) + ' <small>elapsed</small>';
            }
        }
        tickElapsed();
        setInterval(tickElapsed, 1000);

    } else {
        // --- NOT CHECKED IN: show current real time ---
        function tickClock() {
            var now = new Date();
            clockEl.textContent = pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
        }
        tickClock();
        setInterval(tickClock, 1000);
    }
});
