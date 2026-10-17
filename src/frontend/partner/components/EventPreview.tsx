import { Icon } from "../../shared/Icon";
import { formatDateTime } from "../../shared/format";
import { SETTING_ICONS } from "../lib/labels";

type Props = {
  title: string;
  venue: string;
  address: string;
  start: string;
  setting: string;
  price: string;
  free: boolean;
  imageUrl: string | null;
};

// Karta w stylu aplikacji klienta (WarsawNow): tak ogłoszenie zobaczą mieszkańcy
export function EventPreview({ title, venue, address, start, setting, price, free, imageUrl }: Props) {
  return (
    <div className="preview">
      <div className="preview-img">
        {imageUrl && <img src={imageUrl} alt="" />}
        <div className="chips">
          {setting && (
            <span className="chip">
              <Icon name={SETTING_ICONS[setting] ?? "location_on"} />
              {setting}
            </span>
          )}
        </div>
      </div>
      <div className="preview-body">
        <div className="top">
          <b>{title || "Nazwa wydarzenia"}</b>
          <span className={`price${free ? " free" : ""}`}>{price}</span>
        </div>
        <small>
          <Icon name="location_on" size={16} />
          {[venue, address].filter(Boolean).join(", ") || "Miejsce wydarzenia"}
        </small>
        <small>
          <Icon name="schedule" size={16} />
          {start ? formatDateTime(start) : "Termin"}
        </small>
      </div>
    </div>
  );
}
