(function () {
  const frame = document.getElementById("frame");
  if (!frame) return;

  const imgA = document.querySelector(".photos__img--a");
  const imgB = document.querySelector(".photos__img--b");
  const empty = document.getElementById("photos-empty");
  const calendar = document.getElementById("calendar");

  let photos = Array.isArray(window.PHOTODASH_PHOTOS)
    ? shuffleInPlace(window.PHOTODASH_PHOTOS.slice())
    : [];
  let index = 0;
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
    if (!photos.length) {
      setActive(null);
      return;
    }
    const photo = photos[index % photos.length];
    index = (index + 1) % photos.length;
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

  function photosChanged(next) {
    if (!Array.isArray(next)) return false;
    if (next.length !== photos.length) return true;
    for (let i = 0; i < next.length; i++) {
      if (!photos[i] || photos[i].id !== next[i].id || photos[i].url !== next[i].url) {
        return true;
      }
    }
    return false;
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
          photos = shuffleInPlace(data.photos.slice());
          index = 0;
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

  let pollTimer = setInterval(poll, pollMs);
  restartCycle();
})();
