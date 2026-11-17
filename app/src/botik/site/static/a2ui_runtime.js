(function () {
"use strict";
var cfg = (document.getElementById("a2ui-config") || {}).dataset || {};
var demo = cfg.demo === "true";
window.__A2UI_CART__ = window.__A2UI_CART__ || [];

function cart() { return window.__A2UI_CART__; }
function cartTotal() {
  return cart().reduce(function (sum, item) {
    return sum + (Number(item.price) || 0) * (Number(item.qty) || 1);
  }, 0);
}
function refreshCart() {
  document.querySelectorAll("[data-cart-count]").forEach(function (el) {
    el.textContent = String(cart().length);
  });
  document.querySelectorAll("[data-cart-total]").forEach(function (el) {
    var root = el.closest("[data-a2ui-block]");
    el.textContent = cartTotal() + " " + ((root && root.dataset.currency) || "₽");
  });
}
function toast(text, ok) {
  var el = document.createElement("div");
  el.className = "toast toast-end toast-bottom z-[100]";
  el.innerHTML = '<div class="alert ' + (ok ? "alert-success" : "alert-error") +
    ' shadow-lg"><span></span></div>';
  el.querySelector("span").textContent = text;
  document.body.appendChild(el);
  setTimeout(function () { el.remove(); }, 3200);
}

document.querySelectorAll("[data-stepper]").forEach(function (btn) {
  btn.addEventListener("click", function () {
    var root = btn.closest("[data-a2ui-block]") || document;
    var input = root.querySelector('input[data-a2ui-id="' + btn.dataset.target + '"]');
    if (!input) return;
    var min = parseInt(input.min || "0", 10), max = parseInt(input.max || "1000", 10);
    var step = parseInt(input.step || "1", 10);
    var value = parseInt(input.value || String(min), 10);
    value += btn.dataset.stepper === "inc" ? step : -step;
    input.value = Math.min(max, Math.max(min, value));
  });
});

document.querySelectorAll("[data-a2ui-add]").forEach(function (btn) {
  btn.addEventListener("click", function () {
    cart().push({ item: btn.dataset.name, price: Number(btn.dataset.price) || 0, qty: 1 });
    refreshCart();
    btn.classList.add("btn-success");
    setTimeout(function () { btn.classList.remove("btn-success"); }, 350);
    toast("Добавлено: " + btn.dataset.name, true);
  });
});

function collect(root) {
  var data = {};
  root.querySelectorAll("[data-a2ui-id]").forEach(function (el) {
    if (!["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName)) return;
    if (el.dataset.required === "true" && !el.value.trim()) {
      el.classList.add("input-error", "select-error");
      throw new Error("Заполните поле: " + (el.placeholder || el.dataset.a2uiId));
    }
    el.classList.remove("input-error", "select-error");
    data[el.dataset.a2uiId] = el.type === "number" ? Number(el.value) : el.value;
  });
  return data;
}

function saveLocal(payload) {
  try {
    var queue = JSON.parse(localStorage.getItem("a2ui_queue") || "[]");
    queue.push(payload);
    localStorage.setItem("a2ui_queue", JSON.stringify(queue));
  } catch (_) {}
}

document.querySelectorAll("[data-a2ui-action]").forEach(function (btn) {
  btn.addEventListener("click", async function () {
    var root = btn.closest("[data-a2ui-block]");
    if (!root) return;
    var status = root.querySelector("[data-a2ui-status]");
    var action = btn.dataset.a2uiAction;
    if (action === "reset") {
      root.querySelectorAll("input, select").forEach(function (el) { el.value = el.defaultValue; });
      cart().length = 0;
      refreshCart();
      if (status) status.textContent = "";
      return;
    }
    try {
      var payload = {
        site_id: cfg.siteId,
        submit_action: root.dataset.submitAction,
        values: collect(root)
      };
      if (action === "add_to_cart") {
        cart().push(payload.values);
        refreshCart();
        if (status) status.textContent = "В корзине: " + cart().length;
        toast("Добавлено в корзину", true);
        return;
      }
      payload.cart = cart();
      payload.total = cartTotal();
      btn.classList.add("loading");
      var ok = false;
      if (demo) {
        await new Promise(function (r) { setTimeout(r, 400); });
        console.info("[A2UI demo] Заявка собрана:", payload);
        window.dispatchEvent(new CustomEvent("a2ui:submit", { detail: payload }));
        ok = true;
      } else {
        try {
          var res = await fetch((cfg.apiBase || "") + btn.dataset.endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          ok = res.ok;
        } catch (_) { ok = false; }
        if (!ok) {
          saveLocal(payload);
          ok = true;
          toast("Сервер недоступен — заявка сохранена локально", true);
        }
      }
      btn.classList.remove("loading");
      if (ok) {
        cart().length = 0;
        refreshCart();
        if (status) status.textContent = demo ? "Заявка собрана ✓ (демо)" : "Отправлено ✓";
        toast(demo ? "Заявка собрана ✓" : "Заявка отправлена", true);
      } else {
        toast("Ошибка отправки", false);
      }
    } catch (err) {
      btn.classList.remove("loading");
      toast(err.message, false);
    }
  });
});

refreshCart();
})();