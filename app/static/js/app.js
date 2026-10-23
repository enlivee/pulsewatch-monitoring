// PulseWatch Frontend Client: Lanterns Edition
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
        ? "bg-emerald-950 border border-emerald-500/70 text-emerald-300 shadow-[0_0_20px_rgba(0,255,136,0.3)]" 
        : type === "error" 
        ? "bg-rose-950 border border-rose-500/70 text-rose-300 shadow-[0_0_20px_rgba(244,63,94,0.3)]" 
        : "bg-[#07160d] border border-emerald-700/60 text-slate-200";

    toast.className = `flex items-center gap-3 px-4 py-3 rounded-xl shadow-2xl transition-all duration-300 transform translate-y-2 opacity-0 text-xs font-semibold uppercase tracking-wider font-mono ${bgClass}`;
    toast.innerHTML = `
        <span class="flex-1">${message}</span>
        <button onclick="this.parentElement.remove()" class="opacity-70 hover:opacity-100 ml-2 text-sm">&times;</button>
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

// Helper to render status badge HTML
function renderStatusBadge(status, isActive) {
    if (!isActive) {
        return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-900 text-slate-400 border border-slate-800">Спящий</span>`;
    }
    if (status === "UP") {
        return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-[#041a0d] text-emerald-400 border border-emerald-500/60 shadow-[0_0_12px_rgba(0,255,136,0.25)]"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400 lantern-pulse"></span> 200 OK</span>`;
    }
    if (status === "DOWN") {
        return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-rose-950/80 text-rose-400 border border-rose-800/80"><span class="w-1.5 h-1.5 rounded-full bg-rose-400 pulse-down"></span> Сбой</span>`;
    }
    if (status === "DEGRADED") {
        return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-amber-950/80 text-amber-400 border border-amber-800/80">Замедлен</span>`;
    }
    return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-300">Ожидание</span>`;
}

