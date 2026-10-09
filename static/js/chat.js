
(() => {
  "use strict";

  const form = document.getElementById("chatForm");
  const input = document.getElementById("chatInput");
  const messages = document.getElementById("chatMessages");
  const status = document.getElementById("chatStatus");
  const sendButton = document.getElementById("sendButton");
  const voiceButton = document.getElementById("voiceButton");
  const speakToggle = document.getElementById("speakToggle");

  let speakReplies = false;
  let recognition = null;

  // Update this function if your project stores the token under another key.
  function getAuthToken() {
    return (
      localStorage.getItem("token") ||
      localStorage.getItem("access_token") ||
      sessionStorage.getItem("token")
    );
  }

  function addMessage(text, sender) {
    const wrapper = document.createElement("div");
    wrapper.className = `message ${sender}`;

    const bubble = document.createElement("div");
    bubble.className = "bubble";

    // Use textContent, not innerHTML, so responses are treated as plain text.
    bubble.textContent = text;
    wrapper.appendChild(bubble);
    messages.appendChild(wrapper);
    messages.scrollTop = messages.scrollHeight;
  }

  function speak(text) {
    if (!speakReplies || !("speechSynthesis" in window)) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-IN";
    utterance.rate = 1;
    window.speechSynthesis.speak(utterance);
  }

  async function sendMessage(message) {
    const token = getAuthToken();

    if (!token) {
      status.textContent = "Please sign in again to use Smart Chat.";
      return;
    }

    sendButton.disabled = true;
    status.textContent = "PhysioFlex is preparing a response...";

    try {
      const response = await fetch("/api/chat/message", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ message })
      });

      const data = await response.json().catch(() => ({}));

      if (response.status === 401) {
        throw new Error("Your session has expired. Please sign in again.");
      }

      if (!response.ok) {
        throw new Error(data.detail || "Unable to send your message.");
      }

      const reply = data.reply || "I couldn't generate a response. Please try again.";
      addMessage(reply, "assistant");
      speak(reply);
      status.textContent = "";
    } catch (error) {
      status.textContent = error.message || "Network error. Please try again.";
    } finally {
      sendButton.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = input.value.trim();
    if (!message) return;

    addMessage(message, "user");
    input.value = "";
    await sendMessage(message);
  });

  // Optional voice-to-text; browser support varies.
  const SpeechRecognition =
    window.SpeechRecognition || window.webkitSpeechRecognition;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.continuous = false;

    recognition.addEventListener("result", (event) => {
      const transcript = event.results[0][0].transcript;
      input.value = `${input.value} ${transcript}`.trim();
      input.focus();
    });

    recognition.addEventListener("error", () => {
      status.textContent = "Voice input was unavailable. You can type instead.";
    });

    recognition.addEventListener("end", () => {
      voiceButton.classList.remove("active");
      voiceButton.textContent = "🎙 Voice input";
    });

    voiceButton.addEventListener("click", () => {
      try {
        status.textContent = "Listening...";
        voiceButton.classList.add("active");
        voiceButton.textContent = "Listening...";
        recognition.start();
      } catch {
        status.textContent = "Voice input is already active. Please try again.";
      }
    });
  } else {
    voiceButton.disabled = true;
    voiceButton.title = "Voice input is not supported by this browser.";
  }

  speakToggle.addEventListener("click", () => {
    speakReplies = !speakReplies;
    speakToggle.classList.toggle("active", speakReplies);
    speakToggle.textContent = speakReplies
      ? "🔊 Read replies: On"
      : "🔊 Read replies";

    if (!speakReplies && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
  });
})();
