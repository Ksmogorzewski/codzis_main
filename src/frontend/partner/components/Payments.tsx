import { useEffect, useState } from "react";
import { Icon } from "../../shared/Icon";
import { creditsLabel, formatDateTime, formatMoney } from "../../shared/format";
import { useToast } from "../../shared/toast";
import { replaceHash } from "../../shared/useHashRoute";
import { api } from "../lib/api";
import { config, sortedPackages } from "../lib/config";
import { PAYMENT_STATUS } from "../lib/labels";
import type { Payment, Profile } from "../lib/types";

type Props = { profile: Profile; params: URLSearchParams; onError: (e: unknown) => void; onRefresh: () => Promise<void> };

export function Payments({ profile, params, onError, onRefresh }: Props) {
  const toast = useToast();
  const [payments, setPayments] = useState<Payment[] | null>(null);
  const [buying, setBuying] = useState<string | null>(null);
  const cfg = config();
  const packages = sortedPackages();
  const bestValue = packages.reduce((best, p) => (p.price / p.credits < best.price / best.credits ? p : best), packages[0]!);

  // Powrót z bramki: #/platnosci?status=paid|cancelled
  const status = params.get("status");
  useEffect(() => {
    if (!status) return;
    replaceHash("platnosci");
    if (status === "paid") toast("Płatność zakończona – kredyty dodane");
    if (status === "cancelled") toast("Płatność anulowana", "error");
  }, [status, toast]);

  useEffect(() => {
    void onRefresh();
    api<{ items: Payment[] }>("GET", "/payments")
      .then(({ items }) => setPayments(items))
      .catch(onError);
  }, [onError, onRefresh]);

  async function buy(packageId: string) {
    setBuying(packageId);
    try {
      const payment = await api<Payment>("POST", "/payments", { package: packageId });
      window.location.assign(payment.redirectUrl ?? `/mock-pay.html?id=${payment.id}`);
    } catch (e) {
      setBuying(null);
      onError(e);
    }
  }

  return (
    <div className="content">
      <div className="content-head">
        <div>
          <h1>Płatności i kredyty</h1>
          <span>
            Masz {creditsLabel(profile.credits)} · jedno ogłoszenie kosztuje {creditsLabel(profile.eventCost)}
          </span>
        </div>
      </div>

      <div className="plans">
        {packages.map((p) => (
          <div className={`plan${p.id === bestValue.id ? " best" : ""}`} key={p.id}>
            <div className="name">
              <span>{p.name}</span>
              {p.id === bestValue.id && <span className="pill info">Najlepsza cena</span>}
            </div>
            <div className="price">
              <b>{formatMoney(p.price, cfg.currency)}</b>
              <span className="muted">jednorazowo</span>
            </div>
            <ul>
              <li><Icon name="check" />{creditsLabel(p.credits)}</li>
              <li><Icon name="check" />{formatMoney(p.price / p.credits, cfg.currency)} za ogłoszenie</li>
              <li><Icon name="check" />Tagowanie AI i publikacja w rekomendacjach</li>
            </ul>
            <button className={`btn${p.id === bestValue.id ? "" : " btn-ghost"}`} type="button" disabled={buying !== null} onClick={() => buy(p.id)}>
              {buying === p.id ? "Przekierowanie…" : "Kup"}
            </button>
          </div>
        ))}
      </div>

      <div className="panel pay-table">
        <div className="table-head">
          <span>Pakiet</span>
          <span>Data</span>
          <span>Status</span>
        </div>
        {payments?.map((p) => (
          <div className="pay-row" key={p.id}>
            <span>
              <b>{p.packageName}</b> · {creditsLabel(p.credits)} · <span className="num">{formatMoney(p.amount, p.currency)}</span>
            </span>
            <span className="muted">{formatDateTime(p.createdAt)}</span>
            <span>
              <span className={`pill ${PAYMENT_STATUS[p.status].tone}`}>{PAYMENT_STATUS[p.status].label}</span>
              {p.status === "pending" && (
                <a className="pay-finish" href={`/mock-pay.html?id=${encodeURIComponent(p.id)}`}>
                  dokończ
                </a>
              )}
            </span>
          </div>
        ))}
        {payments?.length === 0 && <div className="empty">Brak płatności.</div>}
        {payments === null && <div className="empty"><span className="spinner" aria-hidden="true" /></div>}
      </div>
    </div>
  );
}
