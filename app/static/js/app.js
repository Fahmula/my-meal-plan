/* My Meal Plan – client behaviour (htmx + SortableJS). */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  // ---------------------------------------------------------------- toasts
  const toastHost = $("#toasts");
  const TOAST_ICONS = {
    success: '<path d="M20 6 9 17l-5-5"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    error: '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
  };

  function raiseToasts() {
    // The toast host is a popover so it renders above open <dialog>s (top layer).
    if (!toastHost.showPopover || !toastHost.children.length) return;
    try {
      if (toastHost.matches(":popover-open")) toastHost.hidePopover();
      toastHost.showPopover();
    } catch (_) { /* popover unsupported */ }
  }

  function toast(message, type = "success") {
    const el = document.createElement("div");
    el.className = `app-toast is-${type}`;
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" class="size-4 shrink-0">${TOAST_ICONS[type] || TOAST_ICONS.success}</svg><span></span>`;
    el.querySelector("span").textContent = message;
    toastHost.append(el);
    while (toastHost.children.length > 3) toastHost.firstElementChild.remove();
    if (!toastHost.matches?.(":popover-open")) raiseToasts();
    setTimeout(() => {
      el.classList.add("is-leaving");
      setTimeout(() => {
        el.remove();
        if (!toastHost.children.length && toastHost.hidePopover) {
          try { toastHost.hidePopover(); } catch (_) {}
        }
      }, 260);
    }, type === "error" ? 5200 : 2800);
  }
  window.mealPlanToast = toast;

  document.body.addEventListener("toast", (e) => toast(e.detail.message, e.detail.type));

  // ----------------------------------------------------------------- modal
  const modal = $("#modal");
  const modalBox = $("#modal-content");

  document.body.addEventListener("htmx:afterSwap", (e) => {
    if (e.detail.target !== modalBox) return;
    modalBox.classList.toggle("is-wide", !!modalBox.querySelector("[data-modal-size=wide]"));
    if (!modal.open) {
      modal.showModal();
      raiseToasts();
    }
    modalBox.scrollTop = 0;
  });

  document.body.addEventListener("closeModal", () => modal.open && modal.close());
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-close-modal]")) modal.close();
  });
  modal.addEventListener("close", () => {
    setTimeout(() => { if (!modal.open) modalBox.innerHTML = ""; }, 250);
  });

  // --------------------------------------------------- confirmation dialog
  const confirmDialog = $("#confirm-dialog");
  const confirmAccept = $("[data-confirm-accept]", confirmDialog);
  let settleConfirm = null;

  function finishConfirm(answer) {
    const settle = settleConfirm;
    settleConfirm = null;
    if (confirmDialog.open) confirmDialog.close();
    settle?.(answer);
  }
  confirmAccept.addEventListener("click", () => finishConfirm(true));
  $("[data-confirm-cancel]", confirmDialog).addEventListener("click", () => finishConfirm(false));
  confirmDialog.addEventListener("close", () => finishConfirm(false)); // Esc / backdrop

  function askConfirm({ title, detail, ok, tone }) {
    finishConfirm(false); // never leave an earlier question hanging
    $("[data-confirm-title]", confirmDialog).textContent = title;
    $("[data-confirm-detail]", confirmDialog).textContent = detail || "";
    confirmAccept.textContent = ok || "Delete";
    confirmAccept.className = `btn rounded-full ${tone === "primary" ? "btn-primary" : "btn-error"}`;
    return new Promise((resolve) => {
      settleConfirm = resolve;
      confirmDialog.showModal();
      raiseToasts();
    });
  }

  // Replace the browser's confirm() for hx-confirm with a styled dialog.
  document.body.addEventListener("htmx:confirm", (e) => {
    if (!e.detail.question) return;
    e.preventDefault();
    const elt = e.detail.elt;
    document.activeElement?.blur(); // closes the week dropdown
    askConfirm({
      title: e.detail.question,
      detail: elt.dataset.confirmDetail,
      ok: elt.dataset.confirmOk,
      tone: elt.dataset.confirmTone,
    }).then((ok) => ok && e.detail.issueRequest(true));
  });

  // ---------------------------------------------------------------- errors
  document.body.addEventListener("htmx:responseError", (e) => {
    const xhr = e.detail.xhr;
    let msg = "Something went wrong";
    try {
      const detail = JSON.parse(xhr.responseText).detail;
      if (typeof detail === "string") msg = detail;
      else if (Array.isArray(detail)) msg = detail.map((d) => d.msg).join(", ");
    } catch (_) {
      if (xhr.status) msg += ` (HTTP ${xhr.status})`;
    }
    toast(msg, "error");
  });
  document.body.addEventListener("htmx:sendError", () =>
    toast("Can't reach the server. Check your connection.", "error"));

  // Close menus after choosing an item.
  document.addEventListener("click", (e) => {
    if (e.target.closest(".week-menu button")) document.activeElement?.blur();
    const planDay = e.target.closest(".plan-day");
    if (planDay) planDay.closest("details")?.removeAttribute("open");
  });

  // ------------------------------------------------------- image inputs
  const PLACEHOLDER =
    '<div class="meal-thumb-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="size-9"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg><span>No image yet</span></div>';

  document.addEventListener("change", (e) => {
    const input = e.target.closest("[data-image-input]");
    if (!input) return;
    const field = input.closest(".image-field");
    const file = input.files && input.files[0];
    if (!file) return;
    if (file.type && !file.type.startsWith("image/")) {
      toast("Please choose an image file", "error");
      input.value = "";
      return;
    }
    const img = document.createElement("img");
    img.alt = "";
    img.src = URL.createObjectURL(file);
    $("[data-image-preview]", field).replaceChildren(img);
    $("[data-image-remove-flag]", field).value = "";
    $("[data-image-remove]", field).hidden = false;
    $("[data-image-label]", field).textContent = "Change Image";
  });

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-image-remove]");
    if (!btn) return;
    const field = btn.closest(".image-field");
    $("[data-image-input]", field).value = "";
    $("[data-image-remove-flag]", field).value = "1";
    $("[data-image-preview]", field).innerHTML = PLACEHOLDER;
    $("[data-image-label]", field).textContent = "Add Image";
    btn.hidden = true;
  });

  // ------------------------------------------------------ day card actions
  // Actions are resolved from the card's date at click time, so they stay
  // correct after a drag-and-drop swap moved the meal elements around.
  let lastDropAt = 0;

  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-day-action]");
    if (!trigger) return;
    if (Date.now() - lastDropAt < 400) return; // ignore the click that ends a drag
    const card = trigger.closest(".day-card");
    if (!card) return;
    const date = card.dataset.date;
    if (trigger.dataset.dayAction === "random") {
      htmx.ajax("POST", `/ui/day/${date}/random`, { target: "#week-region", swap: "outerHTML" });
    } else {
      htmx.ajax("GET", `/ui/day/${date}/edit`, { target: "#modal-content" });
    }
  });

  document.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches(".meal-item[data-day-action]")) {
      e.preventDefault();
      e.target.click();
    }
  });

  // --------------------------------------------------------- drag and drop
  const drag = { originCard: null, targetCard: null, x: 0, y: 0, ghostRect: null };

  function pointFrom(ev) {
    const t = ev.touches?.[0] || ev.changedTouches?.[0] || ev;
    return t && typeof t.clientX === "number" ? { x: t.clientX, y: t.clientY } : null;
  }

  function trackPointer(ev) {
    const p = pointFrom(ev);
    if (!p) return;
    drag.x = p.x;
    drag.y = p.y;
    const ghost = $(".sortable-fallback");
    if (ghost) drag.ghostRect = ghost.getBoundingClientRect();
    const under = document.elementFromPoint(p.x, p.y);
    const card = under?.closest(".day-card");
    const target = card && card !== drag.originCard && card.closest("#week-cards") ? card : null;
    if (target !== drag.targetCard) {
      drag.targetCard?.classList.remove("is-drop-target");
      target?.classList.add("is-drop-target");
      drag.targetCard = target;
    }
  }

  function swapNodes(a, b) {
    const marker = document.createComment("");
    a.replaceWith(marker);
    b.replaceWith(a);
    marker.replaceWith(b);
    // Day tint belongs to the slot, not the meal.
    const styleA = a.getAttribute("style");
    a.setAttribute("style", b.getAttribute("style") || "");
    b.setAttribute("style", styleA || "");
  }

  function animateFrom(el, fromRect) {
    if (!fromRect || reducedMotion.matches || !el.animate) return;
    const to = el.getBoundingClientRect();
    const dx = fromRect.left - to.left;
    const dy = fromRect.top - to.top;
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
    el.animate(
      [{ transform: `translate(${dx}px, ${dy}px)`, opacity: 0.85 }, { transform: "none", opacity: 1 }],
      { duration: 320, easing: "cubic-bezier(.2,.8,.2,1)" },
    );
  }

  async function saveSwap(fromDate, toDate) {
    try {
      const res = await fetch("/api/schedule/swap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ from_date: fromDate, to_date: toDate }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
    } catch (err) {
      toast("Couldn't save that change. Restoring your plan.", "error");
      htmx.trigger(document.body, "refreshWeek");
    }
  }

  function onDragEnd() {
    document.removeEventListener("pointermove", trackPointer);
    document.removeEventListener("touchmove", trackPointer);
    document.removeEventListener("mousemove", trackPointer);
    document.body.classList.remove("is-dragging-meal");
    lastDropAt = Date.now();
    // SortableJS swallows "the next click" after a fallback drag. A mouse drop
    // normally produces that click, but touch drops on desktop browsers don't,
    // which would eat the user's next real tap. Consume it with a harmless one.
    setTimeout(() => document.body.dispatchEvent(new MouseEvent("click", { bubbles: true })), 60);

    const from = drag.originCard;
    const to = drag.targetCard;
    to?.classList.remove("is-drop-target");
    drag.originCard = drag.targetCard = null;
    if (!from || !to || !from.isConnected || !to.isConnected) return;

    const moving = $(".meal-item", from);
    const other = $(".meal-item", to);
    if (!moving || !other) return;
    const ghostRect = drag.ghostRect;
    const otherRect = other.getBoundingClientRect();
    const targetWasEmpty = other.classList.contains("is-empty");

    swapNodes(moving, other); // optimistic UI update
    animateFrom(moving, ghostRect);
    animateFrom(other, otherRect);

    const name = moving.dataset.mealName || "Meal";
    if (targetWasEmpty) {
      toast(`${name} moved to ${to.dataset.day}`);
    } else {
      const [first, second] = from.dataset.date < to.dataset.date ? [from, to] : [to, from];
      toast(`${first.dataset.day} and ${second.dataset.day} meals swapped`);
    }
    saveSwap(from.dataset.date, to.dataset.date);
  }

  function initSlots(root) {
    if (!window.Sortable) return;
    root.querySelectorAll("[data-slot]").forEach((slot) => {
      if (slot._sortable) return;
      slot._sortable = Sortable.create(slot, {
        group: "week",
        sort: false,
        filter: ".is-empty",          // empty days are drop targets, not draggable
        preventOnFilter: false,
        forceFallback: true,          // same smooth floating card for mouse and touch
        fallbackOnBody: true,
        fallbackTolerance: 4,
        delay: 200,                   // long-press on touch so normal scrolling still works
        delayOnTouchOnly: true,
        touchStartThreshold: 6,
        ghostClass: "is-drag-origin",
        chosenClass: "is-chosen",
        dragClass: "is-dragging",
        scroll: true,
        scrollSensitivity: 90,
        scrollSpeed: 14,
        bubbleScroll: true,
        onMove: () => false,          // we handle the drop ourselves (swap / move)
        onChoose: () => navigator.vibrate?.(10),
        onStart: (evt) => {
          drag.originCard = evt.item.closest(".day-card");
          drag.targetCard = null;
          drag.ghostRect = null;
          document.body.classList.add("is-dragging-meal");
          document.addEventListener("pointermove", trackPointer, { passive: true });
          document.addEventListener("touchmove", trackPointer, { passive: true });
          document.addEventListener("mousemove", trackPointer, { passive: true });
        },
        onEnd: onDragEnd,
      });
    });
  }

  // Android shows a long-press context menu on images – suppress it on meal cards.
  document.addEventListener("contextmenu", (e) => {
    if (e.target.closest(".meal-item")) e.preventDefault();
  });

  htmx.onLoad((root) => initSlots(root));
  document.addEventListener("DOMContentLoaded", () => initSlots(document));
})();
