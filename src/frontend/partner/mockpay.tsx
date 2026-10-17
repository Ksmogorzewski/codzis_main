// Mock bramki płatności: w prawdziwej integracji tę stronę hostuje operator płatności,
// a o wyniku informuje backend webhookiem (src/api/handler.py: confirm_payment).
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Icon } from "../shared/Icon";
import { creditsLabel, formatMoney } from "../shared/format";
import { api } from "./lib/api";
import { PAYMENT_STATUS } from "./lib/labels";
import { session } from "./lib/session";
import type { Payment } from "./lib/types";
import "./styles.css";

function MockPay() {
  const id = new URLSearchParams(window.location.search).get("id");
  const [payment, setPayment] = useState<Payment | null>(null);
  const [error, setError] = useState(!session.get() ? "Zaloguj się w panelu organizatora, żeby dokończyć płatność." : !id ? "Brak identyfikatora płatności." : "");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!id || !session.get()) return;
    api<Payment>("GET", `/payments/${encodeURIComponent(id)}`)
      .then(setPayment)
      .catch((e: Error) => setError(e.message));
  }, [id]);

  async function finish(action: "confirm" | "cancel") {
    setBusy(true);
    try {
      const result = await api<Payment>("POST", `/payments/${encodeURIComponent(id!)}/${action}`);
      window.location.assign(`/#/platnosci?status=${result.status}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Nie udało się przetworzyć płatności");
      setBusy(false);
    }
  }

  return (
    <div className="gateway-page">
      <div className="gateway">
        <div className="mock">
          To jest <b>symulacja</b> bramki płatności – żadne pieniądze nie zostaną pobrane.
        </div>
        <h1>
          <Icon name="credit_card" />
          MockPay
        </h1>
        {payment && (
          <dl>
            <dt>Odbiorca</dt>
            <dd>WarsawNow</dd>
            <dt>Pakiet</dt>
            <dd>{payment.packageName}</dd>
            <dt>Kredyty</dt>
            <dd>{creditsLabel(payment.credits)}</dd>
            <dt>Do zapłaty</dt>
            <dd className="mono">{formatMoney(payment.amount, payment.currency)}</dd>
          </dl>
        )}
        {payment && payment.status !== "pending" && <span className="muted">Płatność: {PAYMENT_STATUS[payment.status].label}.</span>}
        {payment?.status === "pending" && (
          <div className="actions">
            <button className="btn btn-ghost" type="button" disabled={busy} onClick={() => finish("cancel")}>
              Anuluj
            </button>
            <button className="btn" type="button" disabled={busy} onClick={() => finish("confirm")}>
              {busy ? "Przetwarzanie…" : "Zapłać"}
            </button>
          </div>
        )}
        {error && <p className="form-error">{error}</p>}
        {!payment && !error && <span className="spinner" aria-hidden="true" />}
        <a href="/#/platnosci">← Wróć do panelu</a>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MockPay />
  </StrictMode>,
);