// Trigger manual check WITHOUT reloading page (so audio never interrupts!)
async function checkServiceNow(serviceId, btn) {
    const originalContent = btn ? btn.innerHTML : null;
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="animate-spin inline-block text-emerald-400">↻</span>`;
    }

    try {
        const resp = await fetch(`/api/services/${serviceId}/check`, { method: "POST" });
        if (!resp.ok) throw new Error("Не удалось выполнить проверку");
        const data = await resp.json();

        // 1. Update Card in DOM directly
        const card = document.getElementById(`service-card-${serviceId}`);
        if (card) {
            card.setAttribute("data-status", data.status);

            const badgeContainer = document.getElementById(`service-badge-${serviceId}`);
            if (badgeContainer) badgeContainer.innerHTML = renderStatusBadge(data.status, true);

            const latencyEl = document.getElementById(`service-latency-${serviceId}`);
            if (latencyEl) {
                if (data.response_time_ms) {
                    latencyEl.textContent = `${data.response_time_ms} мс`;
                    latencyEl.className = `text-sm font-bold font-mono mt-0.5 ${data.response_time_ms < 300 ? 'text-emerald-400' : (data.response_time_ms < 1000 ? 'text-amber-400' : 'text-rose-400')}`;
                } else {
                    latencyEl.textContent = "—";
                }
            }

            const errorBox = document.getElementById(`service-error-box-${serviceId}`);
            if (errorBox) {
                if (data.error_message) {
                    errorBox.innerHTML = `<div class="mt-2.5 px-2.5 py-1.5 rounded-lg bg-rose-950/40 border border-rose-900/60 text-[11px] text-rose-300 truncate" title="${data.error_message}">⚠️ ${data.error_message}</div>`;
                } else {
                    errorBox.innerHTML = "";
                }
            }

            const timeEl = document.getElementById(`service-time-${serviceId}`);
            if (timeEl && data.last_check_at) {
                const d = new Date(data.last_check_at);
                timeEl.textContent = `${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}:${String(d.getUTCSeconds()).padStart(2,'0')}`;
            }
        }

        // 2. Refresh top dashboard counters
        refreshDashboardData();

        showToast(`Скан завершен: ${data.status} (${data.response_time_ms ? data.response_time_ms + ' мс' : data.error_message || 'OK'})`, data.status === "UP" ? "success" : "error");

        if (window.lucide) lucide.createIcons();
    } catch (err) {
        showToast(err.message, "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalContent;
            if (window.lucide) lucide.createIcons();
        }
    }
}

// Pause/Resume service WITHOUT reloading page
async function togglePauseService(serviceId, isCurrentlyActive) {
    const endpoint = isCurrentlyActive ? `/api/services/${serviceId}/pause` : `/api/services/${serviceId}/resume`;
    try {
        const resp = await fetch(endpoint, { method: "POST" });
        if (!resp.ok) throw new Error("Ошибка изменения состояния");
        const updated = await resp.json();

        const card = document.getElementById(`service-card-${serviceId}`);
        if (card) {
            const newIsActive = updated.is_active;
            card.setAttribute("data-status", newIsActive ? updated.current_status : "PAUSED");

            const badgeContainer = document.getElementById(`service-badge-${serviceId}`);
            if (badgeContainer) badgeContainer.innerHTML = renderStatusBadge(updated.current_status, newIsActive);

            const btn = document.getElementById(`service-pause-btn-${serviceId}`);
            if (btn) {
                btn.setAttribute("onclick", `togglePauseService(${serviceId}, ${newIsActive ? 'true' : 'false'})`);
                btn.setAttribute("title", newIsActive ? "Приостановить" : "Возобновить");
                btn.innerHTML = `<i data-lucide="${newIsActive ? 'pause' : 'play'}" class="w-4 h-4"></i>`;
                if (window.lucide) lucide.createIcons();
            }
        }

        refreshDashboardData();
        showToast(isCurrentlyActive ? "Мониторинг усыплен" : "Мониторинг пробужден");
    } catch (err) {
        showToast(err.message, "error");
    }
}

// Delete service
async function deleteService(serviceId, serviceName) {
    if (!confirm(`Вы действительно хотите удалить сервис "${serviceName}" из Сектора 2814?`)) {
        return;
    }
    try {
        const resp = await fetch(`/api/services/${serviceId}`, { method: "DELETE" });
        if (!resp.ok) throw new Error("Ошибка удаления сервиса");

        const card = document.getElementById(`service-card-${serviceId}`);
        if (card) card.remove();

        refreshDashboardData();
        showToast(`Сервис "${serviceName}" удален`);
    } catch (err) {
        showToast(err.message, "error");
    }
}

// Refresh dashboard data dynamically in-place (ZERO reload, ZERO audio interruption!)
async function refreshDashboardData() {
    try {
        // 1. Fetch dashboard stats
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
            if (latEl) latEl.textContent = stats.avg_response_time_ms ? `${stats.avg_response_time_ms} мс` : "—";
        }

        // 2. Fetch services list and update cards in-place
        const srvResp = await fetch("/api/services");
        if (srvResp.ok) {
            const services = await srvResp.json();
            for (const s of services) {
                const card = document.getElementById(`service-card-${s.id}`);
                if (card) {
                    card.setAttribute("data-status", !s.is_active ? "PAUSED" : s.current_status);

                    const badge = document.getElementById(`service-badge-${s.id}`);
                    if (badge) badge.innerHTML = renderStatusBadge(s.current_status, s.is_active);

                    const latEl = document.getElementById(`service-latency-${s.id}`);
                    if (latEl) {
                        if (s.last_response_time_ms) {
                            latEl.textContent = `${s.last_response_time_ms} мс`;
                            latEl.className = `text-sm font-bold font-mono mt-0.5 ${s.last_response_time_ms < 300 ? 'text-emerald-400' : (s.last_response_time_ms < 1000 ? 'text-amber-400' : 'text-rose-400')}`;
                        } else {
                            latEl.textContent = "—";
                        }
                    }

                    const upEl = document.getElementById(`service-uptime-${s.id}`);
                    if (upEl && s.uptime_24h !== undefined) {
                        upEl.textContent = `${s.uptime_24h}%`;
                    }

                    const timeEl = document.getElementById(`service-time-${s.id}`);
                    if (timeEl && s.last_check_at) {
                        const d = new Date(s.last_check_at);
                        timeEl.textContent = `${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}:${String(d.getUTCSeconds()).padStart(2,'0')}`;
                    }

                    const errorBox = document.getElementById(`service-error-box-${s.id}`);
                    if (errorBox) {
                        if (s.last_error_message) {
                            errorBox.innerHTML = `<div class="mt-2.5 px-2.5 py-1.5 rounded-lg bg-rose-950/40 border border-rose-900/60 text-[11px] text-rose-300 truncate" title="${s.last_error_message}">⚠️ ${s.last_error_message}</div>`;
                        } else {
                            errorBox.innerHTML = "";
                        }
                    }
                }
            }
            if (window.lucide) lucide.createIcons();
        }

        // Pulse radar indicator
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
            throw new Error(errData.detail || "Ошибка при подключении системы");
        }

        showToast("Система успешно подключена к Сектору 2814!");
        closeModal("modal-add-service");
        form.reset();
        
        // Refresh page or dynamic reload
        setTimeout(() => window.location.reload(), 400);
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
            throw new Error(errData.detail || "Ошибка при обновлении параметров");
        }

        showToast("Параметры успешно обновлены!");
        closeModal("modal-edit-service");
        setTimeout(() => window.location.reload(), 400);
    } catch (err) {
        showToast(err.message, "error");
    }
}
