import { useState, type CSSProperties } from "react";
import { Icon } from "../../shared/Icon";
import { mapsUrl, placeLabel, priceLabel, safeUrl, settingInfo, slotLabel, tint } from "../lib/events";
import type { Recommendation } from "../lib/types";

type Props = { item: Recommendation; now: Date };

// Karta rekomendacji jak w makiecie: zdjęcie, cena, miejsce, termin, "Pasuje: …", Trasa / Bilet
export function EventCard({ item, now }: Props) {
  const [imageFailed, setImageFailed] = useState(false);
  const image = imageFailed ? null : safeUrl(item.imageUrl);
  const price = priceLabel(item);
  const setting = settingInfo(item.tags.setting);
  const when = slotLabel(item.slot, now);
  const place = placeLabel(item);
  const route = mapsUrl(item);
  const ticket = safeUrl(item.ticketUrl);
  const page = ticket ?? safeUrl(item.url);
  const partner = item.origin === "partner";

  return (
    <article className={partner ? "ev-card ev-partner" : "ev-card"}>
      <div className="ev-img" style={{ "--tint": tint(item.id) } as CSSProperties}>
        {image && <img src={image} alt="" loading="lazy" onError={() => setImageFailed(true)} />}
        <div className="ev-badges">
          {partner && <span className="badge badge-red">Od organizatora</span>}
          {setting && (
            <span className="badge">
              <Icon name={setting.icon} />
              {setting.label}
            </span>
          )}
          {item.online && (
            <span className="badge">
              <Icon name="devices" />
              Online
            </span>
          )}
        </div>
      </div>
      <div className="ev-body">
        <div className="ev-head">
          <h3>{item.title}</h3>
          {price && <span className={price.free ? "price price-free" : "price"}>{price.label}</span>}
        </div>
        <div className="ev-meta">
          {when && (
            <span className="ev-when">
              <Icon name={item.kind === "recurring" ? "event_repeat" : "schedule"} />
              {when}
            </span>
          )}
          {(place || item.district) && (
            <span>
              <Icon name="location_on" />
              {[place, item.district].filter(Boolean).join(" · ")}
            </span>
          )}
        </div>
        {item.lead && <p className="ev-lead">{item.lead}</p>}
        <div className="ev-reason">
          <Icon name="auto_awesome" fill />
          <span>
            <b>Pasuje:</b> {item.reason}
          </span>
        </div>
        <div className="ev-actions">
          {route && (
            <a className="btn btn-outline" href={route} target="_blank" rel="noopener noreferrer">
              <Icon name="directions" />
              Trasa
            </a>
          )}
          {page && (
            <a className="btn" href={page} target="_blank" rel="noopener noreferrer">
              <Icon name={ticket ? "confirmation_number" : "open_in_new"} />
              {ticket ? "Bilet" : "Szczegóły"}
            </a>
          )}
        </div>
      </div>
    </article>
  );
}
