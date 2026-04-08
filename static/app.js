function syncEntryForm(form) {
    const clientSelect = form.querySelector("[data-client-select]");
    const projectSelect = form.querySelector("[data-project-select]");
    const taskSelect = form.querySelector("[data-task-select]");
    if (!projectSelect || !taskSelect) {
        return;
    }

    const projectOptions = Array.from(projectSelect.querySelectorAll("option"));
    const taskOptions = Array.from(taskSelect.querySelectorAll("option"));

    function updateProjects() {
        const selectedClient = clientSelect ? clientSelect.value : "";
        projectOptions.forEach((option, index) => {
            if (index === 0) {
                option.hidden = false;
                return;
            }
            option.hidden = selectedClient !== "" && option.dataset.clientId !== selectedClient;
        });

        const current = projectSelect.selectedOptions[0];
        if (current && current.hidden) {
            projectSelect.value = "";
        }
        updateTasks();
    }

    function updateTasks() {
        const selectedProject = projectSelect.value;
        taskOptions.forEach((option, index) => {
            if (index === 0) {
                option.hidden = false;
                return;
            }
            option.hidden = selectedProject !== "" && option.dataset.projectId !== selectedProject;
        });

        const currentTask = taskSelect.selectedOptions[0];
        if (currentTask && currentTask.hidden) {
            taskSelect.value = "";
        }

        if (clientSelect && selectedProject) {
            const projectOption = projectSelect.selectedOptions[0];
            clientSelect.value = projectOption.dataset.clientId || "";
        }
    }

    if (clientSelect) {
        clientSelect.addEventListener("change", updateProjects);
    }
    projectSelect.addEventListener("change", updateTasks);

    updateProjects();
    updateTasks();
}

function formatHumanDate(date) {
    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfTarget = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const dayDifference = Math.round((startOfTarget - startOfToday) / 86400000);
    const timeText = new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);

    if (dayDifference === 0) {
        return `Today at ${timeText}`;
    }
    if (dayDifference === -1) {
        return `Yesterday at ${timeText}`;
    }
    if (dayDifference > -7 && dayDifference < 0) {
        const weekday = new Intl.DateTimeFormat(undefined, { weekday: "long" }).format(date);
        return `${weekday} at ${timeText}`;
    }

    return new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    }).format(date);
}

function initializeHumanDates(root) {
    root.querySelectorAll("[data-human-datetime]").forEach((element) => {
        const rawValue = element.getAttribute("datetime");
        if (!rawValue) {
            return;
        }

        const date = new Date(rawValue);
        if (Number.isNaN(date.getTime())) {
            return;
        }

        element.textContent = formatHumanDate(date);
        element.title = new Intl.DateTimeFormat(undefined, {
            year: "numeric",
            month: "long",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        }).format(date);
    });
}

function initializeEntryForms(root) {
    root.querySelectorAll("[data-entry-form]").forEach((form) => {
        if (form.dataset.entryBound === "true") {
            return;
        }
        form.dataset.entryBound = "true";
        syncEntryForm(form);
    });
}

function initializeDismissibleNotifications(root) {
    root.querySelectorAll("[data-dismissible-notification]").forEach((element) => {
        if (element.dataset.dismissibleBound === "true") {
            return;
        }
        element.dataset.dismissibleBound = "true";
    });
}

function formatDuration(seconds) {
    const safeSeconds = Math.max(Math.floor(seconds), 0);
    const hours = Math.floor(safeSeconds / 3600);
    const minutes = Math.floor((safeSeconds % 3600) / 60);
    const remainingSeconds = safeSeconds % 60;

    if (hours) {
        return `${hours}h ${minutes}m ${remainingSeconds}s`;
    }
    if (minutes) {
        return `${minutes}m ${remainingSeconds}s`;
    }
    return `${remainingSeconds}s`;
}

function updateLiveDurations(root) {
    root.querySelectorAll("[data-live-duration]").forEach((element) => {
        const baseSeconds = Number(element.dataset.baseSeconds);
        const renderedAtValue = element.dataset.renderedAt;
        if (!Number.isFinite(baseSeconds) || !renderedAtValue) {
            return;
        }

        const renderedAt = new Date(renderedAtValue);
        if (Number.isNaN(renderedAt.getTime())) {
            return;
        }

        const elapsedSeconds = baseSeconds + (Date.now() - renderedAt.getTime()) / 1000;
        element.textContent = formatDuration(elapsedSeconds);
        element.title = `Elapsed at ${new Intl.DateTimeFormat(undefined, {
            year: "numeric",
            month: "long",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
        }).format(renderedAt)}`;
    });
}

function updateLiveTotals(root) {
    root.querySelectorAll("[data-live-total]").forEach((element) => {
        const baseSeconds = Number(element.dataset.baseSeconds);
        const renderedAtValue = element.dataset.renderedAt;
        if (!Number.isFinite(baseSeconds) || !renderedAtValue) {
            return;
        }

        const renderedAt = new Date(renderedAtValue);
        if (Number.isNaN(renderedAt.getTime())) {
            return;
        }

        const shouldTrackNow = element.dataset.trackNow === "true";
        const liveSeconds = shouldTrackNow
            ? baseSeconds + (Date.now() - renderedAt.getTime()) / 1000
            : baseSeconds;

        element.textContent = formatDuration(liveSeconds);
    });
}

let liveDurationIntervalId = null;

function pageIsActiveForTimers() {
    return document.visibilityState === "visible" && document.hasFocus();
}

function syncLiveDurationTimer() {
    const hasLiveTimers =
        document.querySelector("[data-live-duration]") !== null
        || document.querySelector('[data-live-total][data-track-now="true"]') !== null;
    const shouldRun = hasLiveTimers && pageIsActiveForTimers();

    if (!shouldRun) {
        if (liveDurationIntervalId !== null) {
            window.clearInterval(liveDurationIntervalId);
            liveDurationIntervalId = null;
        }
        return;
    }

    updateLiveDurations(document);
    updateLiveTotals(document);
    if (liveDurationIntervalId === null) {
        liveDurationIntervalId = window.setInterval(() => {
            if (!pageIsActiveForTimers()) {
                syncLiveDurationTimer();
                return;
            }
            updateLiveDurations(document);
            updateLiveTotals(document);
        }, 1000);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    initializeEntryForms(document);
    initializeHumanDates(document);
    initializeDismissibleNotifications(document);
    updateLiveDurations(document);
    updateLiveTotals(document);
    syncLiveDurationTimer();
});

document.body.addEventListener("htmx:load", (event) => {
    initializeEntryForms(event.target);
    initializeHumanDates(event.target);
    initializeDismissibleNotifications(event.target);
    updateLiveDurations(event.target);
    updateLiveTotals(event.target);
    syncLiveDurationTimer();
});

document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-dismiss-notification]");
    if (!button) {
        return;
    }

    const notification = button.closest("[data-dismissible-notification]");
    if (notification) {
        notification.remove();
    }
});

document.addEventListener("visibilitychange", syncLiveDurationTimer);
window.addEventListener("focus", syncLiveDurationTimer);
window.addEventListener("blur", syncLiveDurationTimer);
