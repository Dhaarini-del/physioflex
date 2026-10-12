
/**
 * PhysioFlex frontend API client + authenticated real-time WebSocket
 *
 * REST authentication: Authorization: Bearer <token>
 * WebSocket authentication: ?token=<JWT>
 *
 * IMPORTANT:
 * The backend must validate the WebSocket JWT and verify that the
 * requested role matches the authenticated user's actual role.
 */

const api = {
  base: '',

  /**
   * Common REST API request handler.
   */
  async request(path, options = {}) {
    const token = localStorage.getItem('token');

    const headers = {
      ...(options.body !== undefined &&
      !(options.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...(options.headers || {}),
    };

    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    let response;

    try {
      response = await fetch(`${this.base}${path}`, {
        ...options,
        headers,
      });
    } catch (error) {
      throw new Error(
        'Unable to connect to the PhysioFlex server. Check your internet connection and try again.'
      );
    }

    if (response.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');

      if (window.location.pathname !== '/login') {
        window.location.replace('/login');
      }

      throw new Error('Session expired. Please sign in again.');
    }

    const contentType = response.headers.get('content-type') || '';
    let data;

    if (contentType.includes('application/json')) {
      data = await response.json().catch(() => ({}));
    } else {
      data = await response.text().catch(() => '');
    }

    if (!response.ok) {
      const message =
        typeof data === 'object' && data !== null
          ? data.detail || data.message
          : data;

      throw new Error(
        message || `Request failed with status ${response.status}`
      );
    }

    return data;
  },

  // --------------------------------------------------
  // Authentication
  // --------------------------------------------------

  login(email, password) {
    return this.request('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  me() {
    return this.request('/api/auth/me');
  },

  // --------------------------------------------------
  // Dashboards
  // --------------------------------------------------

  doctorDashboard() {
    return this.request('/api/dashboard/doctor');
  },

  physioDashboard() {
    return this.request('/api/dashboard/physio');
  },

  patientDashboard() {
    return this.request('/api/dashboard/patient');
  },

  // --------------------------------------------------
  // Patients
  // --------------------------------------------------

  getPatients() {
    return this.request('/api/patients');
  },

  getPatient(id) {
    return this.request(`/api/patients/${encodeURIComponent(id)}`);
  },

  createPatient(body) {
    return this.request('/api/patients', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  updatePatient(id, body) {
    return this.request(`/api/patients/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  },

  deletePatient(id) {
    return this.request(`/api/patients/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  },

  // --------------------------------------------------
  // Exercises
  // --------------------------------------------------

  getExercises() {
    return this.request('/api/exercises');
  },

  // --------------------------------------------------
  // Assessments
  // --------------------------------------------------

  getAssessments(patientId) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/assessments`
    );
  },

  createAssessment(patientId, body) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/assessments`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    );
  },

  // --------------------------------------------------
  // Rehabilitation Plans
  // --------------------------------------------------

  getPlans(patientId) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/plans`
    );
  },

  createPlan(patientId, body) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/plans`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    );
  },

  updatePlan(planId, body) {
    return this.request(`/api/plans/${encodeURIComponent(planId)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  },

  deletePlan(planId) {
    return this.request(`/api/plans/${encodeURIComponent(planId)}`, {
      method: 'DELETE',
    });
  },

  // --------------------------------------------------
  // Exercise Sessions
  // --------------------------------------------------

  getSessions(patientId) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/sessions`
    );
  },

  createSession(body) {
    return this.request('/api/sessions', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  deleteSession(id) {
    return this.request(`/api/sessions/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  },

  // --------------------------------------------------
  // Clinical Notes
  // --------------------------------------------------

  getNotes(patientId) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/notes`
    );
  },

  createNote(patientId, content) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/notes`,
      {
        method: 'POST',
        body: JSON.stringify({ content }),
      }
    );
  },

  // --------------------------------------------------
  // Alerts and Progress
  // --------------------------------------------------

  getAlerts(patientId) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/alerts`
    );
  },

  getProgress(patientId) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/progress`
    );
  },

  getPatientAlerts() {
    return this.request('/api/patient-alerts');
  },

  createPatientAlert(body) {
    return this.request('/api/patient-alerts', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  // --------------------------------------------------
  // Administrator
  // --------------------------------------------------

  adminStats() {
    return this.request('/api/admin/stats');
  },

  adminListUsers() {
    return this.request('/api/admin/users');
  },

  adminCreateUser(body) {
    return this.request('/api/admin/users', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  adminUpdateUser(id, body) {
    return this.request(`/api/admin/users/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  },

  adminDeleteUser(id) {
    return this.request(`/api/admin/users/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    });
  },

  // --------------------------------------------------
  // Credential Requests
  // --------------------------------------------------

  credentialRequests() {
    return this.request('/api/admin/credential-requests');
  },

  provisionCredentials(reqId, body) {
    return this.request(
      `/api/admin/credential-requests/${encodeURIComponent(reqId)}/provision`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    );
  },

  deleteCredentialRequest(reqId) {
    return this.request(
      `/api/admin/credential-requests/${encodeURIComponent(reqId)}`,
      {
        method: 'DELETE',
      }
    );
  },

  // --------------------------------------------------
  // Complaints
  // --------------------------------------------------

  getComplaints() {
    return this.request('/api/complaints');
  },

  createComplaint(body) {
    return this.request('/api/complaints', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  updateComplaint(id, body) {
    return this.request(`/api/complaints/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  },

  // --------------------------------------------------
  // Schedules
  // --------------------------------------------------

  getSchedules() {
    return this.request('/api/schedules');
  },

  createSchedule(body) {
    return this.request('/api/schedules', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  // --------------------------------------------------
  // Physiotherapy Suggestions
  // --------------------------------------------------

  getSuggestions() {
    return this.request('/api/suggestions');
  },

  createSuggestion(body) {
    return this.request('/api/suggestions', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  // --------------------------------------------------
  // Bookings
  // --------------------------------------------------

  getBookings() {
    return this.request('/api/bookings');
  },

  createBooking(body) {
    return this.request('/api/bookings', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  updateBooking(id, body) {
    return this.request(`/api/bookings/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(body),
    });
  },

  // --------------------------------------------------
  // Voice Messages
  // --------------------------------------------------

  getVoiceMessages() {
    return this.request('/api/voice-messages');
  },

  createVoiceMessage(body) {
    return this.request('/api/voice-messages', {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  getVoiceAudio(id) {
    return this.request(
      `/api/voice-messages/${encodeURIComponent(id)}/audio`
    );
  },

  // --------------------------------------------------
  // Evaluation
  // --------------------------------------------------

  getEvaluation(patientId) {
    return this.request(
      `/api/patients/${encodeURIComponent(patientId)}/evaluation`
    );
  },
};


// ==================================================
// Authentication and frontend role-based navigation
// ==================================================

function requireAuth(allowedRoles = []) {
  const token = localStorage.getItem('token');

  let user = null;

  try {
    user = JSON.parse(localStorage.getItem('user') || 'null');
  } catch {
    user = null;
  }

  if (!token || !user || !user.role) {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.replace('/login');
    return null;
  }

  if (allowedRoles.length && !allowedRoles.includes(user.role)) {
    const roleRoutes = {
      admin: '/admin',
      doctor: '/doctor',
      physiotherapist: '/physio',
      patient: '/patient',
    };

    window.location.replace(roleRoutes[user.role] || '/login');
    return null;
  }

  return user;
}


// ==================================================
// Logout
// ==================================================

function logout() {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
  window.location.replace('/login');
}


// ==================================================
// Authenticated real-time WebSocket
// ==================================================

/**
 * Connect to the authenticated role-specific WebSocket.
 *
 * Backend requirement:
 * The endpoint /ws/{role} must:
 * 1. Read the "token" query parameter.
 * 2. Validate the JWT using the same secret and algorithm as auth.py.
 * 3. Check the actual authenticated role against the requested role.
 * 4. Reject unauthorized connections.
 *
 * Returns the WebSocket, or null if no token exists.
 */
function connectRealtime(role, onEvent, options = {}) {
  const allowedRoles = [
    'doctor',
    'physiotherapist',
    'patient',
    'admin',
  ];

  if (!allowedRoles.includes(role)) {
    console.error('Invalid WebSocket role');
    return null;
  }

  const token = localStorage.getItem('token');

  if (!token) {
    console.warn('WebSocket not connected: login token is missing');
    return null;
  }

  const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socketUrl = new URL(
    `${scheme}//${window.location.host}/ws/${encodeURIComponent(role)}`
  );

  // The backend must explicitly support token-based WebSocket authentication.
  socketUrl.searchParams.set('token', token);

  const reconnect = options.reconnect !== false;
  const reconnectDelay = Math.max(options.reconnectDelay || 5000, 1000);

  let stopped = false;
  let socket = null;
  let reconnectTimer = null;
  let keepAliveTimer = null;
  let retryCount = 0;

  function clearTimers() {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    if (keepAliveTimer !== null) {
      clearInterval(keepAliveTimer);
      keepAliveTimer = null;
    }
  }

  function connect() {
    if (stopped || !localStorage.getItem('token')) {
      return;
    }

    try {
      socket = new WebSocket(socketUrl.toString());
    } catch (error) {
      console.error('Could not create WebSocket connection', error);
      scheduleReconnect();
      return;
    }

    socket.onopen = () => {
      retryCount = 0;
      console.info(`PhysioFlex realtime connected (${role})`);

      if (typeof options.onOpen === 'function') {
        options.onOpen(socket);
      }

      keepAliveTimer = setInterval(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
          // This requires backend support for receiving client ping messages.
          socket.send(JSON.stringify({ type: 'ping' }));
        }
      }, 25000);
    };

    socket.onmessage = (event) => {
      let message;

      try {
        message = JSON.parse(event.data);
      } catch {
        console.warn('Ignored malformed WebSocket message');
        return;
      }

      if (typeof onEvent === 'function') {
        try {
          onEvent(message);
        } catch (error) {
          console.error('Realtime event handler failed', error);
        }
      }
    };

    socket.onerror = () => {
      // Browsers intentionally provide limited WebSocket error details.
      console.error('PhysioFlex WebSocket encountered an error');
    };

    socket.onclose = (event) => {
      clearTimers();

      console.info(
        `PhysioFlex realtime disconnected (code ${event.code})`
      );

      if (typeof options.onClose === 'function') {
        options.onClose(event);
      }

      // Do not endlessly retry authentication or policy failures.
      // 1008 is policy violation; 4000–4999 are application-specific.
      if (
        event.code === 1008 ||
        (event.code >= 4000 && event.code <= 4003)
      ) {
        console.error(
          'WebSocket closed by the server. Check authentication and permissions.'
        );
        return;
      }

      scheduleReconnect();
    };
  }

  function scheduleReconnect() {
    if (stopped || !reconnect || reconnectTimer !== null) {
      return;
    }

    if (!localStorage.getItem('token')) {
      return;
    }

    retryCount += 1;

    // Exponential backoff, capped at 30 seconds.
    const delay = Math.min(
      reconnectDelay * Math.pow(2, Math.min(retryCount - 1, 3)),
      30000
    );

    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  }

  connect();

  // Return a WebSocket-like handle with an explicit stop method.
  return {
    get socket() {
      return socket;
    },

    close() {
      stopped = true;
      clearTimers();

      if (
        socket &&
        socket.readyState !== WebSocket.CLOSED &&
        socket.readyState !== WebSocket.CLOSING
      ) {
        socket.close(1000, 'Client disconnected');
      }
    },

    send(data) {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(
          typeof data === 'string' ? data : JSON.stringify(data)
        );
        return true;
      }

      return false;
    },
  };
}
