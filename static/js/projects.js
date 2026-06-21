function projectsView() {
  return {
    projects: [],
    loading: true,

    addDrawerOpen: false,
    addForm: { name: '', path: '', branch: 'main', restart_command: '', github_webhook_secret: '' },
    addSecretConfirm: '',
    addPathError: '',
    addPathValid: false,
    addGitRemote: '',
    addFormError: '',
    addSaving: false,
    addSuccess: {},

    settingsDrawerOpen: false,
    settingsProject: null,
    settingsForm: {},
    settingsSecretConfirm: '',
    settingsPathError: '',
    settingsPathValid: false,
    settingsGitRemote: '',
    settingsFormError: '',
    settingsSaving: false,
    secretEditing: false,
    deleteConfirming: false,

    async load() {
      this.loading = true;
      try {
        const res = await apiFetch('/api/projects');
        if (res.ok) {
          this.projects = await res.json();
        }
      } finally {
        this.loading = false;
      }
    },

    statusBorderClass(project) {
      if (!project.last_log) return 'status-never';
      return project.last_log.overall_status === 'success' ? 'status-success' : 'status-failed';
    },

    statusBadgeClass(status) {
      return statusBadgeClass(status);
    },

    formatTime(iso) {
      return formatTime(iso);
    },

    async deployNow(project) {
      project.deploying = true;
      try {
        const res = await apiFetch(`/api/projects/${project.id}/deploy`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          this.showToast(
            data.status === 'success' ? 'Deploy succeeded' : 'Deploy failed',
            data.status === 'success' ? 'success' : 'error'
          );
        } else {
          this.showToast(data.detail || 'Deploy failed', 'error');
        }
      } catch (e) {
        this.showToast('Deploy failed', 'error');
      } finally {
        project.deploying = false;
        await this.load();
      }
    },

    openAddDrawer() {
      this.addForm = { name: '', path: '', branch: 'main', restart_command: '', github_webhook_secret: '' };
      this.addSecretConfirm = '';
      this.addPathError = '';
      this.addPathValid = false;
      this.addGitRemote = '';
      this.addFormError = '';
      this.addSuccess = {};
      this.addDrawerOpen = true;
    },

    closeAddDrawer() {
      this.addDrawerOpen = false;
      this.load();
    },

    async pasteSecret(target) {
      try {
        const text = await navigator.clipboard.readText();
        if (target === 'add') {
          this.addForm.github_webhook_secret = text;
        } else if (target === 'addConfirm') {
          this.addSecretConfirm = text;
        } else if (target === 'settings') {
          this.settingsForm.github_webhook_secret = text;
        }
      } catch (e) {
        this.showToast('Could not read clipboard', 'error');
      }
    },

    async validatePath(target) {
      const form = target === 'add' ? this.addForm : this.settingsForm;
      if (!form.path) return;

      try {
        const res = await apiFetch('/api/projects/validate-path', {
          method: 'POST',
          body: JSON.stringify({ path: form.path }),
        });
        const data = await res.json();

        if (target === 'add') {
          if (res.ok) {
            this.addPathValid = true;
            this.addPathError = '';
            this.addGitRemote = data.git_remote || '';
          } else {
            this.addPathValid = false;
            this.addGitRemote = '';
            this.addPathError = data.detail || 'Invalid path';
          }
        } else {
          if (res.ok) {
            this.settingsPathValid = true;
            this.settingsPathError = '';
            this.settingsGitRemote = data.git_remote || '';
          } else {
            this.settingsPathValid = false;
            this.settingsGitRemote = '';
            this.settingsPathError = data.detail || 'Invalid path';
          }
        }
      } catch (e) {
        // ignore network errors during inline validation
      }
    },

    async submitAdd() {
      this.addFormError = '';
      if (!this.addForm.name || !this.addForm.path) {
        this.addFormError = 'Project name and server path are required';
        return;
      }
      if (!this.addForm.github_webhook_secret) {
        this.addFormError = 'A GitHub webhook secret is required';
        return;
      }
      if (this.addForm.github_webhook_secret !== this.addSecretConfirm) {
        this.addFormError = 'Webhook secret and confirmation do not match';
        return;
      }

      this.addSaving = true;
      try {
        const res = await apiFetch('/api/projects', {
          method: 'POST',
          body: JSON.stringify(this.addForm),
        });
        const data = await res.json();
        if (!res.ok) {
          this.addFormError = data.detail || 'Failed to create project';
          return;
        }
        this.addSuccess = data;
        this.showToast('Project created', 'success');
      } catch (e) {
        this.addFormError = 'Failed to create project';
      } finally {
        this.addSaving = false;
      }
    },

    openSettingsDrawer(project) {
      this.settingsProject = project;
      this.settingsForm = {
        name: project.name,
        path: project.path,
        branch: project.branch,
        restart_command: project.restart_command || '',
        github_webhook_secret: undefined,
      };
      this.settingsSecretConfirm = '';
      this.settingsPathError = '';
      this.settingsPathValid = false;
      this.settingsGitRemote = '';
      this.settingsFormError = '';
      this.secretEditing = false;
      this.deleteConfirming = false;
      this.settingsDrawerOpen = true;
    },

    closeSettingsDrawer() {
      this.settingsDrawerOpen = false;
      this.settingsProject = null;
    },

    async submitSettings() {
      this.settingsFormError = '';
      const payload = {
        name: this.settingsForm.name,
        path: this.settingsForm.path,
        branch: this.settingsForm.branch,
        restart_command: this.settingsForm.restart_command,
      };
      if (this.secretEditing && this.settingsForm.github_webhook_secret !== undefined) {
        if (!this.settingsForm.github_webhook_secret) {
          this.settingsFormError = 'A GitHub webhook secret is required';
          return;
        }
        if (this.settingsForm.github_webhook_secret !== this.settingsSecretConfirm) {
          this.settingsFormError = 'Webhook secret and confirmation do not match';
          return;
        }
        payload.github_webhook_secret = this.settingsForm.github_webhook_secret;
      }

      this.settingsSaving = true;
      try {
        const res = await apiFetch(`/api/projects/${this.settingsProject.id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
          this.settingsFormError = data.detail || 'Failed to update project';
          return;
        }
        this.showToast('Project updated', 'success');
        this.closeSettingsDrawer();
        await this.load();
      } catch (e) {
        this.settingsFormError = 'Failed to update project';
      } finally {
        this.settingsSaving = false;
      }
    },

    async confirmDelete() {
      try {
        const res = await apiFetch(`/api/projects/${this.settingsProject.id}`, { method: 'DELETE' });
        if (res.ok) {
          this.showToast('Project deleted', 'success');
          this.closeSettingsDrawer();
          await this.load();
        } else {
          const data = await res.json();
          this.showToast(data.detail || 'Failed to delete project', 'error');
        }
      } catch (e) {
        this.showToast('Failed to delete project', 'error');
      }
    },

    copyToClipboard(text) {
      copyToClipboard(text);
    },
  };
}
