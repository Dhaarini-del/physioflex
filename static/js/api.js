/**
 * PhysioFlex frontend API client + real-time WebSocket
 */
const api = {
  base: '',

  async request(path, options = {}) {
    const token = localStorage.getItem('token');
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(this.base + path, { ...options, headers });
    if (res.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
      throw new Error('Session expired');
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || res.statusText || 'Request failed');
    return data;
  },

  login(email, password) {
    return this.request('/api/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
  },
  me() { return this.request('/api/auth/me'); },

  doctorDashboard() { return this.request('/api/dashboard/doctor'); },
  physioDashboard() { return this.request('/api/dashboard/physio'); },
  patientDashboard() { return this.request('/api/dashboard/patient'); },

  getPatients() { return this.request('/api/patients'); },
  getPatient(id) { return this.request(`/api/patients/${id}`); },
  createPatient(body) { return this.request('/api/patients', { method: 'POST', body: JSON.stringify(body) }); },
  updatePatient(id, body) { return this.request(`/api/patients/${id}`, { method: 'PUT', body: JSON.stringify(body) }); },
  deletePatient(id) { return this.request(`/api/patients/${id}`, { method: 'DELETE' }); },

  getExercises() { return this.request('/api/exercises'); },

  getAssessments(patientId) { return this.request(`/api/patients/${patientId}/assessments`); },
  createAssessment(patientId, body) {
    return this.request(`/api/patients/${patientId}/assessments`, { method: 'POST', body: JSON.stringify(body) });
  },

  getPlans(patientId) { return this.request(`/api/patients/${patientId}/plans`); },
  createPlan(patientId, body) {
    return this.request(`/api/patients/${patientId}/plans`, { method: 'POST', body: JSON.stringify(body) });
  },
  updatePlan(planId, body) {
    return this.request(`/api/plans/${planId}`, { method: 'PUT', body: JSON.stringify(body) });
  },
  deletePlan(planId) { return this.request(`/api/plans/${planId}`, { method: 'DELETE' }); },

  getSessions(patientId) { return this.request(`/api/patients/${patientId}/sessions`); },
  createSession(body) { return this.request('/api/sessions', { method: 'POST', body: JSON.stringify(body) }); },
  deleteSession(id) { return this.request(`/api/sessions/${id}`, { method: 'DELETE' }); },

  getNotes(patientId) { return this.request(`/api/patients/${patientId}/notes`); },
  createNote(patientId, content) {
    return this.request(`/api/patients/${patientId}/notes`, { method: 'POST', body: JSON.stringify({ content }) });
  },
  getAlerts(patientId) { return this.request(`/api/patients/${patientId}/alerts`); },
  getProgress(patientId) { return this.request(`/api/patients/${patientId}/progress`); },

  // Admin
  adminStats() { return this.request('/api/admin/stats'); },
  adminListUsers() { return this.request('/api/admin/users'); },
  adminCreateUser(body) { return this.request('/api/admin/users', { method: 'POST', body: JSON.stringify(body) }); },
  adminUpdateUser(id, body) { return this.request(`/api/admin/users/${id}`, { method: 'PUT', body: JSON.stringify(body) }); },
  adminDeleteUser(id) { return this.request(`/api/admin/users/${id}`, { method: 'DELETE' }); },
  credentialRequests() { return this.request('/api/admin/credential-requests'); },
  provisionCredentials(reqId, body) { return this.request(`/api/admin/credential-requests/${reqId}/provision`, { method: 'POST', body: JSON.stringify(body) }); },

  // Complaints
  getComplaints() { return this.request('/api/complaints'); },
  createComplaint(body) { return this.request('/api/complaints', { method: 'POST', body: JSON.stringify(body) }); },
  updateComplaint(id, body) { return this.request(`/api/complaints/${id}`, { method: 'PUT', body: JSON.stringify(body) }); },

  getSchedules() { return this.request('/api/schedules'); },
  createSchedule(body) { return this.request('/api/schedules', { method: 'POST', body: JSON.stringify(body) }); },
  getSuggestions() { return this.request('/api/suggestions'); },
  createSuggestion(body) { return this.request('/api/suggestions', { method: 'POST', body: JSON.stringify(body) }); },
  getPatientAlerts() { return this.request('/api/patient-alerts'); },
  createPatientAlert(body) { return this.request('/api/patient-alerts', { method: 'POST', body: JSON.stringify(body) }); },
  getBookings() { return this.request('/api/bookings'); },
  createBooking(body) { return this.request('/api/bookings', { method: 'POST', body: JSON.stringify(body) }); },
  updateBooking(id, body) { return this.request(`/api/bookings/${id}`, { method: 'PUT', body: JSON.stringify(body) }); },
  getVoiceMessages() { return this.request('/api/voice-messages'); },
  createVoiceMessage(body) { return this.request('/api/voice-messages', { method: 'POST', body: JSON.stringify(body) }); },
  getVoiceAudio(id) { return this.request(`/api/voice-messages/${id}/audio`); },
  getEvaluation(patientId) { return this.request(`/api/patients/${patientId}/evaluation`); },
};




function requireAuth(allowedRoles = []) {
  const token = localStorage.getItem('token');
  const user = JSON.parse(localStorage.getItem('user') || 'null');
  if (!token || !user) { window.location.href = '/login'; return null; }
  if (allowedRoles.length && !allowedRoles.includes(user.role)) {
    if (user.role === 'admin') window.location.href = '/admin';
    else if (user.role === 'doctor') window.location.href = '/doctor';
    else if (user.role === 'physiotherapist') window.location.href = '/physio';
    else window.location.href = '/patient';
    return null;
  }
  return user;
}

function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  window.location.href = '/login';
}

/** Real-time WebSocket helper */
function connectRealtime(role, onEvent) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/${role}`);
  ws.onopen = () => console.log('WS connected as', role);
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (onEvent) onEvent(msg);
    } catch (e) {}
  };
  ws.onclose = () => {
    console.log('WS closed – reconnect in 3s');
    setTimeout(() => connectRealtime(role, onEvent), 3000);
  };
  // keepalive
  setInterval(() => {
    if (ws.readyState === 1) ws.send(JSON.stringify({ type: 'ping' }));
  }, 25000);
  return ws;
}
