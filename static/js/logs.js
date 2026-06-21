function logsView() {
  return {
    logs: [],
    loading: true,
    projectFilter: '',
    statusFilter: '',
    projectOptions: [],
    expanded: null,

    async load() {
      this.loading = true;
      try {
        if (this.projectOptions.length === 0) {
          const projRes = await apiFetch('/api/projects');
          if (projRes.ok) {
            this.projectOptions = await projRes.json();
          }
        }

        const params = new URLSearchParams();
        if (this.projectFilter) params.set('project_id', this.projectFilter);
        if (this.statusFilter) params.set('status', this.statusFilter);

        const res = await apiFetch(`/api/logs?${params.toString()}`);
        if (res.ok) {
          this.logs = await res.json();
        }
      } finally {
        this.loading = false;
      }
    },

    toggleExpand(id) {
      this.expanded = this.expanded === id ? null : id;
    },

    statusBadgeClass(status) {
      return statusBadgeClass(status);
    },

    formatTime(iso) {
      return formatTime(iso);
    },

    truncate(text, length) {
      return truncate(text, length);
    },
  };
}
