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

document.querySelectorAll("[data-entry-form]").forEach(syncEntryForm);
