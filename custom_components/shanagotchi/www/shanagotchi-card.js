const SPRITES = new URL("sprites/", import.meta.url).href;

const SAYS = {
  hungry: "feed me pills!",
  sleep: "zzz",
  ask: "how are you? 1-5",
  sad: "I'm here",
  low: "go easy today",
  okay: "steady",
  happy: "feeling good",
  proud: "best day!",
};
const LIDS = {
  red: ["#c0392b", "Rubbish"],
  yellow: ["#d4a017", "Recycling"],
  green: ["#2e8b57", "Food & garden"],
  purple: ["#7d3c98", "Glass"],
};
const FEELING_ICONS = [
  "mdi:emoticon-cry-outline",
  "mdi:emoticon-sad-outline",
  "mdi:emoticon-neutral-outline",
  "mdi:emoticon-happy-outline",
  "mdi:emoticon-excited-outline",
];

const STYLE = `
  .screen { background: #f4f1ea; color: #1c1c1c; padding: 16px; border-radius: var(--ha-card-border-radius, 12px) var(--ha-card-border-radius, 12px) 0 0; }
  .date { font-weight: 700; border-bottom: 2px solid #1c1c1c; padding-bottom: 8px; margin-bottom: 12px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .cols > div + div { border-left: 2px solid #1c1c1c; padding-left: 16px; }
  .label { color: #b3302a; font-size: 12px; font-weight: 700; letter-spacing: 0.08em; }
  .big { font-size: 24px; font-weight: 700; line-height: 1.2; margin: 4px 0 8px; }
  .red { color: #b3302a; }
  .blue { color: #2e4c8c; }
  .bins { display: flex; flex-wrap: wrap; gap: 12px; }
  .bin { width: 56px; text-align: center; font-size: 12px; }
  .bin i { display: block; height: 8px; margin: 0 2px; }
  .bin b { display: block; height: 48px; margin: 3px 8px 4px; background: #1c1c1c; }
  .pet { display: flex; align-items: flex-start; gap: 4px; }
  .pet img { image-rendering: pixelated; }
  .says { font-family: monospace; margin: 4px 0; }
  .note { font-size: 14px; }
  .row { display: flex; gap: 8px; padding: 8px 16px 0; }
  .row:last-child { padding-bottom: 16px; }
  .ask { padding: 12px 16px 0; font-weight: 500; }
  button { flex: 1; min-height: 48px; padding: 8px 4px; border: 1px solid var(--divider-color); border-radius: 12px; background: none; color: var(--primary-text-color); font: inherit; cursor: pointer; }
  button:hover { background: var(--secondary-background-color); }
  button.on { border-color: var(--primary-color); color: var(--primary-color); }
  button ha-icon { display: block; margin: 0 auto 2px; }
`;

function binNight(attrs, locale) {
  const days = attrs.bin_days;
  if (days === null || days === undefined || days < 0) return "No date";
  if (days === 0) return "Out today";
  if (days === 1) return "Tonight";
  const night = new Date(`${attrs.bin_date}T12:00:00`);
  night.setDate(night.getDate() - 1);
  return days <= 7
    ? night.toLocaleDateString(locale, { weekday: "long" })
    : night.toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "numeric" });
}

function doseLine(attrs, locale) {
  if (attrs.status === "due") return '<div class="big red">Pills due</div>';
  if (attrs.status === "skipped") return '<div class="big">Skipped</div>';
  if (attrs.status === "taken") {
    const at = new Date(attrs.status_changed).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", hour12: false });
    return `<div class="big">Taken ${at}</div>`;
  }
  return `<div class="big">Next ${attrs.next_dose}</div>`;
}

class ShanagotchiCard extends HTMLElement {
  setConfig(config) {
    this._entity = config.entity;
    // Not undefined, so the first update renders even when the entity is missing
    this._state = null;
    if (this._hass) this.hass = this._hass;
  }

  static getStubConfig() {
    return {};
  }

  getCardSize() {
    return 6;
  }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._entity || this._findMood(hass)];
    if (state === this._state) return;
    this._state = state;
    this._render();
  }

  // The entity ID depends on the device's area and any rename, so look the sensor up in the registry
  _findMood(hass) {
    if (hass.entities !== this._entities) {
      this._entities = hass.entities;
      this._found = Object.values(hass.entities ?? {}).find(
        (entry) => entry.platform === "shanagotchi" && entry.translation_key === "mood"
      )?.entity_id;
    }
    return this._found;
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (ev) => {
        const button = ev.target.closest("button");
        if (!button) return;
        const data = button.dataset.value ? { value: Number(button.dataset.value) } : {};
        this._hass.callService("shanagotchi", button.dataset.action, data);
      });
    }
    const state = this._state;
    if (!state) {
      this.shadowRoot.innerHTML = '<ha-card><div style="padding:16px"></div></ha-card>';
      this.shadowRoot.querySelector("div").textContent = this._entity
        ? `Entity ${this._entity} not found.`
        : "Shanagotchi mood sensor not found. Set up the Shanagotchi integration first.";
      return;
    }
    const a = state.attributes;
    const locale = this._hass.locale?.language;
    const mood = state.state in SAYS ? state.state : "okay";
    const star = a.streak_days >= 7 && mood !== "sleep";
    const bins = (a.bin_days ?? -1) >= 0
      ? a.bin_lids.map((lid) => `<div class="bin"><i style="background:${LIDS[lid][0]}"></i><b></b>${LIDS[lid][1]}</div>`).join("")
      : "";
    const today = new Date().toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "numeric" });

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <ha-card>
        <div class="screen">
          <div class="date">${today}</div>
          <div class="cols">
            <div>
              <div class="label">BIN NIGHT</div>
              <div class="big">${binNight(a, locale)}</div>
              <div class="bins">${bins}</div>
            </div>
            <div>
              <div class="pet">
                <img src="${SPRITES}${mood}.png" width="120" height="90" alt="${mood}">
                ${star ? `<img src="${SPRITES}star.png" width="20" height="20" alt="7 day streak">` : ""}
              </div>
              <div class="says">${SAYS[mood]}</div>
              ${doseLine(a, locale)}
              <div class="note red" data-text="notice"></div>
              ${a.checkin_pending ? '<div class="note blue">Tap a face below</div>' : ""}
              <div class="note red" data-text="refill"></div>
            </div>
          </div>
        </div>
        <div class="row">
          <button data-action="take_dose"><ha-icon icon="mdi:pill"></ha-icon>Taken</button>
          <button data-action="skip_dose"><ha-icon icon="mdi:debug-step-over"></ha-icon>Skip</button>
          ${a.refill_due ? '<button data-action="refill_ordered"><ha-icon icon="mdi:medical-bag"></ha-icon>Ordered</button>' : ""}
        </div>
        <div class="ask">How are you feeling?</div>
        <div class="row">
          ${FEELING_ICONS.map((icon, i) => `<button data-action="set_feeling" data-value="${i + 1}" class="${a.feeling === i + 1 ? "on" : ""}"><ha-icon icon="${icon}"></ha-icon>${i + 1}</button>`).join("")}
        </div>
      </ha-card>`;
    // The notice and refill name are user text, so they go in as text and not markup
    this.shadowRoot.querySelector('[data-text="notice"]').textContent = a.notice;
    this.shadowRoot.querySelector('[data-text="refill"]').textContent = a.refill_due ? `Order: ${a.refill_name}` : "";
  }
}

customElements.define("shanagotchi-card", ShanagotchiCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "shanagotchi-card",
  name: "Shanagotchi",
  description: "The Shanagotchi screen: bin night, the character, dose status and the daily check-in.",
});
