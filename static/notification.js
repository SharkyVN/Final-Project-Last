async function loadNotifications() {
    try {
        const res = await fetch("/notification");
        const data = await res.json();
        if (!data.ok) return;

        const count = data.count;
        
        const dot = document.getElementById("notif-dot");
        const countSpan= document.getElementById("notif-count");
        const bell = document.getElementById("notif-bell");
        
        if (!dot || !countSpan || !bell) return;

        if (count > 0) {
            dot.classList.remove("d-none");
            countSpan.textContent = count;
            bell.classList.add("notif-pulse");
        } else {
            dot.classList.add("d-none");
            bell.classList.remove("notif-pulse");
            countSpan.textContent = "";
        }

    } catch (err) {
        console.error("Notification error:", err);
    }
}

/* load imediately*/
loadNotifications();

/* auto-refresh per 60s*/
setInterval(loadNotifications,60000)