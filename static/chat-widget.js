
(() => {
  if (document.getElementById("physio-chat-launcher")) return;

  const launcher = document.createElement("button");
  launcher.id = "physio-chat-launcher";
  launcher.type = "button";
  launcher.textContent = "💬";
  launcher.title = "Open PhysioFlex Smart Chat";
  launcher.setAttribute("aria-label", "Open Smart Chat");

  const panel = document.createElement("section");
  panel.id = "physio-chat-panel";
  panel.setAttribute("aria-label", "PhysioFlex Smart Chat");

  panel.innerHTML = `
    <div class="physio-chat-header">
      <div>
        <strong>PhysioFlex Smart Chat</strong>
        <div style="font-size:12px;margin-top:4px">
          Rehabilitation support
        </div>
      </div>
      <button type="button" id="physio-chat-close"
        aria-label="Close chat">×</button>
    </div>
    <div id="physio-chat-messages" aria-live="polite">
      <div class="physio-chat-bubble bot">
        Hello! How can I help with your rehabilitation questions today?
      </div>
    </div>
    <form class="physio-chat-form" id="physio-chat-form">
      <textarea id="physio-chat-input" rows="2" maxlength="2000"
        placeholder="Ask about your rehabilitation..."
        aria-label="Your message" required></textarea>
      <button id="physio-chat-send" type="submit">Send</button>
    </form>
  `;

  document.body.append(launcher, panel);

  const messages = panel.querySelector("#physio-chat-messages");
  const form = panel.querySelector("#physio-chat-form");
  const input = panel.querySelector("#physio-chat-input");
  const send = panel.querySelector("#physio-chat-send");

  function addMessage(text, type) {
    const bubble = document.createElement("div");
    bubble.className = `physio-chat-bubble ${type}`;
    bubble.textContent = text;
    messages.appendChild(bubble);
    messages.scrollTop = messages.scrollHeight;
    return bubble;
  }

  launcher.addEventListener("click", () => {
    const isOpen = panel.classList.toggle("open");
    launcher.textContent = isOpen ? "×" : "💬";
    launcher.setAttribute(
      "aria-label",
      isOpen ? "Close Smart Chat" : "Open Smart Chat"
    );
    if (isOpen) input.focus();
  });

  panel.querySelector("#physio-chat-close").addEventListener("click", () => {
    panel.classList.remove("open");
    launcher.textContent = "💬";
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = input.value.trim();
    if (!message || send.disabled) return;

    // Match these keys to the token key used by your login page.
    const token =
      localStorage.getItem("token") ||
      localStorage.getItem("access_token") ||
      sessionStorage.getItem("token") ||
      sessionStorage.getItem("access_token");

    if (!token) {
      addMessage(
        "Please sign in again to use Smart Chat.",
        "bot"
      );
      return;
    }

    addMessage(message, "user");
    input.value = "";
    send.disabled = true;
    send.textContent = "...";

    const waiting = addMessage("Thinking...", "bot");

    try {
      const response = await fetch("/api/chat/message", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ message })
      });

      const data = await response.json();
      waiting.remove();

      if (!response.ok) {
        throw new Error(
          data.detail || "Unable to contact Smart Chat."
        );
      }

      addMessage(
        data.reply || "I couldn't generate a response. Please try again.",
        "bot"
      );
    } catch (error) {
      waiting.remove();
      addMessage(
        error.message || "Connection error. Please try again.",
        "bot"
      );
    } finally {
      send.disabled = false;
      send.textContent = "Send";
      input.focus();
    }
  });
})();
