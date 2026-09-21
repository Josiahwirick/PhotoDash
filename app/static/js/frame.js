(function () {
  const frame = document.getElementById("frame");
  if (!frame) return;

  const imgA = document.querySelector(".photos__img--a");
  const imgB = document.querySelector(".photos__img--b");
  const empty = document.getElementById("photos-empty");
  const calendar = document.getElementById("calendar-days") || document.getElementById("calendar");

  // Avoid re-showing the same photo within this window when the library is large enough.
  const COOLDOWN_MS = 15 * 60 * 1000;

  let photos = Array.isArray(window.PHOTODASH_PHOTOS)
    ? window.PHOTODASH_PHOTOS.slice()
    : [];
  /** @type {Map<number|string, number>} photo id → last shown timestamp */
  let lastShown = new Map();
  /** Upcoming photo ids in display order */
  let queue = [];
  let showingA = true;
  let intervalMs = Math.max(5, Number(frame.dataset.interval || 30)) * 1000;
  let pollMs = Math.max(10, Number(frame.dataset.poll || 60)) * 1000;
  let cycleTimer = null;

  function shuffleInPlace(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = arr[i];
      arr[i] = arr[j];
      arr[j] = tmp;
    }
    return arr;
  }

  function photoKey(photo) {
    return photo && photo.id != null ? photo.id : photo && photo.url;
  }

  function byId(list) {
    const map = new Map();
    (list || []).forEach(function (p) {
      map.set(photoKey(p), p);
    });
    return map;
  }

  function rebuildQueue() {
    const now = Date.now();
    const cooled = [];
    const warm = [];
    photos.forEach(function (p) {
      const key = photoKey(p);
      const seen = lastShown.get(key);
      if (seen == null || now - seen >= COOLDOWN_MS) cooled.push(p);
      else warm.push(p);
    });
    // Prefer cooled photos; only use recently shown ones if the cool pool is empty
    // (small library) or after exhausting cool ones — sort warm by oldest first.
    warm.sort(function (a, b) {
      return (lastShown.get(photoKey(a)) || 0) - (lastShown.get(photoKey(b)) || 0);
    });
    const next = shuffleInPlace(cooled.slice()).concat(warm);
    queue = next.map(photoKey);
  }

  function takeNextPhoto() {
    if (!photos.length) return null;
    if (!queue.length) rebuildQueue();

    const lookup = byId(photos);
    // Drop stale queue entries (deleted / deactivated since last rebuild)
    while (queue.length && !lookup.has(queue[0])) queue.shift();
    if (!queue.length) {
      rebuildQueue();
      while (queue.length && !lookup.has(queue[0])) queue.shift();
    }
    if (!queue.length) return null;

    const key = queue.shift();
    const photo = lookup.get(key);
    if (photo) lastShown.set(key, Date.now());
    return photo;
  }

  function showEmpty(on) {
    if (!empty) return;
    empty.hidden = !on;
  }

  function setActive(nextUrl) {
    const current = showingA ? imgA : imgB;
    const next = showingA ? imgB : imgA;
    if (!nextUrl) {
      imgA.removeAttribute("src");
      imgB.removeAttribute("src");
      imgA.classList.remove("is-active");
      imgB.classList.remove("is-active");
      showEmpty(true);
      return;
    }
    showEmpty(false);
    next.onload = function () {
      next.classList.add("is-active");
      current.classList.remove("is-active");
      showingA = !showingA;
    };
    next.src = nextUrl;
  }

  function tick() {
    const photo = takeNextPhoto();
    if (!photo) {
      setActive(null);
      return;
    }
    setActive(photo.url);
  }

  function restartCycle(seconds) {
    if (seconds) {
      intervalMs = Math.max(5, Number(seconds)) * 1000;
      frame.dataset.interval = String(seconds);
    }
    if (cycleTimer) clearInterval(cycleTimer);
    tick();
    cycleTimer = setInterval(tick, intervalMs);
  }

  function renderCalendar(days) {
    if (!calendar || !Array.isArray(days)) return;
    calendar.innerHTML = days
      .map(function (day) {
        const weather = day.weather
          ? [
              '<span class="weather__icon weather__icon--' +
                day.weather.condition +
                '" aria-hidden="true"></span>',
              '<span class="weather__temps">',
              day.is_today && day.weather.current
                ? '<span class="weather__current">' + day.weather.current + "°</span>"
                : "",
              '<span class="weather__range">' +
                (day.weather.low || "—") +
                "° / " +
                (day.weather.high || "—") +
                "°</span>",
              "</span>",
              '<span class="weather__label">' + escapeHtml(day.weather.condition_label) + "</span>",
            ].join("")
          : '<span class="weather__label weather__label--empty">No weather</span>';

        const entries =
          day.entries && day.entries.length
            ? day.entries
                .map(function (entry) {
                  const person = entry.person_name
                    ? '<div class="entry__person"' +
                      (entry.person_color
                        ? ' style="--person-color: ' + escapeAttr(entry.person_color) + '"'
                        : "") +
                      ">" +
                      escapeHtml(entry.person_name) +
                      "</div>"
                    : "";
                  return (
                    '<li class="entry entry--' +
                    escapeAttr(entry.entry_type) +
                    '">' +
                    person +
                    '<div class="entry__text">' +
                    escapeHtml(entry.text) +
                    "</div></li>"
                  );
                })
                .join("")
            : '<li class="entry entry--empty">—</li>';

        return (
          '<article class="day' +
          (day.is_today ? " day--today" : "") +
          '" data-date="' +
          escapeAttr(day.date) +
          '">' +
          '<header class="day__header">' +
          '<div class="day__weekday">' +
          escapeHtml(day.weekday) +
          "</div>" +
          '<div class="day__date">' +
          escapeHtml(day.month_day) +
          "</div></header>" +
          '<div class="day__weather">' +
          weather +
          "</div>" +
          '<ul class="day__entries">' +
          entries +
          "</ul></article>"
        );
      })
      .join("");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/'/g, "&#39;");
  }

  /** Order-independent: only react when the set of photos changes. */
  function photosChanged(next) {
    if (!Array.isArray(next)) return false;
    if (next.length !== photos.length) return true;
    const current = new Set(photos.map(photoKey));
    for (let i = 0; i < next.length; i++) {
      if (!current.has(photoKey(next[i]))) return true;
    }
    return false;
  }

  function applyPhotoList(next) {
    const prevKeys = new Set(photos.map(photoKey));
    photos = next.slice();
    // Drop history for removed photos; keep timestamps for ones that remain.
    Array.from(lastShown.keys()).forEach(function (key) {
      if (!photos.some(function (p) {
        return photoKey(p) === key;
      })) {
        lastShown.delete(key);
      }
    });
    // Rebuild queue when membership changes; preserve cooldown memory.
    const added = photos.some(function (p) {
      return !prevKeys.has(photoKey(p));
    });
    if (added || queue.length === 0) {
      rebuildQueue();
    } else {
      // Filter queue to still-valid ids without full reshuffle
      const lookup = byId(photos);
      queue = queue.filter(function (key) {
        return lookup.has(key);
      });
      if (!queue.length) rebuildQueue();
    }
  }

  function poll() {
    fetch("/api/frame", { headers: { Accept: "application/json" } })
      .then(function (res) {
        if (!res.ok) throw new Error("poll failed");
        return res.json();
      })
      .then(function (data) {
        if (data.days) renderCalendar(data.days);
        if (data.frame_poll_seconds) {
          const nextPoll = Math.max(10, Number(data.frame_poll_seconds)) * 1000;
          if (nextPoll !== pollMs) {
            pollMs = nextPoll;
            clearInterval(pollTimer);
            pollTimer = setInterval(poll, pollMs);
          }
        }
        if (photosChanged(data.photos)) {
          applyPhotoList(data.photos);
          restartCycle(data.photo_interval_seconds || frame.dataset.interval);
        } else if (
          data.photo_interval_seconds &&
          Number(data.photo_interval_seconds) * 1000 !== intervalMs
        ) {
          restartCycle(data.photo_interval_seconds);
        }
      })
      .catch(function () {
        /* keep showing current frame on transient errors */
      });
  }

  rebuildQueue();
  let pollTimer = setInterval(poll, pollMs);
  restartCycle();
})();
