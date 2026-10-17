// Mock bramki płatności: w prawdziwej integracji tę stronę hostuje operator,
// a o wyniku informuje backend webhookiem.
const paymentId = new URLSearchParams(location.search).get("id");
const statusNode = document.getElementById("status");

function setStatus(text, kind = "") {
  statusNode.textContent = text;
  statusNode.className = `status ${kind}`;
}

async function finish(action, button) {
  document.querySelectorAll("#actions button").forEach((b) => (b.disabled = true));
  setStatus(action === "confirm" ? "Przetwarzanie płatności…" : "Anulowanie…");
  try {
    const payment = await api("POST", `/payments/${encodeURIComponent(paymentId)}/${action}`);
    location.assign(`/#platnosci?status=${payment.status}`);
  } catch (err) {
    setStatus(err.message, "error");
    button.disabled = false;
  }
}

async function load() {
  if (!session.get()) return setStatus("Zaloguj się w portalu, żeby dokończyć płatność.", "error");
  if (!paymentId) return setStatus("Brak identyfikatora płatności.", "error");

  try {
    const payment = await api("GET", `/payments/${encodeURIComponent(paymentId)}`);
    document.getElementById("package").textContent = payment.packageName;
    document.getElementById("credits").textContent = creditsLabel(payment.credits);
    document.getElementById("amount").textContent = formatMoney(payment.amount, payment.currency);
    document.getElementById("details").hidden = false;

    if (payment.status !== "pending") {
      document.getElementById("actions").hidden = true;
      return setStatus(`Płatność: ${PAYMENT_STATUS[payment.status] || payment.status}.`);
    }
    setStatus("");
  } catch (err) {
    setStatus(err.message, "error");
  }
}

document.getElementById("pay").addEventListener("click", (e) => finish("confirm", e.target));
document.getElementById("cancel").addEventListener("click", (e) => finish("cancel", e.target));
load();
