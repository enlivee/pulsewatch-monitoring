// PulseWatch Frontend Client
document.addEventListener("DOMContentLoaded", () => {
    // Initialize Lucide icons
    if (window.lucide) {
        lucide.createIcons();
    }

    // Auto-refresh timer for live dashboard
    let refreshSeconds = 15;
    let currentCountdown = refreshSeconds;
    const countdownEl = document.getElementById("refresh-countdown");

    if (countdownEl) {
        setInterval(() => {
            currentCountdown--;
            if (currentCountdown <= 0) {
                currentCountdown = refreshSeconds;
                refreshDashboardData();
            }
            countdownEl.textContent = `${currentCountdown}с`;
        }, 1000);
    }
});

// Toast notification helper
function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    const bgClass = type === "success" 
        ? "bg-emerald-600 text-white" 
        : type === "error" 
        ? "bg-rose-600 text-white" 
        : "bg-sky-600 text-white";

    toast.className = `flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg transition-all duration-300 transform translate-y-2 opacity-0 text-sm font-medium ${bgClass}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" class="opacity-70 hover:opacity-100 ml-2">&times;</button>
    `;

    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.remove("translate-y-2", "opacity-0");
    }, 10);

    setTimeout(() => {
        toast.classList.add("opacity-0", "translate-y-2");
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Modal open/close helpers
function openModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.remove("hidden");
        el.classList.add("flex");
    }
}

function closeModal(id) {
    const el = document.getElementById(id);
    if (el) {
        el.classList.add("hidden");
        el.classList.remove("flex");
    }
}

// Trigger manual check
async function checkServiceNow(serviceId, btn) {
    const originalContent = btn ? btn.innerHTML : null;
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="animate-spin inline-block mr-1">↻</span> Проверка...`;
    }

    try {
        const resp = await fetch(`/api/services/${serviceId}/check`, { method: "POST" });
        if (!resp.ok) throw new Error("Не удалось выполнить проверку");
        const data = await resp.json();
        
        showToast(`Сервис проверен: ${data.status} (${data.response_time_ms ? data.response_time_ms + ' мс' : data.error_message || 'OK'})`, data.status === "UP" ? "success" : "error");
        setTimeout(() => window.location.reload(), 600);
    } catch (err) {
        showToast(err.message, "error");
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalContent;
        }
    }
}

// Pause service
async function togglePauseService(serviceId, isCurrentlyActive) {
    const endpoint = isCurrentlyActive ? `/api/services/${serviceId}/pause` : `/api/services/${serviceId}/resume`;
    try {
        const resp = await fetch(endpoint, { method: "POST" });
        if (!resp.ok) throw new Error("Ошибка изменения состояния");
        showToast(isCurrentlyActive ? "Мониторинг приостановлен" : "Мониторинг возобновлен");
        setTimeout(() => window.location.reload(), 500);
    } catch (err) {
        showToast(err.message, "error");
    }
}

// Delete service
async function deleteService(serviceId, serviceName) {
    if (!confirm(`Вы действительно хотите удалить сервис "${serviceName}" и всю историю его проверок?`)) {
        return;
    }
    try {
        const resp = await fetch(`/api/services/${serviceId}`, { method: "DELETE" });
        if (!resp.ok) throw new Error("Ошибка удаления сервиса");
        showToast(`Сервис "${serviceName}" успешно удален`);
        setTimeout(() => window.location.href = "/", 600);
    } catch (err) {
        showToast(err.message, "error");
    }
}

// Refresh dashboard data dynamically
async function refreshDashboardData() {
    try {
        // Fetch dashboard stats
        const statsResp = await fetch("/api/stats/dashboard");
        if (statsResp.ok) {
            const stats = await statsResp.json();
            const totalEl = document.getElementById("stat-total");
            const upEl = document.getElementById("stat-up");
            const downEl = document.getElementById("stat-down");
            const uptimeEl = document.getElementById("stat-uptime");
            const latEl = document.getElementById("stat-latency");

            if (totalEl) totalEl.textContent = stats.total_services;
            if (upEl) upEl.textContent = stats.up_count;
            if (downEl) downEl.textContent = stats.down_count;
            if (uptimeEl) uptimeEl.textContent = `${stats.avg_uptime_24h}%`;
            if (latEl && stats.avg_response_time_ms) latEl.textContent = `${stats.avg_response_time_ms} мс`;
        }

        // If on home dashboard, reload service cards or page if changes occurred
        const liveIndicator = document.getElementById("live-pulse");
        if (liveIndicator) {
            liveIndicator.classList.add("scale-125");
            setTimeout(() => liveIndicator.classList.remove("scale-125"), 300);
        }
    } catch (err) {
        console.error("Auto-refresh error:", err);
    }
}

// Form submit: Add Service
async function handleCreateServiceSubmit(event) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    const payload = {
        name: formData.get("name"),
        url: formData.get("url"),
        description: formData.get("description") || null,
        category: formData.get("category") || "Общие",
        check_type: formData.get("check_type") || "HTTP",
        method: formData.get("method") || "GET",
        expected_status: parseInt(formData.get("expected_status")) || 200,
        timeout_seconds: parseFloat(formData.get("timeout_seconds")) || 10.0,
        interval_seconds: parseInt(formData.get("interval_seconds")) || 30,
        keyword: formData.get("keyword") || null,
        tags: formData.get("tags") || null,
        is_active: true
    };

    try {
        const resp = await fetch("/api/services", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const errData = await resp.json();
            throw new Error(errData.detail || "Ошибка при создании сервиса");
        }

        showToast("Сервис успешно добавлен и поставлен на мониторинг!");
        closeModal("modal-add-service");
        form.reset();
        setTimeout(() => window.location.reload(), 600);
    } catch (err) {
        showToast(err.message, "error");
    }
}

// Form submit: Edit Service
async function handleEditServiceSubmit(event, serviceId) {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);

    const payload = {
        name: formData.get("name"),
        url: formData.get("url"),
        description: formData.get("description") || null,
        category: formData.get("category") || "Общие",
        check_type: formData.get("check_type") || "HTTP",
        method: formData.get("method") || "GET",
        expected_status: parseInt(formData.get("expected_status")) || 200,
        timeout_seconds: parseFloat(formData.get("timeout_seconds")) || 10.0,
        interval_seconds: parseInt(formData.get("interval_seconds")) || 30,
        keyword: formData.get("keyword") || null,
        tags: formData.get("tags") || null,
    };

    try {
        const resp = await fetch(`/api/services/${serviceId}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (!resp.ok) {
            const errData = await resp.json();
            throw new Error(errData.detail || "Ошибка при обновлении сервиса");
        }

        showToast("Сервис успешно обновлен!");
        closeModal("modal-edit-service");
        setTimeout(() => window.location.reload(), 600);
    } catch (err) {
        showToast(err.message, "error");
    }
}
